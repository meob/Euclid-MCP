"""Diagnostics provider: converts KB errors into LSP Diagnostic objects."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lsprotocol import types

if TYPE_CHECKING:
    from euclid_lsp.positioned_parser import PositionedKB


_SEVERITY_MAP = {
    "parse_error": types.DiagnosticSeverity.Error,
    "undefined_predicate": types.DiagnosticSeverity.Error,
    "circular_rule": types.DiagnosticSeverity.Error,
    "syntax_error": types.DiagnosticSeverity.Error,
    "duplicate_fact": types.DiagnosticSeverity.Warning,
    "duplicate_rule_id": types.DiagnosticSeverity.Warning,
    "inconsistent_arity": types.DiagnosticSeverity.Warning,
    "unsafe_negation": types.DiagnosticSeverity.Information,
}


def compute_diagnostics(
    pkb: PositionedKB,
    errors: list[dict],
    warnings: list[dict],
) -> list[types.Diagnostic]:
    """Convert KB check results into LSP diagnostics with source locations."""
    diagnostics: list[types.Diagnostic] = []

    for err in errors:
        severity = _SEVERITY_MAP.get(err.get("type", ""), types.DiagnosticSeverity.Error)
        line = err.get("line")
        if line is not None:
            start_line = max(0, line - 1)
            start_char = 0
            end_line = start_line
            end_char = 0
        else:
            # Try to locate by predicate name
            predicate = err.get("predicate", "")
            loc = _locate_predicate(pkb, predicate)
            if loc:
                start_line, start_char, end_line, end_char = loc
            else:
                start_line, start_char, end_line, end_char = 0, 0, 0, 0

        diagnostics.append(types.Diagnostic(
            range=types.Range(
                start=types.Position(line=start_line, character=start_char),
                end=types.Position(line=end_line, character=end_char),
            ),
            message=err.get("message", "Unknown error"),
            severity=severity,
            source="euclid-lsp",
        ))

    for warn in warnings:
        severity = _SEVERITY_MAP.get(warn.get("type", ""), types.DiagnosticSeverity.Warning)
        predicate = warn.get("predicate", "")
        loc = _locate_predicate(pkb, predicate)
        if loc:
            start_line, start_char, end_line, end_char = loc
        else:
            start_line, start_char, end_line, end_char = 0, 0, 0, 0

        diagnostics.append(types.Diagnostic(
            range=types.Range(
                start=types.Position(line=start_line, character=start_char),
                end=types.Position(line=end_line, character=end_char),
            ),
            message=warn.get("message", "Unknown warning"),
            severity=severity,
            source="euclid-lsp",
        ))

    return diagnostics


def _locate_predicate(
    pkb: PositionedKB, predicate: str
) -> tuple[int, int, int, int] | None:
    """Find the source location of a predicate in the positioned KB."""
    if not predicate:
        return None

    name = predicate.split("/")[0] if "/" in predicate else predicate

    for item in pkb.items:
        if item.kind == "fact" and item.text.startswith(name + "("):
            return (item.start_line, item.start_col, item.end_line, item.end_col)
        if item.kind == "rule" and item.head and item.head.startswith(name + "("):
            return (item.start_line, item.start_col, item.end_line, item.end_col)
        if item.kind == "query" and name in item.text:
            return (item.start_line, item.start_col, item.end_line, item.end_col)

    return None
