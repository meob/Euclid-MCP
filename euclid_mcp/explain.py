"""Deterministic proof-tree → natural-language explanation.

Walks a ProofNode (fact / rule / and / neg / true) and produces an ordered
list of natural-language reasoning steps. Rule IDs are cited when present,
so explanations stay auditable without any LLM involvement.
"""

import re

from .models import ProofNode, Solution

_RULE_ID_MARKER = re.compile(r"euclid_rule_id\('((?:[^']|'')*)'\)\s*,?\s*")


def explain_solution(solution: Solution) -> list[str]:
    """Return the natural-language reasoning steps for one solution."""
    return _explain_node(solution.proof)


def _explain_node(node: ProofNode) -> list[str]:
    node_type = node.type

    if node_type == "fact":
        return [f"{node.goal} is asserted as a fact in the knowledge base."]

    if node_type == "rule":
        source = f"rule {node.rule_id}" if node.rule_id else "a rule"
        body = _humanize_body(node.body or "")
        steps = [f"{node.goal} is derived by {source} from: {body}."]
        if node.subproof:
            steps.extend(_explain_node(node.subproof))
        return steps

    if node_type == "and":
        and_steps: list[str] = []
        if node.left:
            and_steps.extend(_explain_node(node.left))
        if node.right:
            and_steps.extend(_explain_node(node.right))
        return and_steps

    if node_type == "neg":
        return [
            f"{node.goal} is not provable in the knowledge base "
            "(verified by negation as failure)."
        ]

    if node_type == "true":
        return ["The arithmetic condition holds."]

    return [f"Unexpected proof node type: {node_type}."]


def _humanize_body(text: str) -> str:
    """Turn a Prolog rule body into readable conjunctive English.

    'parent(tom,bob),ancestor(bob,ann)'  →  'parent(tom,bob) and ancestor(bob,ann)'
    '\\+active(bob)'                       →  'NOT active(bob)'
    The internal euclid_rule_id('X') marker is stripped (the rule is already
    cited in the step text). Commas inside parentheses are preserved (they
    are term arguments, not conjunction separators).
    """
    text = _RULE_ID_MARKER.sub("", text)
    text = text.replace("\\+", "NOT ")
    depth = 0
    parts: list[str] = []
    current: list[str] = []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(ch)
    parts.append("".join(current).strip())
    return " and ".join(p for p in parts if p)
