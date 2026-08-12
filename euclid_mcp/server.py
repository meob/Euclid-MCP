import functools
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, TypeVar, cast

from mcp.server.mcpserver import MCPServer

from euclid_mcp.explain import explain_solution
from euclid_mcp.kb_summary import build_kb_summary
from euclid_mcp.language import parse
from euclid_mcp.linter import lint_rule
from euclid_mcp.models import (
    DiagnosisFinding,
    DiagnosisResult,
    Explanation,
    ExplanationResult,
    KBCheckResult,
    KBError,
    ReasonResult,
    WhatIfResult,
)
from euclid_mcp.prolog_bridge import execute as prolog_execute
from euclid_mcp.sanitizer import sanitize
from euclid_mcp.translator import kb_to_decls_clauses

logger = logging.getLogger(__name__)

_IF_SPLIT = re.compile(r"\s+IF\s+", re.IGNORECASE)

_Fn = TypeVar("_Fn", bound=Callable[..., Any])


def _log_call(tool_name: str) -> Callable[[_Fn], _Fn]:
    """Wrap a tool to log per-call timing and outcome."""

    def decorator(fn: _Fn) -> _Fn:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.monotonic()
            result = fn(*args, **kwargs)
            elapsed_ms = (time.monotonic() - start) * 1000
            error = getattr(result, "error", None)
            solutions = getattr(result, "solutions", None)
            count = len(solutions) if isinstance(solutions, list) else None
            if error:
                logger.warning(
                    "tool=%s elapsed_ms=%.1f error=%s",
                    tool_name,
                    elapsed_ms,
                    error,
                )
            else:
                logger.info(
                    "tool=%s elapsed_ms=%.1f solutions=%s",
                    tool_name,
                    elapsed_ms,
                    count if count is not None else "-",
                )
            return result

        return cast(_Fn, wrapper)

    return decorator


def _setup_logging() -> None:
    """Configure root logging from the EUCLID_LOG_LEVEL env var (optional)."""
    level = os.environ.get("EUCLID_LOG_LEVEL", "").upper()
    if level in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        logging.basicConfig(
            level=getattr(logging, level),
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )


def _split_rule(rule: str) -> tuple[str, str]:
    """Split a rule into head and body on 'IF' (case-insensitive)."""
    parts = _IF_SPLIT.split(rule, maxsplit=1)
    return (parts[0], parts[1]) if len(parts) == 2 else (parts[0], "")


def _is_not_goal(goal: str) -> bool:
    """Check if a goal is a NOT-prefixed negation (case-insensitive)."""
    return goal.strip().upper().startswith("NOT ")

# Security limits
MAX_KNOWLEDGE_LENGTH = 500_000  # 500 KB
MAX_QUERY_LENGTH = 5_000  # 5 KB, for the query parameter
MAX_DEPTH_LIMIT = 500
MAX_SOLUTIONS_LIMIT = 1000

_KB_PATH_ENV = "EUCLID_KB_PATH"


def _extract_predicate(text: str) -> tuple[str, str] | None:
    """Extract predicate name and args from a term like 'parent(tom, bob)'."""
    text = text.strip()
    match = re.match(r"([^\W\d_]\w*)\s*\((.*)\)\s*$", text)
    if match:
        return match.group(1), match.group(2)
    # Zero-arity fact
    match = re.match(r"([^\W\d_]\w*)\s*$", text)
    if match:
        return match.group(1), ""
    return None


def _split_conjunction(body: str) -> list[str]:
    """Split a rule body on AND, respecting parentheses."""
    parts = []
    depth = 0
    current: list[str] = []
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(ch)
    if current:
        tail = "".join(current).strip()
        if tail:
            parts.append(tail)
    return parts


def _body_predicates(body: str) -> set[str]:
    """Extract predicate names referenced in a rule body.

    Handles negation (NOT ...) and skips arithmetic goals and variables.
    Used by check_kb for exact recursive-rule detection (avoids substring
    false positives such as 'deploy_role_level' matching 'role_level').
    """
    preds: set[str] = set()
    for goal in _split_conjunction(body):
        goal = goal.strip()
        if _is_not_goal(goal):
            goal = goal[4:].strip()
        parsed = _extract_predicate(goal)
        if parsed:
            preds.add(parsed[0])
    return preds


def _run_check_kb(knowledge: str) -> KBCheckResult:
    """Core KB validation, independent of the MCP server.

    Defined before the server object so the preloaded KB (EUCLID_KB_PATH) can
    be validated at import time, before MCPServer is created.
    """
    start = time.monotonic()
    errors: list[KBError] = []
    warnings: list[KBError] = []

    # Parse the KB
    try:
        kb = parse(knowledge)
    except Exception as exc:
        return KBCheckResult(
            valid=False,
            errors=[KBError(type="parse_error", message=str(exc))],
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    # Collect all defined predicates
    defined: dict[str, set[int]] = {}  # name -> set of arities

    for fact in kb.facts:
        parsed = _extract_predicate(fact)
        if parsed:
            name, args = parsed
            arity = args.count(",") + 1 if args else 0
            defined.setdefault(name, set()).add(arity)

    for rule in kb.rules:
        head, _ = _split_rule(rule)
        parsed = _extract_predicate(head.strip())
        if parsed:
            name, args = parsed
            arity = args.count(",") + 1 if args else 0
            defined.setdefault(name, set()).add(arity)

    # Check 1: duplicate facts
    seen_facts: dict[str, int] = {}
    for fact in kb.facts:
        normalized = fact.strip().rstrip(".")
        if normalized in seen_facts:
            warnings.append(KBError(
                type="duplicate_fact",
                message=f"Duplicate fact: {normalized}",
                predicate=normalized.split("(")[0] if "(" in normalized else normalized,
            ))
        seen_facts[normalized] = seen_facts.get(normalized, 0) + 1

    # Check 2: undefined predicates in rule bodies
    for rule in kb.rules:
        _, body = _split_rule(rule)
        body_goals = _split_conjunction(body)

        for goal in body_goals:
            goal = goal.strip()
            if _is_not_goal(goal):
                goal = goal[4:].strip()

            goal_pred = _extract_predicate(goal)
            if goal_pred:
                goal_name, goal_args = goal_pred
                # Skip variables, arithmetic, and wildcards
                if goal_name.startswith("$") or goal_name in (
                    "true", "false", "is", ">", ">=", "<", "<=", "=<", "==", "=\\=", "!="
                ):
                    continue
                goal_arity = goal_args.count(",") + 1 if goal_args else 0
                if goal_name not in defined:
                    errors.append(KBError(
                        type="undefined_predicate",
                        message=(
                            "Rule body references undefined predicate "
                            f"'{goal_name}/{goal_arity}'"
                        ),
                        predicate=f"{goal_name}/{goal_arity}",
                    ))

    # Check 3: circular rules (simple detection)
    rule_heads: dict[str, list[str]] = {}
    for rule in kb.rules:
        head, _ = _split_rule(rule)
        parsed = _extract_predicate(head.strip())
        if parsed:
            name, _ = parsed
            rule_heads.setdefault(name, []).append(rule)

    for pred_name, rules in rule_heads.items():
        for rule in rules:
            _, body = _split_rule(rule)
            if pred_name in _body_predicates(body):
                # Recursive rule — check if there's also a non-recursive base case
                has_base = any(
                    pred_name not in _body_predicates(_split_rule(r)[1])
                    for r in rules
                )
                if not has_base:
                    errors.append(KBError(
                        type="circular_rule",
                        message=f"Recursive rule for '{pred_name}' without base case",
                        predicate=pred_name,
                    ))

    # Check 4: query referenced but not defined
    if kb.query:
        query_pred = _extract_predicate(kb.query)
        if query_pred:
            name, args = query_pred
            if name not in defined:
                errors.append(KBError(
                    type="undefined_predicate",
                    message=f"Query references undefined predicate '{name}'",
                    predicate=name,
                ))

    # Check 5: unsafe negation (lint)
    for rule in kb.rules:
        lint_warnings = lint_rule(rule)
        for w in lint_warnings:
            warnings.append(KBError(type="unsafe_negation", message=w))

    # Check 6: duplicate rule IDs
    seen_rule_ids: dict[str, int] = {}
    for idx, rule in enumerate(kb.rules):
        rid = kb.rule_ids.get(idx)
        if not rid:
            continue
        if rid in seen_rule_ids:
            warnings.append(KBError(
                type="duplicate_rule_id",
                message=f"Duplicate rule ID: {rid}",
                predicate=rid,
            ))
        seen_rule_ids[rid] = seen_rule_ids.get(rid, 0) + 1

    valid = len(errors) == 0

    elapsed = (time.monotonic() - start) * 1000
    return KBCheckResult(
        valid=valid,
        errors=errors,
        warnings=warnings,
        facts_count=len(kb.facts),
        rules_count=len(kb.rules),
        predicates_count=len(defined),
        elapsed_ms=elapsed,
    )


def _load_preloaded_kb() -> str | None:
    """Load and validate the KB referenced by EUCLID_KB_PATH.

    Returns None when the env var is unset. Raises RuntimeError (fail-fast at
    import time) when the file is missing, unreadable, oversized, or invalid.
    """
    path = os.environ.get(_KB_PATH_ENV, "").strip()
    if not path:
        return None
    if not os.path.isfile(path):
        raise RuntimeError(
            f"EUCLID_KB_PATH points to a missing file: {path}. "
            "Create the file or unset EUCLID_KB_PATH to run without "
            "a preloaded KB."
        )
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(
            f"EUCLID_KB_PATH file is not readable: {path}: {exc}"
        ) from exc
    if len(text) > MAX_KNOWLEDGE_LENGTH:
        raise RuntimeError(
            f"EUCLID_KB_PATH file exceeds the maximum KB size "
            f"({len(text):,} > {MAX_KNOWLEDGE_LENGTH:,} bytes): {path}"
        )
    result = _run_check_kb(text)
    if not result.valid:
        details = "; ".join(e.message for e in result.errors)
        raise RuntimeError(
            f"EUCLID_KB_PATH file is not a valid knowledge base: "
            f"{path}: {details}"
        )
    return text


_PRELOADED_KB = _load_preloaded_kb()

_BASE_INSTRUCTIONS = """Euclid-MCP is a deterministic logical reasoning engine.
Write facts and rules in Euclid IR, the engine returns solutions with proof trees.

Syntax:
  Variables: $name  |  Implication: IF  |  Conjunction: AND  |  Query prefix: ?
  Negation: NOT  |  Arithmetic: >, >=, <, <=, ==, =\\=  |  Multi-line rules supported

Examples:
    human(socrates)
    mortal($x) IF human($x)
    ? mortal($who)

YAML format also supported (see AGENTS.md for full reference).
Use when: logical rules, compliance checks, RBAC, proof trees, deterministic answers."""


def _server_instructions() -> str:
    """Base instructions plus a digest of the preloaded KB when present.

    MCPServer.instructions is read-only, so the digest is computed before the
    server object is created.
    """
    if not _PRELOADED_KB:
        return _BASE_INSTRUCTIONS
    return f"{_BASE_INSTRUCTIONS}\n\n{build_kb_summary(_PRELOADED_KB)}"


mcp = MCPServer("Euclid-MCP", instructions=_server_instructions())


def _resolve_knowledge(knowledge: str | None) -> str | None:
    """Effective KB source: an explicit value wins, else the preloaded KB."""
    if knowledge is not None and knowledge.strip():
        return knowledge
    return _PRELOADED_KB


@mcp.tool(
    description="Perform logical deduction on a knowledge base "
    "and return solutions with proof trees for each result",
)
@_log_call("reason")
def reason(
    knowledge: str | None = None,
    query: str | None = None,
    max_solutions: int = 5,
    max_depth: int = 30,
) -> ReasonResult:
    start = time.monotonic()

    kb_source = _resolve_knowledge(knowledge)
    if kb_source is None:
        return ReasonResult(
            error="No knowledge provided: pass 'knowledge' or preload a KB "
            "via EUCLID_KB_PATH.",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    # Security: validate limits
    if not (1 <= max_solutions <= MAX_SOLUTIONS_LIMIT):
        return ReasonResult(
            error=f"max_solutions must be between 1 and {MAX_SOLUTIONS_LIMIT}",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )
    if not (1 <= max_depth <= MAX_DEPTH_LIMIT):
        return ReasonResult(
            error=f"max_depth must be between 1 and {MAX_DEPTH_LIMIT}",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )
    if query is not None and len(query) > MAX_QUERY_LENGTH:
        return ReasonResult(
            error=f"Query exceeds maximum allowed size "
            f"({len(query):,} > {MAX_QUERY_LENGTH:,} characters)",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    # Security: reject oversized input
    if len(kb_source) > MAX_KNOWLEDGE_LENGTH:
        return ReasonResult(
            error=f"Knowledge exceeds maximum allowed size "
            f"({len(kb_source):,} > {MAX_KNOWLEDGE_LENGTH:,} bytes)",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    try:
        kb = parse(kb_source)
    except Exception as exc:
        return ReasonResult(
            error=f"Knowledge parsing error: {exc}",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    if query:
        try:
            sanitize(query)
        except ValueError as exc:
            return ReasonResult(
                error=str(exc),
                elapsed_ms=(time.monotonic() - start) * 1000,
            )
        kb.query = query

    if not kb.query:
        return ReasonResult(
            error="No query specified. "
            "Add ? query or query: in the knowledge, "
            "or pass the query parameter.",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    try:
        decls, clauses = kb_to_decls_clauses(kb)
    except Exception as exc:
        return ReasonResult(
            error=f"Prolog code generation error: {exc}",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    try:
        solutions = prolog_execute(
            decls,
            clauses,
            kb.query,
            max_depth=max_depth,
            max_solutions=max_solutions,
            timeout=30,
        )
    except RuntimeError as exc:
        return ReasonResult(
            error=str(exc),
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    elapsed = (time.monotonic() - start) * 1000
    return ReasonResult(
        solutions=solutions[:max_solutions],
        query=kb.query,
        elapsed_ms=elapsed,
    )


# ── explain() ───────────────────────────────────────────────────────────────


@mcp.tool(
    description="Explain, in natural language, how a query is proven: "
    "walk the proof tree of each solution and return readable reasoning steps. "
    "Rule IDs are cited when present.",
)
@_log_call("explain")
def explain(
    knowledge: str | None = None,
    query: str | None = None,
    max_solutions: int = 5,
    max_depth: int = 30,
) -> ExplanationResult:
    start = time.monotonic()

    kb_source = _resolve_knowledge(knowledge)
    if kb_source is None:
        return ExplanationResult(
            query=query or "",
            error="No knowledge provided: pass 'knowledge' or preload a KB "
            "via EUCLID_KB_PATH.",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    result = reason(
        kb_source, query=query, max_solutions=max_solutions, max_depth=max_depth
    )
    if result.error:
        return ExplanationResult(
            query=query or "",
            error=result.error,
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    explanations = [
        Explanation(substitutions=sol.substitutions, steps=explain_solution(sol))
        for sol in result.solutions
    ]

    return ExplanationResult(
        query=result.query,
        explanations=explanations,
        elapsed_ms=(time.monotonic() - start) * 1000,
    )


# ── diagnose() ──────────────────────────────────────────────────────────────


@mcp.tool(
    description="Diagnose why a query succeeds or fails. "
    "Modes: 'why' (explain success), 'why_not' (explain failure), "
    "'what_needs' (what would make it succeed)",
)
@_log_call("diagnose")
def diagnose(
    knowledge: str | None = None,
    query: str = "",
    mode: str = "why",
    max_solutions: int = 5,
    max_depth: int = 30,
) -> DiagnosisResult:
    start = time.monotonic()

    kb_source = _resolve_knowledge(knowledge)
    if kb_source is None:
        return DiagnosisResult(
            error="No knowledge provided: pass 'knowledge' or preload a KB "
            "via EUCLID_KB_PATH.",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    if mode not in ("why", "why_not", "what_needs"):
        return DiagnosisResult(
            error=f"Invalid mode '{mode}'. Use 'why', 'why_not', or 'what_needs'",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    # First: check if the query holds or not
    base_result = reason(kb_source, query=query, max_solutions=max_solutions, max_depth=max_depth)
    if base_result.error:
        return DiagnosisResult(
            error=base_result.error,
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    holds = len(base_result.solutions) > 0

    # Parse KB for structural analysis
    try:
        kb = parse(kb_source)
    except Exception as exc:
        return DiagnosisResult(
            error=f"Knowledge parsing error: {exc}",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    findings = _analyze_query(kb, query, holds)

    # Build conclusion
    if mode == "why":
        if holds:
            conclusion = f"The query HOLDS. {len(base_result.solutions)} solution(s) found."
        else:
            conclusion = "The query does NOT hold."
    elif mode == "why_not":
        if holds:
            conclusion = "The query actually holds — no diagnosis needed."
        else:
            missing = [f for f in findings if f.type == "missing_fact"]
            if missing:
                preds = ", ".join(f.predicate for f in missing[:5])
                conclusion = f"The query fails. Missing facts: {preds}"
            else:
                conclusion = "The query fails. Check rule conditions."
    elif mode == "what_needs":
        if holds:
            conclusion = "The query already holds — nothing needed."
        else:
            suggestions = [f for f in findings if f.type in ("missing_fact", "missing_rule")]
            if suggestions:
                preds = ", ".join(f.predicate for f in suggestions[:5])
                conclusion = f"To make this query true, consider adding: {preds}"
            else:
                conclusion = "Cannot determine what is needed. Review rule definitions."

    elapsed = (time.monotonic() - start) * 1000
    return DiagnosisResult(
        query=query,
        mode=mode,
        holds=holds,
        findings=findings,
        proof=base_result.solutions[0].proof if base_result.solutions else None,
        solutions=base_result.solutions,
        conclusion=conclusion,
        elapsed_ms=elapsed,
    )


def _analyze_query(kb, query: str, holds: bool) -> list[DiagnosisFinding]:
    """Analyze a query against the KB and return findings."""
    findings: list[DiagnosisFinding] = []

    # Extract predicate name and args from query
    query_pred = _extract_predicate(query)
    if not query_pred:
        return findings

    pred_name, pred_args = query_pred

    # Collect all defined predicates from facts and rules
    defined_facts: dict[str, list[str]] = {}
    defined_rules: dict[str, list[str]] = {}

    for fact in kb.facts:
        parsed = _extract_predicate(fact)
        if parsed:
            name, _ = parsed
            defined_facts.setdefault(name, []).append(fact)

    for rule in kb.rules:
        head, _ = _split_rule(rule)
        parsed = _extract_predicate(head.strip())
        if parsed:
            name, _ = parsed
            defined_rules.setdefault(name, []).append(rule)

    # Check if the query predicate is defined
    if pred_name not in defined_facts and pred_name not in defined_rules:
        findings.append(DiagnosisFinding(
            type="missing_fact",
            predicate=pred_name,
            detail=f"No facts or rules defined for '{pred_name}'",
        ))
        return findings

    # Analyze each rule that could match the query
    for rule in defined_rules.get(pred_name, []):
        _, body = _split_rule(rule)
        body_goals = _split_conjunction(body)

        for goal in body_goals:
            goal = goal.strip()
            if not goal or _is_not_goal(goal):
                continue

            # Check if goal references a defined predicate
            goal_pred = _extract_predicate(goal)
            if goal_pred:
                goal_name, _ = goal_pred
                if goal_name not in defined_facts and goal_name not in defined_rules:
                    findings.append(DiagnosisFinding(
                        type="missing_fact",
                        predicate=goal_name,
                        detail=f"Rule body references '{goal_name}' which is not defined",
                    ))
                elif goal_name in defined_facts:
                    findings.append(DiagnosisFinding(
                        type="satisfied",
                        predicate=goal_name,
                        detail=(
                            f"Facts exist for '{goal_name}' "
                            f"({len(defined_facts[goal_name])} facts)"
                        ),
                    ))

    # Check for circular rules
    if holds:
        for rule in defined_rules.get(pred_name, []):
            _, body = _split_rule(rule)
            if pred_name in body:
                findings.append(DiagnosisFinding(
                    type="blocking_condition",
                    predicate=pred_name,
                    detail=f"Recursive rule detected: {rule.strip()[:80]}",
                ))

    return findings


# ── what_if() ───────────────────────────────────────────────────────────────


@mcp.tool(
    description="What-if analysis: apply modifications to a knowledge base "
    "and see how they affect query results. "
    "Use + prefix to add facts, - prefix to remove facts.",
)
@_log_call("what_if")
def what_if(
    base_knowledge: str | None = None,
    modifications: str = "",
    query: str = "",
    max_solutions: int = 5,
    max_depth: int = 30,
) -> WhatIfResult:
    start = time.monotonic()

    kb_source = _resolve_knowledge(base_knowledge)
    if kb_source is None:
        return WhatIfResult(
            error="No base knowledge provided: pass 'base_knowledge' or "
            "preload a KB via EUCLID_KB_PATH.",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    # Validate input
    if not modifications.strip():
        return WhatIfResult(
            error="No modifications specified. Use + to add or - to remove facts.",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    # Parse modifications
    add_facts: list[str] = []
    remove_facts: list[str] = []
    for line in modifications.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("+ "):
            content = line[2:].strip()
            # Handle AND-separated facts: "fact1 AND fact2"
            for part in re.split(r"\s+and\s+", content, flags=re.IGNORECASE):
                add_facts.append(part.strip())
        elif line.startswith("- "):
            content = line[2:].strip()
            # Handle AND-separated facts
            for part in re.split(r"\s+and\s+", content, flags=re.IGNORECASE):
                remove_facts.append(part.strip())
        else:
            return WhatIfResult(
                error=f"Invalid modification line: '{line}'. Use + or - prefix.",
                elapsed_ms=(time.monotonic() - start) * 1000,
            )

    # Build modified knowledge
    modified_lines: list[str] = []
    for line in kb_source.splitlines():
        stripped = line.strip()
        # Skip removed facts
        if any(_facts_match(stripped, rf) for rf in remove_facts):
            continue
        modified_lines.append(line)

    # Add new facts
    for fact in add_facts:
        modified_lines.append(fact)

    modified_knowledge = "\n".join(modified_lines)

    # Run before (base only) and after (modified)
    base_result = reason(
        kb_source, query=query,
        max_solutions=max_solutions, max_depth=max_depth,
    )
    mod_result = reason(
        modified_knowledge, query=query,
        max_solutions=max_solutions, max_depth=max_depth,
    )

    if base_result.error:
        return WhatIfResult(
            error=f"Base knowledge error: {base_result.error}",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )
    if mod_result.error:
        return WhatIfResult(
            error=f"Modified knowledge error: {mod_result.error}",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    before_count = len(base_result.solutions)
    after_count = len(mod_result.solutions)

    if after_count > before_count:
        delta = "more"
    elif after_count < before_count:
        delta = "less"
    elif after_count == 0:
        delta = "same"
    else:
        delta = "same"

    mod_label = ", ".join(
        list(f"+ {f}" for f in add_facts) + list(f"- {f}" for f in remove_facts)
    )

    conclusion_parts: list[str] = []
    if before_count == 0 and after_count > 0:
        conclusion_parts.append(
            f"The modification ENABLES the query ({after_count} new solution(s))"
        )
    elif before_count > 0 and after_count == 0:
        conclusion_parts.append(
            f"The modification BLOCKS the query (was {before_count} solution(s))"
        )
    elif after_count > before_count:
        conclusion_parts.append(
            f"Solutions increased: {before_count} -> {after_count}"
        )
    elif after_count < before_count:
        conclusion_parts.append(
            f"Solutions decreased: {before_count} -> {after_count}"
        )
    else:
        conclusion_parts.append(f"No change in solution count ({after_count})")

    conclusion = ". ".join(conclusion_parts) + "."

    elapsed = (time.monotonic() - start) * 1000
    return WhatIfResult(
        query=query,
        modifications=mod_label,
        before_count=before_count,
        after_count=after_count,
        delta=delta,
        solutions_before=base_result.solutions,
        solutions_after=mod_result.solutions,
        conclusion=conclusion,
        elapsed_ms=elapsed,
    )


def _facts_match(line: str, pattern: str) -> bool:
    """Check if a knowledge line matches a fact pattern (for removal)."""
    line = line.strip().rstrip(".")
    pattern = pattern.strip().rstrip(".")
    return line == pattern


# ── check_kb() ──────────────────────────────────────────────────────────────


@mcp.tool(
    description="Check a knowledge base for consistency: "
    "syntax errors, undefined predicates, circular rules, duplicates.",
)
@_log_call("check_kb")
def check_kb(knowledge: str | None = None) -> KBCheckResult:
    start = time.monotonic()
    kb_source = _resolve_knowledge(knowledge)
    if kb_source is None:
        return KBCheckResult(
            valid=False,
            errors=[KBError(
                type="no_knowledge",
                message="No knowledge provided: pass 'knowledge' or preload "
                        "a KB via EUCLID_KB_PATH.",
            )],
            error="No knowledge provided: pass 'knowledge' or preload a KB "
                  "via EUCLID_KB_PATH.",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )
    return _run_check_kb(kb_source)


def main() -> None:
    _setup_logging()
    mcp.run()


if __name__ == "__main__":
    main()
