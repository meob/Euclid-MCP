from euclid_mcp.language import parse


def test_text_facts():
    kb = parse("parent(tom, bob)\nparent(bob, ann)")
    assert len(kb.facts) == 2
    assert kb.facts[0] == "parent(tom, bob)"
    assert kb.query is None


def test_text_fact_rule_query():
    kb = parse("mortal(socrates)\nhuman(socrates)\nmortal($x) IF human($x)\n? mortal($who)")
    assert len(kb.facts) == 2
    assert len(kb.rules) == 1
    assert kb.query == "mortal($who)"


def test_text_with_and():
    kb = parse(
        "parent(tom, bob)\n"
        "ancestor($x, $y) IF parent($x, $z) AND ancestor($z, $y)\n"
        "? ancestor(tom, $who)"
    )
    assert len(kb.rules) == 1
    assert "if" in kb.rules[0]


def test_text_comments():
    kb = parse("# comment\nparent(tom, bob) // inline\n? query($x)")
    assert len(kb.facts) == 1
    assert kb.facts[0] == "parent(tom, bob)"
    assert kb.query == "query($x)"


def test_yaml_simple():
    kb = parse("facts:\n  - parent(tom, bob)\n  - parent(bob, ann)\nquery: parent(tom, $who)")
    assert len(kb.facts) == 2
    assert kb.query == "parent(tom, $who)"


def test_yaml_with_rules():
    kb = parse("""
facts:
  - parent(tom, bob)
rules:
  - ancestor($x, $y) IF parent($x, $y)
query: ancestor(tom, $who)
""")
    assert len(kb.facts) == 1
    assert len(kb.rules) == 1
    assert kb.query == "ancestor(tom, $who)"


def test_empty():
    kb = parse("")
    assert len(kb.facts) == 0
    assert len(kb.rules) == 0
    assert kb.query is None


def test_query_without_marker():
    kb = parse("parent(tom, bob)\n? parent(tom, $c)")
    assert kb.query == "parent(tom, $c)"


def test_multiline_rule():
    kb = parse("""
stale_access($user) IF
    user($user) AND last_login_days($user, $days) AND $days > 90
""")
    assert len(kb.rules) == 1
    assert "stale_access" in kb.rules[0]
    assert "user($user)" in kb.rules[0]
    assert "last_login_days($user, $days)" in kb.rules[0]
    assert "$days > 90" in kb.rules[0]


def test_multiline_rule_with_and():
    kb = parse("""
can_deploy($user, $env) IF
    user($user) AND
    has_role($user, $role) AND
    deploy_requires_level($env, $min) AND
    deploy_role_level($role, $level) AND
    $level >= $min
""")
    assert len(kb.rules) == 1
    assert "can_deploy" in kb.rules[0]
    assert "has_role" in kb.rules[0]
    assert "deploy_requires_level" in kb.rules[0]


def test_not_operator():
    kb = parse("inactive_user($user) IF user($user) AND NOT active($user)")
    assert len(kb.rules) == 1
    assert "not active($user)" in kb.rules[0]


def test_version_directive():
    kb = parse("@version 1.0\nparent(tom, bob)\n? parent($x, $y)")
    assert kb.version == "1.0"
    assert len(kb.facts) == 1
    assert kb.query == "parent($x, $y)"


def test_version_directive_with_comments():
    kb = parse("# Header\n@version 1.0\n// Another comment\nparent(tom, bob)\n? parent($x, $y)")
    assert kb.version == "1.0"
    assert len(kb.facts) == 1


def test_no_version_directive():
    kb = parse("parent(tom, bob)\n? parent($x, $y)")
    assert kb.version is None
    assert len(kb.facts) == 1


def test_version_not_treated_as_fact():
    kb = parse("@version 1.0\nparent(tom, bob)\n? parent($x, $y)")
    assert len(kb.facts) == 1
    assert kb.facts[0] == "parent(tom, bob)"


def test_case_insensitive_identifiers():
    kb = parse("Human(ALICE)\nhasRole(ALICE, Admin)\n? hasRole($who, Admin)")
    assert kb.facts[0] == "human(alice)"
    assert kb.facts[1] == "hasrole(alice, admin)"
    assert kb.query == "hasrole($who, admin)"


def test_case_insensitive_rule():
    kb = parse("Human(Socrates)\nMortal($X) IF Human($X)\n? Mortal($Who)")
    assert kb.facts[0] == "human(socrates)"
    assert kb.rules[0] == "mortal($x) if human($x)"
    assert kb.query == "mortal($who)"


def test_case_insensitive_variables_normalized():
    kb = parse("parent(tom, bob)\n? parent($X, $Y)")
    assert kb.query == "parent($x, $y)"


def test_keywords_case_insensitive():
    kb = parse("human(socrates)\nmortal($x) if human($x) and alive($x)")
    assert len(kb.rules) == 1
    assert kb.rules[0] == "mortal($x) if human($x), alive($x)"


def test_keywords_mixed_case():
    kb = parse("human(socrates)\nmortal($x) iF human($x) AnD alive($x)")
    assert len(kb.rules) == 1
    assert kb.rules[0] == "mortal($x) if human($x), alive($x)"


def test_multiline_rule_lowercase_and():
    kb = parse("""
can_deploy($user, $env) if
    user($user) and
    has_role($user, $role) and
    deploy_requires_level($env, $min) and
    deploy_role_level($role, $level) and
    $level >= $min
""")
    assert len(kb.rules) == 1
    assert "can_deploy" in kb.rules[0]
    assert "has_role" in kb.rules[0]
    assert "deploy_requires_level" in kb.rules[0]


def test_not_operator_case_insensitive():
    kb = parse("inactive_user($user) IF user($user) and not active($user)")
    assert len(kb.rules) == 1
    assert "not active($user)" in kb.rules[0]


def test_version_case_insensitive():
    kb = parse("@VERSION 2.0\nparent(tom, bob)\n? parent($x, $y)")
    assert kb.version == "2.0"
    assert len(kb.facts) == 1
    assert kb.facts[0] == "parent(tom, bob)"


def test_reserved_keyword_as_predicate():
    import pytest
    with pytest.raises(ValueError, match="Reserved keyword"):
        parse("if($x) IF human($x)")


def test_is_reserved_keyword():
    import pytest
    with pytest.raises(ValueError, match="Reserved keyword"):
        parse("is(1, 2)")


def test_percent_comment():
    kb = parse("% comment\nparent(tom, bob)\n% another\n? parent($x, $y)")
    assert len(kb.facts) == 1
    assert kb.facts[0] == "parent(tom, bob)"


def test_string_literal_double_quotes():
    kb = parse('user(alice, "alice@example.com")\n? user($who, $email)')
    assert kb.facts[0] == 'user(alice, "alice@example.com")'
    assert kb.query == 'user($who, $email)'


def test_string_literal_single_quotes():
    kb = parse("user(alice, 'alice@example.com')\n? user($who, $email)")
    assert kb.facts[0] == "user(alice, 'alice@example.com')"


def test_string_with_comma():
    kb = parse('address(alice, "Via Roma, 15")\n? address($who, $addr)')
    assert kb.facts[0] == 'address(alice, "Via Roma, 15")'


def test_string_with_if_inside():
    kb = parse('note(alice, "data IF more")\n? note($who, $text)')
    assert kb.facts[0] == 'note(alice, "data IF more")'


def test_string_with_and_inside():
    kb = parse('note(alice, "x AND y")\n? note($who, $text)')
    assert kb.facts[0] == 'note(alice, "x AND y")'


def test_string_preserves_case():
    kb = parse('user("Alice Smith")\n? user($name)')
    assert kb.facts[0] == 'user("Alice Smith")'


def test_string_in_rule():
    kb = parse('greet($x) IF name($x, "World")\n? greet($who)')
    assert kb.rules[0] == 'greet($x) if name($x, "World")'
