"""Unit tests for the explain tool: deterministic proof-tree → natural language."""

from euclid_mcp.server import explain


class TestExplain:
    def test_single_fact(self):
        r = explain("human(socrates)\n? human(socrates)")
        assert r.error is None
        assert r.query == "human(socrates)"
        assert len(r.explanations) == 1
        steps = r.explanations[0].steps
        assert len(steps) == 1
        assert "human(socrates)" in steps[0]
        assert "fact" in steps[0].lower()

    def test_variables_rule(self):
        r = explain("human(socrates)\nmortal($x) IF human($x)\n? mortal($who)")
        assert r.error is None
        assert len(r.explanations) == 1
        exp = r.explanations[0]
        assert exp.substitutions["who"] == "socrates"
        assert len(exp.steps) == 2
        assert "mortal(socrates)" in exp.steps[0]
        assert "human(socrates)" in exp.steps[1]

    def test_multi_hop(self):
        kb = (
            "parent(tom, bob)\n"
            "parent(bob, ann)\n"
            "ancestor($x, $y) IF parent($x, $y)\n"
            "ancestor($x, $y) IF parent($x, $z) AND ancestor($z, $y)\n"
            "? ancestor(tom, ann)"
        )
        r = explain(kb)
        assert r.error is None
        assert len(r.explanations) == 1
        steps = r.explanations[0].steps
        assert len(steps) >= 4
        assert any("ancestor(tom,ann)" in s for s in steps)
        assert any("ancestor(bob,ann)" in s for s in steps)
        assert any("parent(tom,bob)" in s and "ancestor(bob,ann)" in s for s in steps)

    def test_negation(self):
        kb = "active(alice)\nblocked($u) IF NOT active($u)\n? blocked(bob)"
        r = explain(kb)
        assert r.error is None
        assert len(r.explanations) == 1
        steps = r.explanations[0].steps
        assert len(steps) == 2
        assert "NOT active(bob)" in steps[0]
        assert "active(bob)" in steps[1]
        assert "not provable" in steps[1]

    def test_arithmetic_comparison(self):
        kb = (
            "last_login(user_a, 100)\n"
            "stale($u) IF last_login($u, $days) AND $days > 90\n"
            "? stale(user_a)"
        )
        r = explain(kb)
        assert r.error is None
        assert len(r.explanations) == 1
        steps = r.explanations[0].steps
        assert len(steps) == 3
        assert any("arithmetic" in s.lower() for s in steps)

    def test_zero_solutions(self):
        r = explain("human(socrates)\n? human(plato)")
        assert r.error is None
        assert len(r.explanations) == 0

    def test_cites_rule_id(self):
        kb = (
            "human(socrates)\n"
            "mortal($x) IF human($x)  # rule: RBAC-0043\n"
            "? mortal($who)"
        )
        r = explain(kb)
        assert r.error is None
        steps = r.explanations[0].steps
        assert any("rule RBAC-0043" in s for s in steps)

    def test_no_rule_id(self):
        kb = "human(socrates)\nmortal($x) IF human($x)\n? mortal($who)"
        r = explain(kb)
        assert r.error is None
        steps = r.explanations[0].steps
        assert any("by a rule from" in s for s in steps)
        assert not any("rule_id" in s for s in steps)

    def test_multi_hop_cites_ids_inner_and_outer(self):
        kb = (
            "parent(tom, bob)\n"
            "parent(bob, ann)\n"
            "ancestor($x, $y) IF parent($x, $y)  # rule: BASE-1\n"
            "ancestor($x, $y) IF parent($x, $z) AND ancestor($z, $y)  # rule: REC-2\n"
            "? ancestor(tom, ann)"
        )
        r = explain(kb)
        assert r.error is None
        steps = r.explanations[0].steps
        assert any("rule REC-2" in s for s in steps)
        assert any("rule BASE-1" in s for s in steps)

    def test_no_query_error(self):
        r = explain("human(socrates)")
        assert r.error is not None
        assert "No query" in r.error
        assert len(r.explanations) == 0

    def test_max_solutions(self):
        kb = (
            "parent(tom, bob)\nparent(tom, liz)\nparent(tom, ann)\n"
            "? parent(tom, $who)"
        )
        r = explain(kb, max_solutions=2)
        assert r.error is None
        assert len(r.explanations) == 2
