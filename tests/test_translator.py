from euclid_mcp.models import KB
from euclid_mcp.translator import to_prolog


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
