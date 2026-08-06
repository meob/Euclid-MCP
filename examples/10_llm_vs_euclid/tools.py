"""
Tools definition for Ollama + executor functions that call Euclid-MCP.
"""

import sys
from pathlib import Path

# Add project root to path
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from euclid_mcp.models import DiagnosisResult, KBCheckResult, ReasonResult, WhatIfResult
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
                            "can_deploy($who, production) "
                            "stale_access($who) "
                            "resource($name, production, not_encrypted, _, _, _)"
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
                        "description": "The query to diagnose, e.g. user_has_permission(intern_01, deploy_code)",
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
                            "Example: '+ has_role(alice, sysadmin)' or '- has_role(bob, intern)'"
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


def format_reason_result(result: ReasonResult) -> str:
    """Format ReasonResult into a concise string for LLM consumption."""
    if result.error:
        return f"Error: {result.error}"
    if not result.solutions:
        return "No solutions found. The query does not hold."
    lines = [f"Query: {result.query}", f"Found {len(result.solutions)} solution(s) in {result.elapsed_ms:.1f}ms:"]
    for i, sol in enumerate(result.solutions, 1):
        bindings = ", ".join(f"{k}={v}" for k, v in sol.substitutions.items()) if sol.substitutions else "{}"
        lines.append(f"  {i}. {bindings}")
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


def execute_tool(tool_name: str, arguments: dict, knowledge: str) -> str:
    """Execute a Euclid-MCP tool and return formatted result string."""
    if tool_name == "reason":
        result = reason(knowledge=knowledge, query=arguments.get("query", ""), max_solutions=50, max_depth=30)
        return format_reason_result(result)

    elif tool_name == "diagnose":
        result = diagnose(
            knowledge=knowledge,
            query=arguments.get("query", ""),
            mode=arguments.get("mode", "why"),
            max_solutions=50,
            max_depth=30,
        )
        return format_diagnose_result(result)

    elif tool_name == "what_if":
        result = what_if(
            base_knowledge=knowledge,
            modifications=arguments.get("modifications", ""),
            query=arguments.get("query", ""),
            max_solutions=50,
            max_depth=30,
        )
        return format_what_if_result(result)

    elif tool_name == "check_kb":
        result = check_kb(knowledge=knowledge)
        return format_check_kb_result(result)

    return f"Unknown tool: {tool_name}"
