"""Tests for the hover provider."""

from euclid_lsp.hover import compute_hover
from euclid_lsp.positioned_parser import parse_positioned


class TestHover:
    def test_hover_on_predicate(self):
        text = "parent(tom, bob)\nancestor($x, $y) IF parent($x, $y)"
        pkb = parse_positioned(text)
        # Hover on line 0, col 0 (start of "parent")
        result = compute_hover(pkb, 0, 0)
        assert result is not None
        assert "parent" in result.contents.value

    def test_hover_on_unknown(self):
        pkb = parse_positioned("parent(tom, bob)")
        # Hover on a comment line (no predicate)
        result = compute_hover(pkb, 0, 100)
        assert result is None

    def test_hover_shows_facts_and_rules(self):
        text = "parent(tom, bob)\nparent(bob, ann)\nancestor($x, $y) IF parent($x, $y)"
        pkb = parse_positioned(text)
        result = compute_hover(pkb, 0, 0)
        assert result is not None
        assert "Facts: 2" in result.contents.value

    def test_hover_in_rule_head(self):
        text = "ancestor($x, $y) IF parent($x, $y)"
        pkb = parse_positioned(text)
        result = compute_hover(pkb, 0, 0)
        assert result is not None
        assert "ancestor" in result.contents.value
        assert "Rules: 1" in result.contents.value
