import shutil

import pytest

from euclid_mcp.models import KB
from euclid_mcp.prolog_bridge import execute
from euclid_mcp.translator import kb_to_decls_clauses

pytestmark = pytest.mark.skipif(
    shutil.which("swipl") is None,
    reason="SWI-Prolog (swipl) not installed",
)


def _run(kb: KB) -> list:
    decls, clauses = kb_to_decls_clauses(kb)
    return execute(decls, clauses, kb.query, timeout=15)


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


def test_execute_with_kb_hash():
    kb = KB(facts=["mortal(socrates)"], query="mortal($who)")
    decls, clauses = kb_to_decls_clauses(kb)
    first = execute(decls, clauses, "mortal($who)", timeout=15, kb_hash="kb-1")
    second = execute(decls, clauses, "mortal($who)", timeout=15, kb_hash="kb-1")
    assert len(first) == len(second) == 1
    assert first[0].substitutions == second[0].substitutions == {"who": "socrates"}


# ── deep health + graceful shutdown hook ─────────────────────────────────────


def test_health_info_before_any_engine():
    from euclid_mcp.prolog_bridge import close, health_info

    close()
    # A cold process has no engine yet (it starts lazily on first use): that
    # is healthy, and health_info() must not launch one just to answer.
    info = health_info()
    assert info is not None
    assert info["backend"] == "prolog"
    assert info["reachable"] is True
    assert info["facts"] is None
    assert info["requests_since_restart"] == 0


def test_health_info_after_engine_use():
    from euclid_mcp.prolog_bridge import close, execute, health_info

    close()
    decls, clauses = kb_to_decls_clauses(
        KB(facts=["human(socrates)"], rules=["mortal($x) IF human($x)"])
    )
    execute(decls, clauses, "mortal($who)", timeout=15)
    info = health_info()
    assert info is not None
    assert info["backend"] == "prolog"
    assert info["facts"] == 1
    assert info["rules"] == 1
    assert isinstance(info["requests_since_restart"], int)
    close()


def test_close_is_idempotent_and_engine_relaunches():
    from euclid_mcp.prolog_bridge import close, execute

    close()
    close()  # closing twice must be a no-op
    decls, clauses = kb_to_decls_clauses(KB(facts=["human(socrates)"]))
    solutions = execute(decls, clauses, "human(socrates)", timeout=15)
    assert len(solutions) == 1
    assert solutions[0].substitutions == {}
    close()


def test_compound_binding_rendered_as_string():
    # A query variable bound to a nested compound term must come back as a
    # rendered string, not crash json_write with type_error(json_term, ...).
    kb = KB(
        facts=[
            "final(cfg(done, $t), cfg(done, $t))",
            "step(cfg(run, tape($l, cell(0, $r))),"
            " cfg(done, tape($l, cell(1, $r))))",
        ],
        rules=["final($c, $f) IF step($c, $c2) AND final($c2, $f)"],
        query="final(cfg(run, tape($l, cell(0, cell(blank, blank)))), $end)",
    )
    solutions = _run(kb)
    assert len(solutions) == 1
    end = solutions[0].substitutions["end"]
    assert isinstance(end, str)
    flat = end.replace(" ", "")
    assert flat.startswith("cfg(done,tape(")
    assert "cell(1," in flat
