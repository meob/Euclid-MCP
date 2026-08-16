"""Euclid-MCP command-line interface.

A thin, human-friendly wrapper around the five reasoning tools
(``reason``, ``explain``, ``diagnose``, ``what_if``, ``check_kb``).
The engine backend is selected via ``--backend`` (``auto`` | ``prolog`` |
``native``), mirroring ``EUCLID_BACKEND``.

Without a subcommand, ``euclid-cli`` opens an interactive Euclid-IR REPL:
facts and rules accumulate in a session knowledge base, ``? query`` lines run
deductions, and ``:`` meta commands cover the remaining tools. The same loop
reads piped input, so it doubles as a batch script runner.

Usage:
    euclid-cli check [-f kb.euclid] [--knowledge "human(socrates)"]
    euclid-cli reason [-f kb.euclid] [--knowledge "..."] [--query "? mortal($who)"]
    euclid-cli explain [-f kb.euclid] [--query "..."]
    euclid-cli diagnose [-f kb.euclid] --query "..." [--mode why|why_not|what_needs]
    euclid-cli what-if [-f kb.euclid] --modifications "+ human(plato)" [--query "..."]
    euclid-cli [-f kb.euclid]            # interactive REPL
    echo "human(socrates)\\n? mortal($who)" | euclid-cli   # batch script
"""

import argparse
import json
import os
import re
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

# A rule keeps consuming lines while its body is empty or ends with `and`
# (see language._parse_text). Mirror that here to drive the continuation prompt.
_IF_PATTERN = re.compile(r"\s+if\s+", re.IGNORECASE)
_INCOMPLETE_TAIL = re.compile(r"(?:if|and)\s*$", re.IGNORECASE)
_COMMENT_PATTERN = re.compile(r"(?<!\S)\s*(#|//|%).*$")


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


def _strip_comment(line: str) -> str:
    """Drop trailing comments (#, //, %) before continuation detection."""
    return _COMMENT_PATTERN.sub("", line)


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
        label = f"{pad}{node.goal}  [and]" if node.goal else f"{pad}[and]"
        lines = [label]
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
    for predicate in result.predicates:
        arities = "/".join(str(a) for a in predicate.arities) or "?"
        print(f"  - {predicate.name}/{arities}: {predicate.facts} facts, "
              f"{predicate.rules} rules")
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
        description="Deterministic logical reasoning via the Euclid-MCP engine. "
                    "Run with no subcommand for the interactive Euclid-IR REPL.",
    )
    parser.add_argument(
        "--backend",
        choices=("auto", "prolog", "native"),
        default="auto",
        help="inference backend (default: auto)",
    )
    parser.add_argument(
        "-f", "--file",
        metavar="KB_FILE",
        help="read the knowledge base from a .euclid file, or seed the "
             "interactive session with it (otherwise EUCLID_KB_PATH or "
             "preload is used)",
    )
    parser.add_argument(
        "--knowledge",
        metavar="KB_TEXT",
        help="knowledge base text passed inline (takes precedence over --file)",
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

    subparsers = parser.add_subparsers(dest="tool")

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
            "predicates": [p.model_dump() for p in result.predicates],
            "elapsed_ms": result.elapsed_ms,
        })
    else:
        _render_check(result)
    return EXIT_ERROR if not result.valid else EXIT_OK


# ── Interactive REPL ─────────────────────────────────────────────────────────


class _ExitRepl(Exception):
    """Raised to terminate the REPL cleanly (e.g. :quit)."""


class _Repl:
    """Interactive (and batch) Euclid-IR shell backed by the tool functions.

    Facts and rules accumulate in a session knowledge base that persists
    across ``? query`` lines. Piped input runs the same loop without prompts.
    """

    PROMPT = "euclid > "
    CONTINUATION = "... > "

    def __init__(self, seed: str | None = None) -> None:
        self._lines: list[str] = seed.split("\n") if seed else []
        self._pending: list[str] = []
        self._last_query: str | None = None
        self._max_solutions = 5
        self._max_depth = 30

    # -- session helpers ---------------------------------------------------

    def _session_text(self) -> str | None:
        """The accumulated session KB, or None when empty."""
        text = "\n".join(self._lines).strip()
        return text or None

    def _flush(self) -> None:
        """Move pending statements into the session; roll back on syntax errors."""
        if not self._pending:
            return
        start = len(self._lines)
        self._lines.extend(self._pending)
        self._pending = []
        result = check_kb(knowledge=self._session_text())
        if result.error or any(e.type == "parse_error" for e in result.errors):
            del self._lines[start:]
            message = result.error or result.errors[0].message
            print(f"Error: {message}", file=sys.stderr)

    @staticmethod
    def _is_incomplete(line: str) -> bool:
        """True when a rule line still expects a continuation (IF/AND)."""
        cleaned = _strip_comment(line).strip()
        if not cleaned:
            return False
        is_rule = bool(_IF_PATTERN.search(cleaned)) or cleaned.lower().endswith(" if")
        return is_rule and bool(_INCOMPLETE_TAIL.search(cleaned))

    # -- line processing -----------------------------------------------------

    def _process_line(self, line: str) -> None:
        stripped = line.strip()
        if not stripped:
            self._flush()
            return
        if stripped.startswith((":", "?")):
            self._flush()
            if stripped.startswith(":"):
                self._command(stripped)
            else:
                self._last_query = stripped[1:].strip()
                self._query(self._last_query)
            return
        self._pending.append(line)
        if not self._is_incomplete(line):
            self._flush()

    # -- tool handlers --------------------------------------------------------

    def _query(self, query: str) -> None:
        result = reason(
            knowledge=self._session_text(),
            query=query,
            max_solutions=self._max_solutions,
            max_depth=self._max_depth,
        )
        if result.error:
            print(f"Error: {result.error}", file=sys.stderr)
            return
        print(f"Query: {query}")
        if not result.solutions:
            print("No solutions.")
            return
        _render_reason(result)

    def _check(self) -> None:
        if self._session_text() is None:
            print("(session KB is empty)")
            return
        result = check_kb(knowledge=self._session_text())
        if result.error:
            print(f"Error: {result.error}", file=sys.stderr)
            return
        _render_check(result)

    def _explain(self, rest: str) -> None:
        query = rest or self._last_query
        if not query:
            print("No query. Use `:explain <query>` or run `? query` first.",
                  file=sys.stderr)
            return
        result = explain(
            knowledge=self._session_text(),
            query=query,
            max_solutions=self._max_solutions,
            max_depth=self._max_depth,
        )
        if result.error:
            print(f"Error: {result.error}", file=sys.stderr)
            return
        _render_explain(result)

    def _diagnose(self, rest: str) -> None:
        mode = "why"
        query: str | None = rest
        parts = rest.split()
        if "--mode" in parts:
            idx = parts.index("--mode")
            if idx + 1 < len(parts):
                mode = parts[idx + 1]
                query = " ".join(parts[:idx] + parts[idx + 2:])
        elif len(parts) >= 2 and parts[-1] in ("why", "why_not", "what_needs"):
            mode = parts[-1]
            query = " ".join(parts[:-1])
        query = query or self._last_query
        if not query:
            print("No query. Use `:diagnose <query>` or run `? query` first.",
                  file=sys.stderr)
            return
        result = diagnose(
            knowledge=self._session_text(),
            query=query,
            mode=mode,
            max_solutions=self._max_solutions,
            max_depth=self._max_depth,
        )
        if result.error:
            print(f"Error: {result.error}", file=sys.stderr)
            return
        _render_diagnose(result)

    def _what_if(self, rest: str) -> None:
        if not rest:
            print("Usage: :what-if <modifications>, e.g. `:what-if + human(plato)`",
                  file=sys.stderr)
            return
        if not self._last_query:
            print("No query. Run `? query` first to set one.",
                  file=sys.stderr)
            return
        result = what_if(
            base_knowledge=self._session_text(),
            modifications=rest,
            query=self._last_query,
            max_solutions=self._max_solutions,
            max_depth=self._max_depth,
        )
        if result.error:
            print(f"Error: {result.error}", file=sys.stderr)
            return
        _render_what_if(result)

    def _load(self, path: str) -> None:
        if not path:
            print("Usage: :load <file>", file=sys.stderr)
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"Error: cannot read {path}: {exc}", file=sys.stderr)
            return
        self._lines.extend(text.split("\n"))
        print(f"Loaded {path} into the session KB.")

    def _reset(self) -> None:
        self._lines.clear()
        self._pending.clear()
        self._last_query = None
        print("Session KB cleared.")

    # -- meta commands ---------------------------------------------------------

    def _command(self, line: str) -> None:
        body = line[1:].strip()
        if not body:
            self._print_help()
            return
        name, _, rest = body.partition(" ")
        name = name.lower()
        rest = rest.strip()

        if name in ("help", "h"):
            self._print_help()
        elif name in ("quit", "q", "exit"):
            raise _ExitRepl()
        elif name == "reset":
            self._reset()
        elif name in ("check", "c"):
            self._check()
        elif name in ("kb", "list"):
            self._print_kb()
        elif name == "load":
            self._load(rest)
        elif name == "explain":
            self._explain(rest)
        elif name == "diagnose":
            self._diagnose(rest)
        elif name == "what-if":
            self._what_if(rest)
        else:
            print(f"Unknown command: :{name} — try :help", file=sys.stderr)

    def _print_kb(self) -> None:
        text = self._session_text()
        if text is None:
            print("(session KB is empty)")
            return
        print(text)

    def _print_banner(self) -> None:
        print("Euclid-MCP REPL — type facts and rules in Euclid-IR, then `? query`.")
        print("Commands: :help  :check  :kb  :load  :explain  :diagnose  "
              ":what-if  :reset  :quit")
        print()
        if self._session_text() is not None:
            result = check_kb(knowledge=self._session_text())
            print(f"Loaded session KB: {result.facts_count} facts, "
                  f"{result.rules_count} rules, {result.predicates_count} predicates.")
            for error in result.errors:
                print(f"  [error] {error.message}")

    def _print_help(self) -> None:
        print(
            """
Type facts and rules in Euclid-IR; the session KB accumulates across queries.
Run a deduction with `? query`.

    human(socrates)           add a fact
    mortal($x) IF human($x)   add a rule (continuation after IF / AND)
    ? mortal($who)            solve the query and print solutions with proofs

Commands:
    :check               validate the session KB (check_kb)
    :kb                  print the accumulated session KB
    :load <file>         append a .euclid file to the session KB
    :explain [query]     explain solutions in natural language
    :diagnose <query> [why|why_not|what_needs]
    :what-if <mods>      test modifications, e.g. "+ human(plato)"
    :reset               clear the session KB
    :quit                exit the REPL

When the session KB is empty, the EUCLID_KB_PATH / preload KB is used as
a fallback.
""".strip()
        )

    # -- main loop ---------------------------------------------------------------

    def run(self) -> int:
        interactive = sys.stdin.isatty()
        if interactive:
            self._print_banner()
        try:
            while True:
                prompt = self.PROMPT if not self._pending else self.CONTINUATION
                try:
                    raw = input(prompt if interactive else "")
                except EOFError:
                    break
                except KeyboardInterrupt:
                    if interactive:
                        print()
                    continue
                for line in raw.split("\n"):
                    self._process_line(line)
        except _ExitRepl:
            pass
        if interactive:
            print()
        return EXIT_OK


def _run_repl(args: argparse.Namespace) -> int:
    return _Repl(_resolve_knowledge(args)).run()


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    _set_backend(args.backend)
    if args.tool is None:
        return _run_repl(args)
    return cast(int, args.func(args))


if __name__ == "__main__":
    sys.exit(main())
