"""Hover provider: shows predicate info on hover."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lsprotocol import types

if TYPE_CHECKING:
    from euclid_lsp.positioned_parser import PositionedKB


def compute_hover(
    pkb: PositionedKB,
    line: int,
    col: int,
) -> types.Hover | None:
    """Return hover information for the predicate at the given position."""
    # Find the item at this line
    item = _find_item_at(pkb, line, col)
    if not item:
        return None

    # Extract the predicate name under cursor
    pred_name = _extract_pred_at_col(item.text, col)
    if not pred_name:
        return None

    # Build hover content
    lines: list[str] = []
    lines.append(f"**{pred_name}** — Euclid-IR predicate")
    lines.append("")

    # Find all occurrences in the KB
    facts = [
        i for i in pkb.items
        if i.kind == "fact" and i.text.startswith(pred_name + "(")
    ]
    rules = [
        i for i in pkb.items
        if i.kind == "rule" and i.head and i.head.startswith(pred_name + "(")
    ]

    if facts:
        lines.append(f"Facts: {len(facts)}")
        for f in facts[:3]:
            lines.append(f"  `{f.text}`")
        if len(facts) > 3:
            lines.append(f"  ... and {len(facts) - 3} more")

    if rules:
        lines.append(f"Rules: {len(rules)}")
        for r in rules[:3]:
            lines.append(f"  `{r.text}`")
            if r.rule_id:
                lines.append(f"  Rule ID: `{r.rule_id}`")
        if len(rules) > 3:
            lines.append(f"  ... and {len(rules) - 3} more")

    if not facts and not rules:
        lines.append("No definitions found in this KB.")

    return types.Hover(
        contents=types.MarkupContent(
            kind=types.MarkupKind.Markdown,
            value="\n".join(lines),
        ),
        range=types.Range(
            start=types.Position(line=line, character=col),
            end=types.Position(line=line, character=col + len(pred_name)),
        ),
    )


def _find_item_at(pkb: PositionedKB, line: int, col: int):
    """Find the LocatedItem that contains the given position."""
    for item in pkb.items:
        if item.start_line <= line <= item.end_line:
            return item
    return None


def _extract_pred_at_col(text: str, col: int) -> str | None:
    """Extract the predicate name at the given column in a text string."""
    # Find word boundary around col
    start = min(col, len(text) - 1) if text else 0
    end = min(col, len(text))
    while start > 0 and (text[start - 1].isalnum() or text[start - 1] == "_"):
        start -= 1
    while end < len(text) and (text[end].isalnum() or text[end] == "_"):
        end += 1

    word = text[start:end]
    if not word or not word[0].isalpha():
        return None

    # Check if it's followed by '(' to confirm it's a predicate
    after = text[end:].lstrip()
    if after.startswith("("):
        return word

    return None
