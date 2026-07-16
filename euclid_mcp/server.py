import re
import time

from mcp.server.fastmcp import FastMCP

from euclid_mcp.language import parse
from euclid_mcp.models import (
    DiagnosisFinding,
    DiagnosisResult,
    KBCheckResult,
    KBError,
    ReasonResult,
    WhatIfResult,
)
from euclid_mcp.prolog_bridge import execute as prolog_execute
from euclid_mcp.translator import to_prolog

# Security limits
MAX_KNOWLEDGE_LENGTH = 500_000  # 500 KB
MAX_DEPTH_LIMIT = 500
MAX_SOLUTIONS_LIMIT = 1000

mcp = FastMCP(
    "Euclid-MCP",
    instructions="""Euclid-MCP is a deterministic logical reasoning engine.
Write facts and rules in Euclid IR, the engine returns solutions with proof trees.

Syntax:
  Variables: $name  |  Implication: IF  |  Conjunction: AND  |  Query prefix: ?
  Negation: NOT  |  Arithmetic: >, >=, <, <=, =:=, =\\=  |  Multi-line rules supported

Examples:
    human(socrates)
    mortal($x) IF human($x)
    ? mortal($who)

YAML format also supported (see AGENTS.md for full reference).
Use when: logical rules, compliance checks, RBAC, proof trees, deterministic answers.
""",
)


@mcp.tool(
    description="Perform logical deduction on a knowledge base "
    "and return solutions with proof trees for each result",
)
def reason(
    knowledge: str,
    query: str | None = None,
    max_solutions: int = 5,
    max_depth: int = 30,
) -> ReasonResult:
    start = time.monotonic()

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

    # Security: reject oversized input
    if len(knowledge) > MAX_KNOWLEDGE_LENGTH:
        return ReasonResult(
            error=f"Knowledge exceeds maximum allowed size "
            f"({len(knowledge):,} > {MAX_KNOWLEDGE_LENGTH:,} bytes)",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    try:
        kb = parse(knowledge)
    except Exception as exc:
        return ReasonResult(
            error=f"Knowledge parsing error: {exc}",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    if query:
        kb.query = query

    if not kb.query:
        return ReasonResult(
            error="No query specified. "
            "Add ? query or query: in the knowledge, "
            "or pass the query parameter.",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    try:
        prolog_code = to_prolog(kb, max_depth=max_depth, max_solutions=max_solutions)
    except Exception as exc:
        return ReasonResult(
            error=f"Prolog code generation error: {exc}",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    try:
        solutions = prolog_execute(prolog_code, timeout=30)
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


# ── diagnose() ──────────────────────────────────────────────────────────────


@mcp.tool(
    description="Diagnose why a query succeeds or fails. "
    "Modes: 'why' (explain success), 'why_not' (explain failure), "
    "'what_needs' (what would make it succeed)",
)
def diagnose(
    knowledge: str,
    query: str,
    mode: str = "why",
    max_solutions: int = 5,
    max_depth: int = 30,
) -> DiagnosisResult:
    start = time.monotonic()

    if mode not in ("why", "why_not", "what_needs"):
        return DiagnosisResult(
            error=f"Invalid mode '{mode}'. Use 'why', 'why_not', or 'what_needs'",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    # First: check if the query holds or not
    base_result = reason(knowledge, query=query, max_solutions=max_solutions, max_depth=max_depth)
    if base_result.error:
        return DiagnosisResult(
            error=base_result.error,
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    holds = len(base_result.solutions) > 0

    # Parse KB for structural analysis
    try:
        kb = parse(knowledge)
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
        head = rule.split(" IF ")[0].strip()
        parsed = _extract_predicate(head)
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
        body = rule.split(" IF ", 1)[1] if " IF " in rule else ""
        body_goals = _split_conjunction(body)

        for goal in body_goals:
            goal = goal.strip()
            if not goal or goal.startswith("NOT "):
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
                        detail=f"Facts exist for '{goal_name}' ({len(defined_facts[goal_name])} facts)",
                    ))

    # Check for circular rules
    if holds:
        for rule in defined_rules.get(pred_name, []):
            body = rule.split(" IF ", 1)[1] if " IF " in rule else ""
            if pred_name in body:
                findings.append(DiagnosisFinding(
                    type="blocking_condition",
                    predicate=pred_name,
                    detail=f"Recursive rule detected: {rule.strip()[:80]}",
                ))

    return findings


def _extract_predicate(text: str) -> tuple[str, str] | None:
    """Extract predicate name and args from a term like 'parent(tom, bob)'."""
    text = text.strip()
    match = re.match(r"([a-z_]\w*)\s*\((.*)\)\s*$", text)
    if match:
        return match.group(1), match.group(2)
    # Zero-arity fact
    match = re.match(r"([a-z_]\w*)\s*$", text)
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


# ── what_if() ───────────────────────────────────────────────────────────────


@mcp.tool(
    description="What-if analysis: apply modifications to a knowledge base "
    "and see how they affect query results. "
    "Use + prefix to add facts, - prefix to remove facts.",
)
def what_if(
    base_knowledge: str,
    modifications: str,
    query: str,
    max_solutions: int = 5,
    max_depth: int = 30,
) -> WhatIfResult:
    start = time.monotonic()

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
            for part in content.split(" AND "):
                add_facts.append(part.strip())
        elif line.startswith("- "):
            content = line[2:].strip()
            # Handle AND-separated facts
            for part in content.split(" AND "):
                remove_facts.append(part.strip())
        else:
            return WhatIfResult(
                error=f"Invalid modification line: '{line}'. Use + or - prefix.",
                elapsed_ms=(time.monotonic() - start) * 1000,
            )

    # Build modified knowledge
    modified_lines: list[str] = []
    for line in base_knowledge.splitlines():
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
    base_result = reason(base_knowledge, query=query, max_solutions=max_solutions, max_depth=max_depth)
    mod_result = reason(modified_knowledge, query=query, max_solutions=max_solutions, max_depth=max_depth)

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
def check_kb(knowledge: str) -> KBCheckResult:
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
        head = rule.split(" IF ")[0].strip()
        parsed = _extract_predicate(head)
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
        body = rule.split(" IF ", 1)[1] if " IF " in rule else ""
        body_goals = _split_conjunction(body)

        for goal in body_goals:
            goal = goal.strip()
            if goal.startswith("NOT "):
                goal = goal[4:].strip()

            goal_pred = _extract_predicate(goal)
            if goal_pred:
                goal_name, goal_args = goal_pred
                # Skip variables, arithmetic, and wildcards
                if goal_name.startswith("$") or goal_name in (
                    "true", "false", "is", ">", ">=", "<", "=<", "=:=", "=\\="
                ):
                    continue
                goal_arity = goal_args.count(",") + 1 if goal_args else 0
                if goal_name not in defined:
                    errors.append(KBError(
                        type="undefined_predicate",
                        message=f"Rule body references undefined predicate '{goal_name}/{goal_arity}'",
                        predicate=f"{goal_name}/{goal_arity}",
                    ))

    # Check 3: circular rules (simple detection)
    rule_heads: dict[str, list[str]] = {}
    for rule in kb.rules:
        head = rule.split(" IF ")[0].strip()
        parsed = _extract_predicate(head)
        if parsed:
            name, _ = parsed
            rule_heads.setdefault(name, []).append(rule)

    for pred_name, rules in rule_heads.items():
        for rule in rules:
            body = rule.split(" IF ", 1)[1] if " IF " in rule else ""
            if pred_name in body:
                # Recursive rule — check if there's also a non-recursive base case
                has_base = any(pred_name not in (r.split(" IF ", 1)[1] if " IF " in r else "") for r in rules)
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


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
