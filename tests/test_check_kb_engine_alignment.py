"""check_kb must reject statements the engines would refuse.

``language.parse`` is deliberately line-lenient, while both inference
backends re-parse every statement with the strict term parser. The gap let
a green ``:check`` precede a runtime engine error (e.g. a stray ``AND ...``
line surfacing as a "fact"). run_check_kb now validates every fact, rule
and the query against the same strict parser the engines use.
"""

from euclid_mcp.validation import run_check_kb


def test_lenient_but_unparsable_statement_is_flagged():
    res = run_check_kb("p(a b)\n? p($x)")
    assert res.valid is False
    assert any(e.type == "parse_error" for e in res.errors)


def test_bad_rule_body_is_flagged():
    res = run_check_kb("p IF q(a b)\n? p")
    assert res.valid is False
    assert any(e.type == "parse_error" for e in res.errors)


def test_good_kb_stays_green():
    res = run_check_kb(
        "edge(a, b)\n"
        "path($x, $y) IF edge($x, $y)\n"
        "? path($f, $t)"
    )
    assert res.valid is True
    assert res.errors == []


def test_unicode_and_quoted_data_stay_green():
    res = run_check_kb('parent(父, 张三)\nlabel("_999")\n? parent($a, $b)')
    assert res.valid is True
    assert res.errors == []
