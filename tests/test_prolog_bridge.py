import shutil

import pytest

from euclid_mcp.models import KB
from euclid_mcp.prolog_bridge import execute
from euclid_mcp.translator import to_prolog

pytestmark = pytest.mark.skipif(
    shutil.which("swipl") is None,
    reason="SWI-Prolog (swipl) not installed",
)


def _run(kb: KB) -> list:
    code = to_prolog(kb)
    return execute(code, timeout=15)


def test_socrates():
    kb = KB(
        facts=["mortal(socrates)", "human(socrates)"],
        rules=["mortal($x) IF human($x)"],
        query="mortal($who)",
    )
    solutions = _run(kb)
    assert len(solutions) == 2
    assert all(s.substitutions.get("who") == "socrates" for s in solutions)
    types = {s.proof.type for s in solutions}
    assert "fact" in types
    assert "rule" in types


def test_ancestor():
    kb = KB(
        facts=["parent(tom, bob)", "parent(bob, ann)", "parent(tom, liz)"],
        rules=[
            "ancestor($x, $y) IF parent($x, $y)",
            "ancestor($x, $y) IF parent($x, $z) AND ancestor($z, $y)",
        ],
        query="ancestor(tom, $who)",
    )
    solutions = _run(kb)
    assert len(solutions) == 3
    who_values = {s.substitutions["who"] for s in solutions}
    assert who_values == {"bob", "ann", "liz"}


def test_no_solutions():
    kb = KB(
        facts=["mortal(socrates)"],
        query="immortal($who)",
    )
    solutions = _run(kb)
    assert len(solutions) == 0


def test_ground_query():
    kb = KB(
        facts=["mortal(socrates)", "human(socrates)"],
        rules=["mortal($x) IF human($x)"],
        query="mortal(socrates)",
    )
    solutions = _run(kb)
    assert len(solutions) == 2
    assert all(s.substitutions == {} for s in solutions)


def test_multiple_facts():
    kb = KB(
        facts=["parent(tom, bob)", "parent(tom, liz)"],
        query="parent(tom, $c)",
    )
    solutions = _run(kb)
    assert len(solutions) == 2
    assert {s.substitutions["c"] for s in solutions} == {"bob", "liz"}
