"""Tests for the diagnostics provider."""

from euclid_lsp.diagnostics import compute_diagnostics
from euclid_lsp.positioned_parser import parse_positioned


class TestDiagnostics:
    def test_no_errors(self):
        text = "parent(tom, bob)"
        pkb = parse_positioned(text)
        diagnostics = compute_diagnostics(pkb, [], [])
        assert diagnostics == []

    def test_error_diagnostic(self):
        text = "parent(tom, bob)"
        pkb = parse_positioned(text)
        errors = [
            {
                "type": "undefined_predicate",
                "message": "Rule body references undefined predicate 'foo/1'",
                "predicate": "foo/1",
            }
        ]
        diagnostics = compute_diagnostics(pkb, errors, [])
        assert len(diagnostics) == 1
        assert diagnostics[0].severity == 1  # Error

    def test_warning_diagnostic(self):
        text = "parent(tom, bob)"
        pkb = parse_positioned(text)
        warnings = [
            {
                "type": "duplicate_fact",
                "message": "Duplicate fact: parent(tom, bob)",
                "predicate": "parent",
            }
        ]
        diagnostics = compute_diagnostics(pkb, [], warnings)
        assert len(diagnostics) == 1
        assert diagnostics[0].severity == 2  # Warning

    def test_source_is_euclid_lsp(self):
        pkb = parse_positioned("")
        diagnostics = compute_diagnostics(pkb, [{"type": "parse_error", "message": "err"}], [])
        assert diagnostics[0].source == "euclid-lsp"
