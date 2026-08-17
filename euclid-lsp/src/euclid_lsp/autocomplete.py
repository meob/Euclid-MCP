"""Autocomplete provider: suggests predicate names, keywords, and built-ins."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from lsprotocol import types

if TYPE_CHECKING:
    from euclid_lsp.positioned_parser import PositionedKB

_KEYWORDS = [
    "if", "and", "not", "is",
]

_ARITH_OPERATORS = [
    ">", ">=", "<", "<=", "==", "!=",
]

_BUILTINS = [
    "true", "false",
]


def compute_completions(
    pkb: PositionedKB,
    line: str,
    col: int,
) -> list[types.CompletionItem]:
    """Generate completion items based on current document state."""
    items: list[types.CompletionItem] = []

    # Extract defined predicate names from the KB
    defined_preds: set[str] = set()
    for item in pkb.items:
        if item.kind == "fact":
            m = re.match(r"([a-z_]\w*)", item.text)
            if m:
                defined_preds.add(m.group(1))
        elif item.kind == "rule" and item.head:
            m = re.match(r"([a-z_]\w*)", item.head)
            if m:
                defined_preds.add(m.group(1))

    # Check what's being typed (word prefix)
    prefix = _get_word_prefix(line, col)

    # Predicate completions
    for pred in sorted(defined_preds):
        if not prefix or pred.startswith(prefix):
            items.append(types.CompletionItem(
                label=pred,
                kind=types.CompletionItemKind.Function,
                detail="predicate",
                insert_text=pred,
            ))

    # Keyword completions
    for kw in _KEYWORDS:
        if not prefix or kw.startswith(prefix):
            items.append(types.CompletionItem(
                label=kw,
                kind=types.CompletionItemKind.Keyword,
                detail="keyword",
                insert_text=kw,
            ))

    # Arithmetic operators
    for op in _ARITH_OPERATORS:
        if not prefix or op.startswith(prefix):
            items.append(types.CompletionItem(
                label=op,
                kind=types.CompletionItemKind.Operator,
                detail="operator",
                insert_text=op,
            ))

    # Built-ins
    for b in _BUILTINS:
        if not prefix or b.startswith(prefix):
            items.append(types.CompletionItem(
                label=b,
                kind=types.CompletionItemKind.Value,
                detail="builtin",
                insert_text=b,
            ))

    # Snippet: rule template
    if not prefix or "if".startswith(prefix):
        items.append(types.CompletionItem(
            label="rule template",
            kind=types.CompletionItemKind.Snippet,
            detail="multi-line rule",
            insert_text="${1:predicate}(${2:args}) IF\n    ${3:body_goal} AND\n    ${4:body_goal}",
            insert_text_format=types.InsertTextFormat.Snippet,
        ))

    return items


def _get_word_prefix(line: str, col: int) -> str:
    """Extract the word being typed at the cursor position."""
    text_before = line[:col]
    m = re.search(r"[a-z_]\w*$", text_before)
    return m.group(0) if m else ""
