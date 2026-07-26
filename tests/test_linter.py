from euclid_mcp.linter import lint_rule


def test_unsafe_negation_unbound_var():
    warnings = lint_rule("blocked($user) IF NOT active($user)")
    assert len(warnings) == 1
    assert "Unsafe negation" in warnings[0]
    assert "user" in warnings[0]


def test_safe_negation_bound_var():
    warnings = lint_rule(
        "inactive($user) IF user($user) AND NOT active($user)"
    )
    assert len(warnings) == 0


def test_unsafe_negation_multiple_vars():
    warnings = lint_rule(
        "block($u, $r) IF NOT has_access($u, $r)"
    )
    assert len(warnings) == 1
    assert "r" in warnings[0]
    assert "u" in warnings[0]


def test_safe_negation_partially_bound():
    warnings = lint_rule(
        "check($u, $r) IF user($u) AND has_role($u, $r) AND NOT active($r)"
    )
    assert len(warnings) == 0


def test_unsafe_negation_later_bound():
    warnings = lint_rule(
        "check($u) IF NOT active($u) AND user($u)"
    )
    assert len(warnings) == 1
    assert "'u'" in warnings[0]


def test_no_negation():
    warnings = lint_rule("mortal($x) IF human($x)")
    assert len(warnings) == 0


def test_fact_no_warning():
    warnings = lint_rule("parent(tom, bob)")
    assert len(warnings) == 0
