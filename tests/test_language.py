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
    kb = parse("parent(tom, bob)\nancestor($x, $y) IF parent($x, $z) AND ancestor($z, $y)\n? ancestor(tom, $who)")
    assert len(kb.rules) == 1
    assert "IF" in kb.rules[0]


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
