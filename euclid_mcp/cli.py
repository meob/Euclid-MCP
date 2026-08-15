"""Euclid-MCP command-line interface.

A thin, human-friendly wrapper around the five reasoning tools
(``reason``, ``explain``, ``diagnose``, ``what_if``, ``check_kb``).
The engine backend is selected via ``--backend`` (``auto`` | ``prolog`` |
``native``), mirroring ``EUCLID_BACKEND``.

Usage:
    euclid-cli check [-f kb.euclid] [--knowledge "human(socrates)"]
    euclid-cli reason [-f kb.euclid] [--knowledge "..."] [--query "? mortal($who)"]
    euclid-cli explain [-f kb.euclid] [--query "..."]
    euclid-cli diagnose [-f kb.euclid] --query "..." [--mode why|why_not|what_needs]
    euclid-cli what-if [-f kb.euclid] --modifications "+ human(plato)" [--query "..."]
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import cast

from euclid_mcp.models import ProofNode
from euclid_mcp.server import (
    _setup_logging,
    check_kb,
    diagnose,
    explain,
    reason,
    what_if,
)

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2


def _load_kb(file: str | None) -> str | None:
    """Read the KB source from ``file``; None when no file is given."""
    if not file:
        return None
    path = Path(file)
    if not path.is_file():
        print(f"euclid-cli: no such file: {file}", file=sys.stderr)
        sys.exit(EXIT_USAGE)
    return path.read_text(encoding="utf-8")


def _set_backend(backend: str) -> None:
    os.environ["EUCLID_BACKEND"] = backend


def _print_json(payload: object) -> None:
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")


def _substitutions_lines(substitutions: dict) -> list[str]:
    return [f"  {key}: {value}" for key, value in sorted(substitutions.items())]


def _proof_lines(node: ProofNode | None, indent: int = 0) -> list[str]:
    """Render a proof tree as indented lines (fact/rule/and nodes)."""
    if node is None:
        return []
    pad = "  " * indent
    kind = node.type
    if kind == "fact":
        return [f"{pad}{node.goal}  [fact]"]
    if kind == "rule":
        rule_id = f" ({node.rule_id})" if node.rule_id else ""
        lines = [f"{pad}{node.goal}  [rule{rule_id}]"]
        if node.subproof is not None:
            lines.extend(_proof_lines(node.subproof, indent + 1))
        return lines
    if kind == "and":
        lines = [f"{pad}{node.goal}  [and]"]
        lines.extend(_proof_lines(node.left, indent + 1))
        lines.extend(_proof_lines(node.right, indent + 1))
        return lines
    return [f"{pad}{node.goal}  [{kind}]"]


def _render_reason(result) -> None:
    for index, sol in enumerate(result.solutions, start=1):
        print(f"Solution {index}:")
        if sol.substitutions:
            print("\n".join(_substitutions_lines(sol.substitutions)))
        print("\n".join(_proof_lines(sol.proof)) or "  (no proof)")
        print()


def _render_explain(result) -> None:
    for index, explanation in enumerate(result.explanations, start=1):
        print(f"Explanation {index}:")
        if explanation.substitutions:
            print("\n".join(_substitutions_lines(explanation.substitutions)))
        for step in explanation.steps:
            print(f"  - {step}")
        print()


def _render_diagnose(result) -> None:
    status = "HOLDS" if result.holds else "does NOT hold"
    print(f"Query: {result.query}")
    print(f"Mode:  {result.mode}")
    print(f"Query {status}.")
    if result.conclusion:
        print(f"Conclusion: {result.conclusion}")
    for finding in result.findings:
        print(f"  [{finding.type}] {finding.predicate} — {finding.detail}")


def _render_what_if(result) -> None:
    print(f"Query: {result.query}")
    print(f"Modifications: {result.modifications}")
    print(f"Solutions: {result.before_count} -> {result.after_count} (delta: {result.delta})")
    if result.conclusion:
        print(f"Conclusion: {result.conclusion}")


def _render_check(result) -> None:
    print(f"KB valid: {result.valid}")
    print(f"Facts: {result.facts_count}  Rules: {result.rules_count}  "
          f"Predicates: {result.predicates_count}")
    for error in result.errors:
        where = f" (line {error.line})" if error.line else ""
        print(f"  [error] {error.message}{where}")
    for warning in result.warnings:
        where = f" (line {warning.line})" if warning.line else ""
        print(f"  [warning] {warning.message}{where}")


def _handle(result) -> int:
    """Dispatch rendering; returns the process exit code."""
    if result.error:
        print(f"Error: {result.error}", file=sys.stderr)
        return EXIT_ERROR
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="euclid-cli",
        description="Deterministic logical reasoning via the Euclid-MCP engine.",
    )
    parser.add_argument(
        "--backend",
        choices=("auto", "prolog", "native"),
        default="auto",
        help="inference backend (default: auto)",
    )

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "-f", "--file",
        metavar="KB_FILE",
        help="read the knowledge base from a .euclid file "
             "(otherwise EUCLID_KB_PATH or preload is used)",
    )
    common.add_argument(
        "--knowledge",
        metavar="KB_TEXT",
        help="knowledge base text passed inline (takes precedence over --file)",
    )
    common.add_argument("--json", action="store_true", help="emit JSON to stdout")

    subparsers = parser.add_subparsers(dest="tool", required=True)

    p_check = subparsers.add_parser("check", parents=[common], help="validate a knowledge base")
    p_check.set_defaults(func=_run_check)

    p_reason = subparsers.add_parser("reason", parents=[common], help="run a deduction")
    p_reason.add_argument("--query", help="query to evaluate (default: from the KB)")
    p_reason.add_argument("--max-solutions", type=int, default=5)
    p_reason.add_argument("--max-depth", type=int, default=30)
    p_reason.set_defaults(func=_run_reason)

    p_explain = subparsers.add_parser(
        "explain", parents=[common], help="explain solutions in natural language"
    )
    p_explain.add_argument("--query", help="query to evaluate (default: from the KB)")
    p_explain.add_argument("--max-solutions", type=int, default=5)
    p_explain.add_argument("--max-depth", type=int, default=30)
    p_explain.set_defaults(func=_run_explain)

    p_diagnose = subparsers.add_parser(
        "diagnose", parents=[common], help="diagnose why a query holds or fails"
    )
    p_diagnose.add_argument("--query", required=True, help="query to diagnose")
    p_diagnose.add_argument(
        "--mode", choices=("why", "why_not", "what_needs"), default="why"
    )
    p_diagnose.add_argument("--max-solutions", type=int, default=5)
    p_diagnose.add_argument("--max-depth", type=int, default=30)
    p_diagnose.set_defaults(func=_run_diagnose)

    p_what_if = subparsers.add_parser(
        "what-if", parents=[common], help="evaluate knowledge modifications"
    )
    p_what_if.add_argument(
        "--modifications", required=True,
        help="+ fact(...) to add, - fact(...) to remove",
    )
    p_what_if.add_argument("--query", help="query to evaluate (default: from the KB)")
    p_what_if.add_argument("--max-solutions", type=int, default=5)
    p_what_if.add_argument("--max-depth", type=int, default=30)
    p_what_if.set_defaults(func=_run_what_if)

    return parser


def _resolve_knowledge(args: argparse.Namespace) -> str | None:
    """Effective KB source: explicit ``--knowledge``, then ``-f`` file, else None."""
    if args.knowledge:
        return cast(str, args.knowledge)
    return _load_kb(args.file)


def _run_reason(args) -> int:
    result = reason(
        knowledge=_resolve_knowledge(args),
        query=args.query,
        max_solutions=args.max_solutions,
        max_depth=args.max_depth,
    )
    if result.error:
        return _handle(result)
    if args.json:
        _print_json({
            "query": result.query,
            "solutions": [s.model_dump() for s in result.solutions],
            "elapsed_ms": result.elapsed_ms,
        })
    else:
        if result.query:
            print(f"Query: {result.query}")
        _render_reason(result)
    return EXIT_OK


def _run_explain(args) -> int:
    result = explain(
        knowledge=_resolve_knowledge(args),
        query=args.query,
        max_solutions=args.max_solutions,
        max_depth=args.max_depth,
    )
    if result.error:
        return _handle(result)
    if args.json:
        _print_json({
            "query": result.query,
            "explanations": [e.model_dump() for e in result.explanations],
            "elapsed_ms": result.elapsed_ms,
        })
    else:
        if result.query:
            print(f"Query: {result.query}")
        _render_explain(result)
    return EXIT_OK


def _run_diagnose(args) -> int:
    result = diagnose(
        knowledge=_resolve_knowledge(args),
        query=args.query,
        mode=args.mode,
        max_solutions=args.max_solutions,
        max_depth=args.max_depth,
    )
    if result.error:
        return _handle(result)
    if args.json:
        _print_json({
            "query": result.query,
            "mode": result.mode,
            "holds": result.holds,
            "findings": [f.model_dump() for f in result.findings],
            "conclusion": result.conclusion,
            "elapsed_ms": result.elapsed_ms,
        })
    else:
        _render_diagnose(result)
    return EXIT_OK


def _run_what_if(args) -> int:
    result = what_if(
        base_knowledge=_resolve_knowledge(args),
        modifications=args.modifications,
        query=args.query,
        max_solutions=args.max_solutions,
        max_depth=args.max_depth,
    )
    if result.error:
        return _handle(result)
    if args.json:
        _print_json({
            "query": result.query,
            "modifications": result.modifications,
            "before_count": result.before_count,
            "after_count": result.after_count,
            "delta": result.delta,
            "conclusion": result.conclusion,
            "elapsed_ms": result.elapsed_ms,
        })
    else:
        _render_what_if(result)
    return EXIT_OK


def _run_check(args) -> int:
    result = check_kb(knowledge=_resolve_knowledge(args))
    if result.error:
        return _handle(result)
    if args.json:
        _print_json({
            "valid": result.valid,
            "errors": [e.model_dump() for e in result.errors],
            "warnings": [w.model_dump() for w in result.warnings],
            "facts_count": result.facts_count,
            "rules_count": result.rules_count,
            "predicates_count": result.predicates_count,
            "elapsed_ms": result.elapsed_ms,
        })
    else:
        _render_check(result)
    return EXIT_ERROR if not result.valid else EXIT_OK


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    _set_backend(args.backend)
    return cast(int, args.func(args))


if __name__ == "__main__":
    sys.exit(main())
