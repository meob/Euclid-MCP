import shutil
import threading

import pytest

from euclid_mcp.models import KB
from euclid_mcp.prolog_server import (
    PrologServer,
    engine_requests_total,
    engine_restarts_total,
    engine_timeouts_total,
    kb_size,
    kb_skipped_loads_total,
)
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


def test_query_caps_solutions(server):
    kb = KB(facts=[f"item({i})" for i in range(50)], rules=[])
    decls, clauses = kb_to_decls_clauses(kb)
    server.load(decls, clauses)
    resp = server.query(build_query_snippet("item($x)", max_solutions=3))
    assert resp["status"] == "ok"
    assert len(resp["solutions"]) == 3
    assert set(s["solution"]["x"] for s in resp["solutions"]) == {0, 1, 10}


def test_query_cap_does_not_trim_within_limit(server):
    kb = KB(facts=[f"item({i})" for i in range(10)], rules=[])
    decls, clauses = kb_to_decls_clauses(kb)
    server.load(decls, clauses)
    resp = server.query(build_query_snippet("item($x)", max_solutions=25))
    assert len(resp["solutions"]) == 10


def test_restart_after_request_count():
    srv = PrologServer(restart_every=3)
    kb = KB(facts=["parent(tom, bob)"], rules=[])
    decls, clauses = kb_to_decls_clauses(kb)
    try:
        srv.load(decls, clauses)  # request 1
        first_pid = srv._proc.pid
        srv.load(decls, clauses)  # request 2
        assert srv._proc.pid == first_pid
        srv.load(decls, clauses)  # request 3 -> threshold crossed
        assert srv._proc.pid == first_pid
        # request 4 is a load: the periodic restart fires at its start, so the
        # relaunched engine already has the workspace for the query that follows.
        srv.load(decls, clauses)
        assert srv._proc.pid != first_pid
        resp = srv.query(build_query_snippet("parent($who, bob)", max_solutions=5))
        assert len(resp["solutions"]) == 1
    finally:
        srv.close()


def test_periodic_restart_defers_to_next_load():
    srv = PrologServer(restart_every=3)
    try:
        srv.ping()  # request 1
        first_pid = srv._proc.pid
        srv.ping()  # request 2
        srv.ping()  # request 3 -> threshold crossed
        srv.ping()  # request 4
        assert srv._proc.pid == first_pid  # no load: restart deferred
    finally:
        srv.close()


def test_restart_after_timeout(server):
    pid_before = server._proc.pid
    with pytest.raises(RuntimeError, match="timed out"):
        server._request(
            {"command": "query", "snippet": "repeat, fail.", "timeout": 0.1}
        )
    assert server._proc is None
    server.ping()
    assert server._proc is not None
    assert server._proc.pid != pid_before


def test_load_skips_unchanged_kb_hash(server):
    kb = KB(facts=["parent(tom, bob)"], rules=[])
    decls, clauses = kb_to_decls_clauses(kb)
    first = server.load(decls, clauses, kb_hash="h1")
    assert first["skipped"] is False
    assert first["facts"] == 1
    second = server.load(decls, clauses, kb_hash="h1")
    assert second["skipped"] is True
    assert second["facts"] == 1  # stored stats are returned, not recomputed
    resp = server.query(build_query_snippet("parent($who, bob)", max_solutions=5))
    assert len(resp["solutions"]) == 1


def test_load_reloads_on_kb_hash_change(server):
    kb = KB(facts=["parent(tom, bob)"], rules=[])
    decls, clauses = kb_to_decls_clauses(kb)
    assert server.load(decls, clauses, kb_hash="h1")["skipped"] is False
    assert server.load(decls, clauses, kb_hash="h2")["skipped"] is False
    # the workspace is now h2, so h1 must rebuild again
    assert server.load(decls, clauses, kb_hash="h1")["skipped"] is False


def test_load_without_kb_hash_always_reloads(server):
    kb = KB(facts=["parent(tom, bob)"], rules=[])
    decls, clauses = kb_to_decls_clauses(kb)
    assert server.load(decls, clauses)["skipped"] is False
    assert server.load(decls, clauses)["skipped"] is False


def test_assert_retract_invalidate_workspace_hash(server):
    kb = KB(facts=["parent(tom, bob)"], rules=[])
    decls, clauses = kb_to_decls_clauses(kb)
    server.load(decls, clauses, kb_hash="h1")
    server.assert_clause("parent(liz, mia).")
    # the assert invalidated the hash: reloading the same KB must rebuild the
    # workspace from decls/clauses, so the asserted fact is gone
    assert server.load(decls, clauses, kb_hash="h1")["skipped"] is False
    resp = server.query(build_query_snippet("parent($who, mia)", max_solutions=5))
    assert resp["status"] == "ok"
    assert resp["solutions"] == []  # the asserted fact is not present
    # the original KB is still intact after the rebuild
    resp = server.query(build_query_snippet("parent(tom, $who)", max_solutions=5))
    assert resp["status"] == "ok"
    assert [s["solution"]["who"] for s in resp["solutions"]] == ["bob"]
    # retract also invalidates: the same hash must rebuild again
    server.retract("parent(liz, mia).")
    assert server.load(decls, clauses, kb_hash="h1")["skipped"] is False


def test_skip_does_not_leak_previous_workspace(server):
    kb_a = KB(facts=["parent(tom, bob)"], rules=[])
    kb_b = KB(facts=["parent(ann, pat)"], rules=[])
    decls_a, clauses_a = kb_to_decls_clauses(kb_a)
    decls_b, clauses_b = kb_to_decls_clauses(kb_b)
    server.load(decls_a, clauses_a, kb_hash="a")
    server.load(decls_b, clauses_b, kb_hash="b")  # reload -> workspace is B
    server.load(decls_a, clauses_a, kb_hash="a")  # reload again -> workspace is A
    resp = server.query(build_query_snippet("parent($who, bob)", max_solutions=5))
    assert len(resp["solutions"]) == 1
    assert resp["solutions"][0]["solution"]["who"] == "tom"


def test_load_and_query_is_atomic_under_concurrency(server):
    """Concurrent load+query must not mix workspaces between requests."""

    def make_kb(tag):
        kb = KB(
            facts=[f"item({tag},{i})" for i in range(10)],
            rules=["answer($t,$x) IF item($t,$x)"],
        )
        return kb_to_decls_clauses(kb)

    decls_a, clauses_a = make_kb("a")
    decls_b, clauses_b = make_kb("b")
    snippet = build_query_snippet("answer($t,$x)", max_solutions=50)

    failures: list[str] = []

    def worker(tag, decls, clauses):
        expected = {(tag, i) for i in range(10)}
        for _ in range(150):
            resp = server.load_and_query(decls, clauses, snippet, kb_hash=tag)
            got = {
                (s["solution"]["t"], s["solution"]["x"])
                for s in resp.get("solutions", [])
            }
            if got != expected:
                failures.append(f"{tag}: got {sorted(got)} != {sorted(expected)}")
                return

    threads = [
        threading.Thread(target=worker, args=("a", decls_a, clauses_a)),
        threading.Thread(target=worker, args=("b", decls_b, clauses_b)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=90)
    assert failures == []


# ── observability metrics ───────────────────────────────────────────────────
# The metrics are process-wide singletons (euclid_mcp/metrics.py), so every
# assertion uses a relative delta from the value measured before the action.


def test_engine_request_counter_increments(server):
    before = engine_requests_total.value(command="query")
    decls, clauses = kb_to_decls_clauses(KB(facts=["human(socrates)"], rules=[]))
    server.load(decls, clauses)
    server.query(build_query_snippet("human($who)"))
    assert engine_requests_total.value(command="query") == before + 1


def test_periodic_restart_counter_increments():
    before = engine_restarts_total.value(reason="periodic")
    srv = PrologServer(restart_every=2)
    kb = KB(facts=["parent(tom, bob)"], rules=[])
    decls, clauses = kb_to_decls_clauses(kb)
    try:
        srv.load(decls, clauses)  # request 1
        srv.load(decls, clauses)  # request 2 -> threshold crossed
        srv.load(decls, clauses)  # request 3 -> periodic restart fires
        assert srv._proc is not None
        assert engine_restarts_total.value(reason="periodic") == before + 1
    finally:
        srv.close()


def test_timeout_counter_and_restart_reason(server):
    timeouts_before = engine_timeouts_total.value()
    restart_before = engine_restarts_total.value(reason="timeout")
    with pytest.raises(RuntimeError, match="timed out"):
        server._request(
            {"command": "query", "snippet": "repeat, fail.", "timeout": 0.1}
        )
    assert engine_timeouts_total.value() == timeouts_before + 1
    server.ping()  # relaunch happens lazily on the next request
    assert server._proc is not None
    assert engine_restarts_total.value(reason="timeout") == restart_before + 1


def test_skipped_load_counter_increments(server):
    before = kb_skipped_loads_total.value()
    decls, clauses = kb_to_decls_clauses(KB(facts=["parent(tom, bob)"], rules=[]))
    server.load(decls, clauses, kb_hash="h1")
    server.load(decls, clauses, kb_hash="h1")
    assert kb_skipped_loads_total.value() == before + 1


def test_kb_size_gauge(server):
    kb = KB(facts=[f"item({i})" for i in range(5)], rules=["answer($x) IF item($x)"])
    decls, clauses = kb_to_decls_clauses(kb)
    server.load(decls, clauses)
    assert kb_size.value(kind="facts") == 5
    assert kb_size.value(kind="rules") == 1


def test_requests_since_restart(server):
    before = server.requests_since_restart
    decls, clauses = kb_to_decls_clauses(KB(facts=["human(socrates)"], rules=[]))
    server.load(decls, clauses)
    server.query(build_query_snippet("human($who)"))
    assert server.requests_since_restart == before + 2
