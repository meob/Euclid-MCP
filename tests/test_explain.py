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


class TestExplainStructured:
    """C5: language-independent typed steps (structured_steps)."""

    def test_single_fact_kind(self):
        r = explain("human(socrates)\n? human(socrates)")
        steps = r.explanations[0].structured_steps
        assert len(steps) == 1
        step = steps[0]
        assert step.kind == "fact"
        assert step.goal == "human(socrates)"
        assert step.rule_id is None
        assert step.body == []

    def test_rule_step_carries_rule_id_and_body(self):
        kb = (
            "human(socrates)\n"
            "mortal($x) IF human($x)  # rule: RBAC-0043\n"
            "? mortal($who)"
        )
        r = explain(kb)
        steps = r.explanations[0].structured_steps
        assert len(steps) == 2
        rule_step = steps[0]
        assert rule_step.kind == "rule"
        assert rule_step.goal == "mortal(socrates)"
        assert rule_step.rule_id == "RBAC-0043"
        assert rule_step.body == ["human(socrates)"]
        assert steps[1].kind == "fact"
        assert steps[1].goal == "human(socrates)"

    def test_no_rule_id_rule_step(self):
        r = explain("human(socrates)\nmortal($x) IF human($x)\n? mortal($who)")
        steps = r.explanations[0].structured_steps
        rule_step = next(s for s in steps if s.kind == "rule")
        assert rule_step.rule_id is None
        assert rule_step.body == ["human(socrates)"]

    def test_multi_conjunct_body_split(self):
        kb = (
            "user(alice)\n"
            "role(alice, admin)\n"
            "can_admin($u) IF user($u) AND role($u, admin)\n"
            "? can_admin(alice)"
        )
        r = explain(kb)
        steps = r.explanations[0].structured_steps
        rule_step = next(s for s in steps if s.kind == "rule")
        assert rule_step.body == ["user(alice)", "role(alice,admin)"]

    def test_negation_kind(self):
        kb = "active(alice)\nblocked($u) IF NOT active($u)\n? blocked(bob)"
        r = explain(kb)
        steps = r.explanations[0].structured_steps
        rule_step = steps[0]
        assert rule_step.kind == "rule"
        assert rule_step.body == ["NOT active(bob)"]
        neg_step = steps[1]
        assert neg_step.kind == "neg"
        assert neg_step.goal == "active(bob)"

    def test_arithmetic_true_kind(self):
        kb = (
            "last_login(user_a, 100)\n"
            "stale($u) IF last_login($u, $days) AND $days > 90\n"
            "? stale(user_a)"
        )
        r = explain(kb)
        steps = r.explanations[0].structured_steps
        assert any(s.kind == "true" for s in steps)

    def test_typed_count_matches_english(self):
        kb = (
            "parent(tom, bob)\nparent(bob, ann)\n"
            "ancestor($x, $y) IF parent($x, $y)\n"
            "ancestor($x, $y) IF parent($x, $z) AND ancestor($z, $y)\n"
            "? ancestor(tom, ann)"
        )
        r = explain(kb)
        assert r.error is None
        for e in r.explanations:
            assert len(e.structured_steps) == len(e.steps)

    def test_body_strips_internal_marker(self):
        kb = (
            "parent(tom, bob)\n"
            "ancestor($x, $y) IF parent($x, $y)  # rule: BASE-1\n"
            "? ancestor(tom, bob)"
        )
        r = explain(kb)
        steps = r.explanations[0].structured_steps
        rule_step = next(s for s in steps if s.kind == "rule")
        assert rule_step.rule_id == "BASE-1"
        assert rule_step.body == ["parent(tom,bob)"]
        assert "euclid_rule_id" not in " ".join(rule_step.body)

    def test_inner_and_outer_rule_ids(self):
        kb = (
            "parent(tom, bob)\n"
            "parent(bob, ann)\n"
            "ancestor($x, $y) IF parent($x, $y)  # rule: BASE-1\n"
            "ancestor($x, $y) IF parent($x, $z) AND ancestor($z, $y)  # rule: REC-2\n"
            "? ancestor(tom, ann)"
        )
        r = explain(kb)
        steps = r.explanations[0].structured_steps
        rule_ids = [s.rule_id for s in steps if s.kind == "rule"]
        assert rule_ids == ["REC-2", "BASE-1"]

    def test_steps_derived_from_typed(self):
        """English strings are exactly the rendered typed steps (regression)."""
        kb = (
            "human(socrates)\n"
            "mortal($x) IF human($x)  # rule: BIO-001\n"
            "? mortal($who)"
        )
        r = explain(kb)
        exp = r.explanations[0]
        for typed, english in zip(exp.structured_steps, exp.steps):
            assert "mortal(socrates)" in english or "human(socrates)" in english
        assert exp.steps == [
            "mortal(socrates) is derived by rule BIO-001 from: human(socrates).",
            "human(socrates) is asserted as a fact in the knowledge base.",
        ]
