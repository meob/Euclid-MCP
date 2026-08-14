"""Deterministic proof-tree → explanation.

Walks a ProofNode (fact / rule / and / neg / true) and produces an ordered
list of reasoning steps. Two representations are derived from the same walk:

* ``explain_solution_typed`` → ``list[ExplainStep]``: language-independent
  typed steps (kind + goal + rule_id + body conjuncts). Studio renders these
  with localized templates.
* ``explain_solution`` → ``list[str]``: the English natural-language steps,
  rendered from the typed steps (backward compatible).

Rule IDs are cited when present, so explanations stay auditable without any
LLM involvement.
"""

import re

from .models import ExplainStep, ProofNode, Solution

_RULE_ID_MARKER = re.compile(r"euclid_rule_id\('((?:[^']|'')*)'\)\s*,?\s*")


def explain_solution(solution: Solution) -> list[str]:
    """Return the natural-language reasoning steps for one solution."""
    return [_render_step(step) for step in explain_solution_typed(solution)]


def explain_solution_typed(solution: Solution) -> list[ExplainStep]:
    """Return the language-independent typed reasoning steps for one solution."""
    return _explain_node(solution.proof)


def _explain_node(node: ProofNode) -> list[ExplainStep]:
    node_type = node.type

    if node_type == "fact":
        return [ExplainStep(kind="fact", goal=node.goal)]

    if node_type == "rule":
        steps = [
            ExplainStep(
                kind="rule",
                goal=node.goal,
                rule_id=node.rule_id,
                body=_humanize_parts(node.body or ""),
            )
        ]
        if node.subproof:
            steps.extend(_explain_node(node.subproof))
        return steps

    if node_type == "and":
        and_steps: list[ExplainStep] = []
        if node.left:
            and_steps.extend(_explain_node(node.left))
        if node.right:
            and_steps.extend(_explain_node(node.right))
        return and_steps

    if node_type == "neg":
        return [ExplainStep(kind="neg", goal=node.goal)]

    if node_type == "true":
        return [ExplainStep(kind="true")]

    return [ExplainStep(kind="unknown", goal=node_type)]


def _render_step(step: ExplainStep) -> str:
    """Render one typed step as English, matching the pre-C5 strings exactly."""
    if step.kind == "fact":
        return f"{step.goal} is asserted as a fact in the knowledge base."

    if step.kind == "rule":
        source = f"rule {step.rule_id}" if step.rule_id else "a rule"
        body = " and ".join(step.body)
        return f"{step.goal} is derived by {source} from: {body}."

    if step.kind == "neg":
        return (
            f"{step.goal} is not provable in the knowledge base "
            "(verified by negation as failure)."
        )

    if step.kind == "true":
        return "The arithmetic condition holds."

    return f"Unexpected proof node type: {step.goal}."


def _humanize_parts(text: str) -> list[str]:
    """Split a Prolog rule body into readable conjuncts.

    'parent(tom,bob),ancestor(bob,ann)'  →  ['parent(tom,bob)', 'ancestor(bob,ann)']
    '\\+active(bob)'                       →  ['NOT active(bob)']
    The internal euclid_rule_id('X') marker is stripped (the rule is already
    cited in the step). Commas inside parentheses are preserved (they are term
    arguments, not conjunction separators).
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
    return [part for part in parts if part]
