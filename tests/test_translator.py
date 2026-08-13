from euclid_mcp.models import KB
from euclid_mcp.translator import build_query_snippet, to_prolog


def test_snippet_caps_solutions_in_prolog():
    snip = build_query_snippet("mortal($who)", max_solutions=7)
    assert "MaxSolutions = 7," in snip
    assert "nb_setval(euclid_solution_count, 0)" in snip
    assert "C0 < MaxSolutions" in snip
    assert "C1 is C0 + 1" in snip


def test_translate_socrates():
    kb = KB(
        facts=["mortal(socrates)", "human(socrates)"],
        rules=["mortal($x) IF human($x)"],
        query="mortal($who)",
    )
    code = to_prolog(kb)
    assert "mortal(socrates)." in code
    assert "human(socrates)." in code
    assert "mortal(X) :- human(X)" in code
    assert "% meta-interpreter:" in code
    assert "prove(true, _, true) :- !." in code
    assert ":- output, halt." in code


def test_translate_no_vars():
    kb = KB(
        facts=["mortal(socrates)"],
        query="mortal(socrates)",
    )
    code = to_prolog(kb)
    assert "mortal(socrates)." in code
    assert "output :-" in code
    assert "solution" in code


def test_translate_multiple_rules():
    kb = KB(
        facts=["parent(tom, bob)", "parent(bob, ann)"],
        rules=[
            "ancestor($x, $y) IF parent($x, $y)",
            "ancestor($x, $y) IF parent($x, $z) AND ancestor($z, $y)",
        ],
        query="ancestor(tom, $who)",
    )
    code = to_prolog(kb)
    assert "parent(X, Y)" in code or "parent(X,Y)" in code
    assert "ancestor" in code
    assert "ancestor(Z, Y)" in code


def test_dynamic_declarations():
    kb = KB(
        facts=["parent(tom, bob)"],
        rules=["ancestor($x, $y) IF parent($x, $y)"],
        query="ancestor(tom, $who)",
    )
    code = to_prolog(kb)
    assert ":- dynamic" in code
    assert "parent/2" in code
    assert "ancestor/2" in code


def test_arithmetic_in_rule():
    kb = KB(
        facts=["user(alice)", "last_login_days(alice, 120)"],
        rules=[
            "stale_access($user) IF user($user) AND "
            "last_login_days($user, $days) AND $days > 90"
        ],
        query="stale_access($who)",
    )
    code = to_prolog(kb)
    assert "stale_access(User) :- user(User), last_login_days(User, Days), Days > 90." in code
    assert "is_arith_goal(Goal)" in code


def test_arithmetic_gte():
    kb = KB(
        facts=["level(alice, 6)"],
        rules=["has_clearance($user, $min) IF level($user, $l) AND $l >= $min"],
        query="has_clearance($who, 5)",
    )
    code = to_prolog(kb)
    assert "has_clearance(User, Min) :- level(User, L), L >= Min." in code


def test_not_operator():
    kb = KB(
        facts=["user(alice)", "active(alice)"],
        rules=["inactive_user($user) IF user($user) AND NOT active($user)"],
        query="inactive_user($who)",
    )
    code = to_prolog(kb)
    assert "\\+ active(User)" in code or "\\+active(User)" in code


def test_query_conjunction():
    kb = KB(
        facts=["parent(tom, bob)", "age(bob, 25)"],
        rules=["parent($x, $y) IF parent($x, $y)"],
        query="parent(tom, $who) AND age($who, $age)",
    )
    code = to_prolog(kb)
    assert "(parent(tom, Who), age(Who, Age))" in code


def test_query_conjunction_dedup_vars():
    kb = KB(
        facts=["parent(tom, bob)"],
        rules=["ancestor($x, $y) IF parent($x, $y)"],
        query="ancestor(tom, $who) AND parent($who, $x)",
    )
    code = to_prolog(kb)
    assert "'who': Who" in code
    assert "'x': X" in code
    assert "'who': Who, 'who': Who" not in code


def test_not_equal_operator():
    kb = KB(
        facts=["count(alice, 5)"],
        rules=["not_zero($user) IF count($user, $n) AND $n != 0"],
        query="not_zero($who)",
    )
    code = to_prolog(kb)
    assert "=\\= " in code


def test_less_equal_operator():
    kb = KB(
        facts=["level(alice, 6)"],
        rules=["in_range($user) IF level($user, $l) AND $l <= 10"],
        query="in_range($who)",
    )
    code = to_prolog(kb)
    assert "=< " in code


def test_equal_operator():
    kb = KB(
        facts=["answer(alice, 42)"],
        rules=["correct($user) IF answer($user, $n) AND $n == 42"],
        query="correct($who)",
    )
    code = to_prolog(kb)
    assert "=:= " in code


def test_equal_operator_in_query():
    kb = KB(
        facts=["answer(alice, 42)"],
        query="answer($who, $n) AND $n == 42",
    )
    code = to_prolog(kb)
    assert "=:= " in code


def test_operators_inside_string_preserved():
    kb = KB(
        facts=['note(alice, "a <= b != c == d")'],
        query="note($who, $text)",
    )
    code = to_prolog(kb)
    assert '"a <= b != c == d"' in code
