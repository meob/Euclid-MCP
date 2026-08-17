"""Tests for the autocomplete provider."""

from euclid_lsp.autocomplete import compute_completions
from euclid_lsp.positioned_parser import parse_positioned


class TestAutocomplete:
    def test_keyword_completions(self):
        pkb = parse_positioned("")
        items = compute_completions(pkb, "if ", 3)
        labels = [i.label for i in items]
        assert "if" in labels
        assert "and" in labels
        assert "not" in labels

    def test_predicate_completions(self):
        pkb = parse_positioned("parent(tom, bob)\nancestor($x, $y) IF parent($x, $y)")
        items = compute_completions(pkb, "", 0)
        labels = [i.label for i in items]
        assert "parent" in labels
        assert "ancestor" in labels

    def test_arithmetic_completions(self):
        pkb = parse_positioned("")
        items = compute_completions(pkb, ">=", 2)
        labels = [i.label for i in items]
        assert ">=" in labels

    def test_prefix_filtering(self):
        pkb = parse_positioned("parent(tom, bob)\nancestor($x, $y) IF parent($x, $y)")
        items = compute_completions(pkb, "par", 3)
        labels = [i.label for i in items]
        assert "parent" in labels
        assert "ancestor" not in labels
