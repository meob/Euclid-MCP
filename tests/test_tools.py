"""Unit tests for all 4 MCP tools: reason, diagnose, what_if, check_kb."""

import pytest

from euclid_mcp.server import check_kb, diagnose, reason, what_if

# =============================================================================
# reason
# =============================================================================


class TestReason:
    def test_happy_path(self):
        r = reason("human(socrates)\nmortal($x) IF human($x)\n? mortal($who)")
        assert r.error is None
        assert len(r.solutions) == 1
        assert r.solutions[0].substitutions["who"] == "socrates"
        assert r.solutions[0].proof.type in ("rule", "fact")

    def test_multiple_solutions(self):
        r = reason(
            "parent(tom, bob)\nparent(tom, liz)\n? parent(tom, $who)",
            max_solutions=10,
        )
        assert r.error is None
        assert len(r.solutions) == 2
        names = {s.substitutions["who"] for s in r.solutions}
        assert names == {"bob", "liz"}

    def test_no_query(self):
        r = reason("human(socrates)")
        assert r.error is not None
        assert "No query" in r.error

    def test_override_query(self):
        r = reason(
            "human(socrates)\nhuman(plato)\n? human($who)",
            query="human(plato)",
        )
        assert r.error is None
        assert len(r.solutions) >= 1

    def test_max_solutions(self):
        r = reason(
            "parent(tom, bob)\nparent(tom, liz)\nparent(tom, ann)\n? parent(tom, $who)",
            max_solutions=2,
        )
        assert r.error is None
        assert len(r.solutions) == 2

    def test_empty_kb(self):
        r = reason("? fact(x)")
        assert r.error is None
        assert len(r.solutions) == 0

    def test_no_query_even_with_garbage(self):
        r = reason("INVALID SYNTAX {{{{")
        assert r.error is not None
        assert "No query" in r.error

    def test_proof_tree_structure(self):
        r = reason("human(socrates)\nmortal($x) IF human($x)\n? mortal($who)")
        assert r.error is None
        proof = r.solutions[0].proof
        assert proof.goal is not None
        assert "mortal" in proof.goal


# =============================================================================
# diagnose
# =============================================================================


class TestDiagnose:
    def test_why_holds(self):
        r = diagnose(
            "human(socrates)\nmortal($x) IF human($x)",
            query="mortal(socrates)",
            mode="why",
        )
        assert r.error is None
        assert r.holds is True
        assert "HOLDS" in r.conclusion

    def test_why_fails(self):
        r = diagnose(
            "human(socrates)\nmortal($x) IF human($x)",
            query="mortal(plato)",
            mode="why",
        )
        assert r.error is None
        assert r.holds is False
        assert "NOT" in r.conclusion or "does not" in r.conclusion.lower()

    def test_why_not_fails(self):
        r = diagnose(
            "human(socrates)\nmortal($x) IF human($x)",
            query="mortal(plato)",
            mode="why_not",
        )
        assert r.error is None
        assert r.holds is False
        assert len(r.conclusion) > 0

    def test_why_not_holds(self):
        r = diagnose(
            "human(socrates)\nmortal($x) IF human($x)",
            query="mortal(socrates)",
            mode="why_not",
        )
        assert r.error is None
        assert r.holds is True
        assert "holds" in r.conclusion.lower()

    def test_what_needs(self):
        r = diagnose(
            "human(socrates)\nmortal($x) IF human($x)",
            query="mortal(plato)",
            mode="what_needs",
        )
        assert r.error is None
        assert r.holds is False
        assert len(r.conclusion) > 0

    def test_invalid_mode(self):
        r = diagnose(
            "human(socrates)",
            query="human(socrates)",
            mode="bogus",
        )
        assert r.error is not None
        assert "Invalid mode" in r.error

    def test_missing_predicate(self):
        r = diagnose(
            "human(socrates)",
            query="ghost($x)",
            mode="why",
        )
        assert r.error is None
        assert r.holds is False
        assert len(r.findings) > 0
        assert any(f.type == "missing_fact" for f in r.findings)

    def test_populates_solutions(self):
        r = diagnose(
            "human(socrates)\nmortal($x) IF human($x)",
            query="mortal(socrates)",
            mode="why",
        )
        assert r.error is None
        assert len(r.solutions) >= 1
        assert r.proof is not None


# =============================================================================
# what_if
# =============================================================================


class TestWhatIf:
    def test_add_fact(self):
        base = "human(socrates)\nmortal($x) IF human($x)"
        r = what_if(base, "+ human(plato)", "mortal($who)")
        assert r.error is None
        assert r.after_count > r.before_count
        assert r.delta == "more"
        assert "ENABLES" in r.conclusion or "increased" in r.conclusion.lower()

    def test_remove_fact(self):
        base = "human(socrates)\nhuman(plato)\nmortal($x) IF human($x)"
        r = what_if(base, "- human(socrates)", "mortal($who)")
        assert r.error is None
        assert r.after_count < r.before_count
        assert r.delta == "less"

    def test_add_and_remove(self):
        base = "human(socrates)\nhuman(plato)\nmortal($x) IF human($x)"
        r = what_if(
            base,
            "- human(socrates)\n+ human(alcibiades)",
            "mortal($who)",
        )
        assert r.error is None
        assert r.after_count == r.before_count
        assert r.delta == "same"

    def test_and_separated_facts(self):
        base = "human(socrates)\nmortal($x) IF human($x)"
        r = what_if(base, "+ human(plato) AND human(alcibiades)", "mortal($who)")
        assert r.error is None
        assert r.after_count == 3

    def test_no_modifications(self):
        r = what_if("human(socrates)", "", "human(socrates)")
        assert r.error is not None
        assert "No modifications" in r.error

    def test_add_then_remove_same_fact(self):
        base = "human(socrates)\nmortal($x) IF human($x)"
        r = what_if(base, "+ human(plato)\n- human(plato)", "mortal($who)")
        assert r.error is None
        assert r.after_count >= r.before_count

    def test_modifications_label(self):
        base = "human(socrates)\nmortal($x) IF human($x)"
        r = what_if(base, "+ human(plato)", "mortal($who)")
        assert r.error is None
        assert "+ human(plato)" in r.modifications

    def test_solutions_before_and_after(self):
        base = "human(socrates)\nmortal($x) IF human($x)"
        r = what_if(base, "+ human(plato)", "mortal($who)")
        assert r.error is None
        assert len(r.solutions_before) >= 1
        assert len(r.solutions_after) >= 2


# =============================================================================
# check_kb
# =============================================================================


class TestCheckKB:
    def test_valid_kb(self):
        r = check_kb("human(socrates)\nmortal($x) IF human($x)\n? mortal($who)")
        assert r.valid is True
        assert len(r.errors) == 0
        assert r.facts_count == 1
        assert r.rules_count == 1

    def test_duplicates(self):
        r = check_kb("human(socrates)\nhuman(socrates)")
        assert r.valid is True
        assert len(r.warnings) >= 1
        assert any(w.type == "duplicate_fact" for w in r.warnings)

    def test_undefined_predicate(self):
        r = check_kb("mortal($x) IF ghost($x)")
        assert r.valid is False
        assert any(e.type == "undefined_predicate" for e in r.errors)

    def test_circular_rule(self):
        r = check_kb("ancestor($x, $y) IF ancestor($x, $z) AND ancestor($z, $y)")
        assert r.valid is False
        assert any(e.type == "circular_rule" for e in r.errors)

    def test_garbage_input_no_errors(self):
        r = check_kb("??? INVALID @#$%")
        assert r.valid is True
        assert r.facts_count == 0
        assert r.rules_count == 0

    def test_counts(self):
        r = check_kb(
            "a(1)\nb(2)\nc(3)\nr($x) IF a($x)\ns($x) IF b($x)\n? r($who)"
        )
        assert r.facts_count == 3
        assert r.rules_count == 2
        assert r.predicates_count == 5  # a, b, c, r, s

    def test_undefined_query_predicate(self):
        r = check_kb("human(socrates)\n? ghost($who)")
        assert r.valid is False
        assert any(
            e.type == "undefined_predicate" and "ghost" in e.message for e in r.errors
        )

    def test_valid_complex_kb(self):
        kb = """
parent(tom, bob)
parent(bob, ann)
parent(tom, liz)
ancestor($x, $y) IF parent($x, $y)
ancestor($x, $y) IF parent($x, $z) AND ancestor($z, $y)
? ancestor(tom, $who)
"""
        r = check_kb(kb)
        assert r.valid is True
        assert len(r.errors) == 0
        assert r.facts_count == 3
        assert r.rules_count == 2
