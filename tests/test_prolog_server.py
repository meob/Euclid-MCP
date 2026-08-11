import shutil

import pytest

from euclid_mcp.models import KB
from euclid_mcp.prolog_server import PrologServer
from euclid_mcp.translator import build_query_snippet, kb_to_decls_clauses

pytestmark = pytest.mark.skipif(
    shutil.which("swipl") is None,
    reason="SWI-Prolog (swipl) not installed",
)


@pytest.fixture()
def server():
    srv = PrologServer()
    try:
        srv.ping()
    except Exception:
        pytest.skip("SWI-Prolog engine failed to launch")
    yield srv
    srv.close()


def test_ping(server):
    resp = server.ping()
    assert resp["status"] == "ok"
    assert resp["engine"] == "prolog"


def test_load_stats(server):
    kb = KB(facts=["parent(tom, bob)"], rules=["ancestor($x, $y) IF parent($x, $y)"])
    decls, clauses = kb_to_decls_clauses(kb)
    resp = server.load(decls, clauses)
    assert resp["status"] == "ok"
    assert resp["facts"] == 1
    assert resp["rules"] == 1


def test_load_replaces_workspace(server):
    decls, clauses = kb_to_decls_clauses(KB(facts=["human(socrates)"], rules=[]))
    server.load(decls, clauses)
    assert server.stats()["facts"] == 1

    decls2, clauses2 = kb_to_decls_clauses(KB(facts=["human(plato)"], rules=[]))
    server.load(decls2, clauses2)
    stats = server.stats()
    assert stats["facts"] == 1
    resp = server.query(build_query_snippet("human($who)"))
    assert resp["solutions"][0]["solution"] == {"who": "plato"}


def test_query_solutions(server):
    kb = KB(
        facts=["human(socrates)"],
        rules=["mortal($x) IF human($x)"],
    )
    decls, clauses = kb_to_decls_clauses(kb)
    server.load(decls, clauses)
    resp = server.query(build_query_snippet("mortal($who)"))
    assert resp["status"] == "ok"
    assert len(resp["solutions"]) == 1
    sol = resp["solutions"][0]
    assert sol["solution"] == {"who": "socrates"}
    assert sol["proof"]["type"] == "rule"


def test_query_empty(server):
    decls, clauses = kb_to_decls_clauses(KB(facts=["human(socrates)"], rules=[]))
    server.load(decls, clauses)
    resp = server.query(build_query_snippet("mortal($who)"))
    assert resp == {"status": "ok", "solutions": []}


def test_assert_retract(server):
    decls, clauses = kb_to_decls_clauses(KB(facts=[], rules=[]))
    server.load(decls, clauses)
    server.assert_clause("flag(x).")
    assert server.stats()["facts"] == 1
    resp = server.retract("flag(x).")
    assert resp["status"] == "ok"
    assert resp["count"] == 1
    assert server.stats()["facts"] == 0


def test_unknown_command(server):
    with pytest.raises(RuntimeError):
        server._request({"command": "nope"})
