"""Static analysis for Euclid-IR rules.

Detects unsafe negation: variables inside NOT that are not bound
by previous positive goals in the same rule body.
"""

import re


def lint_rule(rule: str) -> list[str]:
    """Check a rule for unsafe negation.

    Returns a list of warning messages. Empty list means no issues.
    """
    warnings: list[str] = []

    # Split rule into head and body
    parts = re.split(r"\s+IF\s+", rule, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) < 2:
        return warnings
    body = parts[1]

    # Split body on AND
    goals = re.split(r"\s+AND\s+", body, flags=re.IGNORECASE)

    bound_vars: set[str] = set()
    for goal in goals:
        goal = goal.strip()
        if not goal:
            continue

        # Check if this is a NOT goal
        if re.match(r"\bNOT\b\s+", goal, re.IGNORECASE):
            neg_content = re.sub(
                r"\bNOT\b\s+", "", goal, count=1, flags=re.IGNORECASE
            ).strip()
            # Extract variables from the negated goal
            neg_vars = set(re.findall(r"\$([a-z][a-zA-Z0-9_]*)", neg_content))
            unbound = neg_vars - bound_vars
            if unbound:
                warnings.append(
                    f"Unsafe negation: variables {sorted(unbound)} in NOT "
                    f"are not bound by previous positive goals"
                )
        else:
            # Positive goal: extract variables and add to bound set
            bound_vars.update(re.findall(r"\$([a-z][a-zA-Z0-9_]*)", goal))

    return warnings
