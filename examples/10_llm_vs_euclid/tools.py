"""
Tools definition for Ollama + executor functions that call Euclid-MCP.
"""

import sys
from pathlib import Path

# Add project root to path
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from euclid_mcp.models import (
    DiagnosisResult,
    KBCheckResult,
    ProofNode,
    ReasonResult,
    Solution,
    WhatIfResult,
)
from euclid_mcp.server import check_kb, diagnose, reason, what_if

# ── Ollama tool definitions ──

EUCLID_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "reason",
            "description": (
                "Run logical deduction over the IT security knowledge base. "
                "Use this for permission checks, access control, compliance queries, "
                "deployment authorization, data classification, or any factual question about the KB."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Euclid-IR query. Use variables like $who, $perm, $res. "
                            "Examples: "
                            "user_has_permission($who, deploy_code) "
                            "user_has_permission($who, write_code) "
                            "can_deploy($who, production) "
                            "stale_access($who) "
                            "resource($name, production, not_encrypted, _, _, _). "
                            "Compound query example (join with AND, reuse $variables): "
                            "can_access_resource($who, $res) AND resource($res, production, _, _, _, secret) AND department($who, data)"
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "diagnose",
            "description": (
                "Explain why a query succeeds or fails. "
                "Use when something should work but does not, or to understand access decisions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The query to diagnose, e.g. user_has_permission(eng_0002, deploy_code)",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["why", "why_not", "what_needs"],
                        "description": (
                            "'why' = explain why it holds, "
                            "'why_not' = explain why it fails, "
                            "'what_needs' = what would make it succeed"
                        ),
                    },
                },
                "required": ["query", "mode"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "what_if",
            "description": (
                "Test scenario analysis: apply modifications to the knowledge base "
                "and see how they affect query results. Use + to add facts, - to remove."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "modifications": {
                        "type": "string",
                        "description": (
                            "Facts to add or remove. One per line. "
                            "Prefix with + to add, - to remove. "
                            "Example: '+ has_role(eng_0002, sysadmin)' or '- has_role(eng_0002, intern)'"
                        ),
                    },
                    "query": {
                        "type": "string",
                        "description": "The query to evaluate after modifications",
                    },
                },
                "required": ["modifications", "query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_kb",
            "description": (
                "Validate the knowledge base for consistency: "
                "syntax errors, undefined predicates, circular rules."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]


# ── Executor: dispatch tool calls to Euclid-MCP ──


def format_proof_tree(node: ProofNode | None, indent: int = 0) -> list[str]:
    """Render a proof tree as box-drawing lines (Prolog-style derivation chain)."""
    if node is None:
        return []
    pad = "  " * indent
    if node.type == "fact":
        return [f"{pad}├─ FACT: {node.goal}"]
    if node.type == "rule":
        lines = [f"{pad}├─ RULE: {node.goal}", f"{pad}│  └─ body: {node.body}"]
        if node.subproof:
            lines.extend(format_proof_tree(node.subproof, indent + 2))
        return lines
    if node.type == "and":
        lines = [f"{pad}├─ AND"]
        if node.left:
            lines.extend(format_proof_tree(node.left, indent + 1))
        if node.right:
            lines.extend(format_proof_tree(node.right, indent + 1))
        return lines
    return []


def _bindings_str(substitutions: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in substitutions.items()) if substitutions else "{}"


def _proofs_block(solutions: list[Solution], max_proofs: int = 2) -> list[str]:
    """Binding lines plus proof trees for the first few solutions."""
    lines: list[str] = []
    for i, sol in enumerate(solutions, 1):
        lines.append(f"  {i}. {_bindings_str(sol.substitutions)}")
        if i <= max_proofs:
            if sol.proof:
                lines.extend(format_proof_tree(sol.proof))
            if i == max_proofs and len(solutions) > max_proofs:
                lines.append(f"  ... (proof tree shown for first {max_proofs} of {len(solutions)} solutions)")
    return lines


def format_reason_result(result: ReasonResult) -> str:
    """Format ReasonResult into a concise string for LLM consumption."""
    if result.error:
        return f"Error: {result.error}"
    if not result.solutions:
        return "No solutions found. The query does not hold."
    lines = [f"Query: {result.query}", f"Found {len(result.solutions)} solution(s) in {result.elapsed_ms:.1f}ms:"]
    for i, sol in enumerate(result.solutions, 1):
        bindings = _bindings_str(sol.substitutions)
        lines.append(f"  {i}. {bindings}")
    return "\n".join(lines)


def format_reason_verbose(result: ReasonResult, max_proofs: int = 2) -> str:
    """Full reason result including the Prolog derivation chain per solution."""
    if result.error:
        return f"Error: {result.error}"
    if not result.solutions:
        return "No solutions found. The query does not hold."
    lines = [f"Query: {result.query}", f"Found {len(result.solutions)} solution(s) in {result.elapsed_ms:.1f}ms:"]
    lines.extend(_proofs_block(result.solutions, max_proofs))
    return "\n".join(lines)


def format_diagnose_result(result: DiagnosisResult) -> str:
    """Format DiagnosisResult into a concise string."""
    if result.error:
        return f"Error: {result.error}"
    lines = [
        f"Query: {result.query} (mode: {result.mode})",
        f"Holds: {'YES' if result.holds else 'NO'}",
    ]
    if result.findings:
        lines.append("Findings:")
        for f in result.findings:
            lines.append(f"  - [{f.type}] {f.predicate}: {f.detail}")
    lines.append(f"Conclusion: {result.conclusion}")
    return "\n".join(lines)


def format_diagnose_verbose(result: DiagnosisResult) -> str:
    """Full diagnose result including the proof tree."""
    if result.error:
        return f"Error: {result.error}"
    lines = [
        f"Query: {result.query} (mode: {result.mode})",
        f"Holds: {'YES' if result.holds else 'NO'}",
    ]
    if result.findings:
        lines.append("Findings:")
        for f in result.findings:
            lines.append(f"  - [{f.type}] {f.predicate}: {f.detail}")
    if result.proof:
        lines.append("Proof tree:")
        lines.extend(format_proof_tree(result.proof))
    lines.append(f"Conclusion: {result.conclusion}")
    return "\n".join(lines)


def format_what_if_result(result: WhatIfResult) -> str:
    """Format WhatIfResult into a concise string."""
    if result.error:
        return f"Error: {result.error}"
    lines = [
        f"Query: {result.query}",
        f"Modifications: {result.modifications}",
        f"Before: {result.before_count} solution(s), After: {result.after_count} solution(s)",
        f"Delta: {result.delta}",
        f"Conclusion: {result.conclusion}",
    ]
    return "\n".join(lines)


def format_what_if_verbose(result: WhatIfResult, max_proofs: int = 2) -> str:
    """Full what_if result including the derivations after modification."""
    if result.error:
        return f"Error: {result.error}"
    lines = [
        f"Query: {result.query}",
        f"Modifications: {result.modifications}",
        f"Before: {result.before_count} solution(s), After: {result.after_count} solution(s)",
        f"Delta: {result.delta}",
    ]
    if result.solutions_after:
        lines.append("Derivations after modification:")
        lines.extend(_proofs_block(result.solutions_after, max_proofs))
    lines.append(f"Conclusion: {result.conclusion}")
    return "\n".join(lines)


def format_check_kb_result(result: KBCheckResult) -> str:
    """Format KBCheckResult into a concise string."""
    lines = [
        f"Valid: {result.valid}",
        f"Facts: {result.facts_count}, Rules: {result.rules_count}, Predicates: {result.predicates_count}",
    ]
    if result.errors:
        lines.append("Errors:")
        for e in result.errors:
            lines.append(f"  - [{e.type}] {e.message}")
    if result.warnings:
        lines.append("Warnings:")
        for w in result.warnings:
            lines.append(f"  - [{w.type}] {w.message}")
    return "\n".join(lines)


def execute_tool(tool_name: str, arguments: dict, knowledge: str) -> tuple[str, str]:
    """Execute a Euclid-MCP tool.

    Returns a tuple (concise, verbose): the concise string is fed back to the
    LLM, the verbose string (with proof trees) is shown in --verbose mode.
    """
    if tool_name == "reason":
        result = reason(knowledge=knowledge, query=arguments.get("query", ""), max_solutions=50, max_depth=30)
        return format_reason_result(result), format_reason_verbose(result)

    elif tool_name == "diagnose":
        result = diagnose(
            knowledge=knowledge,
            query=arguments.get("query", ""),
            mode=arguments.get("mode", "why"),
            max_solutions=50,
            max_depth=30,
        )
        return format_diagnose_result(result), format_diagnose_verbose(result)

    elif tool_name == "what_if":
        result = what_if(
            base_knowledge=knowledge,
            modifications=arguments.get("modifications", ""),
            query=arguments.get("query", ""),
            max_solutions=50,
            max_depth=30,
        )
        return format_what_if_result(result), format_what_if_verbose(result)

    elif tool_name == "check_kb":
        result = check_kb(knowledge=knowledge)
        return format_check_kb_result(result), format_check_kb_result(result)

    return f"Unknown tool: {tool_name}", f"Unknown tool: {tool_name}"
