# Benchmark 5 — Stress & soak: engine correctness under load

- **Script:** `benchmarks/euclid_bench.py`
- **Run date:** 2026-08-12 (three runs)
- **Environment:** SWI-Prolog 10.0.2 (arm64-darwin), Python 3.12.11, `.venv`

## What it measures

Whether the persistent engine **stays correct under load**: no response
mixing, no workspace (KB) pollution, and no engine errors. It also exercises
the periodic engine restart (`--restart-every`, direct mode) and the HTTP API
serialization (`--mode api`).

## Method

Each request loads a **tagged** knowledge base (`item(<tag>, <x>)` facts plus
an `answer/2` rule) and must return exactly that KB's solutions. Any response
whose solutions come from a different tag — or that differs from the expected
set — is request mixing or workspace pollution and fails the run. The tagged
KBs rotate in a fixed order, so a KB that is polluted by the previous one can
never verify.

Modes:

- `direct` — hammers the persistent engine (`PrologServer`) directly. `load` +
  `query` run as a single atomically-locked exchange
  (`PrologServer.load_and_query`), so concurrent workers cannot interleave
  workspaces — `--workers N` must always pass.
- `api` — stresses the real HTTP API (single-threaded `HTTPServer`);
  concurrent clients are serialized by the accept loop, so correctness must
  hold at any `--workers` value.

## Results (2026-08-12)

### Run 1 — `direct`, workers=1, 1 200 iterations, restart_every=1000

```
RESULT: PASS
iterations=1,200    throughput=280.1 req/s
latency   mean=3.4ms   p50=3.2ms   p95=3.7ms   p99=4.4ms
mismatches=0    exceptions=0    engine_restarts=2
```

The soak crosses the restart threshold twice (2 400 `_request` calls ≈ 2
periodic restarts at `restart_every=1000`) with **zero failures**.

### Run 2 — `direct`, workers=4, 12 s (v0.3.1, after the atomicity fix)

```
RESULT: PASS
iterations=5,324    throughput=442.9 req/s
latency   mean=9.0ms   p50=8.2ms   p95=9.1ms   p99=10.1ms
mismatches=0    exceptions=0    engine_restarts=10
```

Before the fix (2026-08-12) the same run failed with ~50% response mixing
(1 464 mismatches over 2 925 iterations) — see the atomicity-gap note below.

### Run 3 — `api`, workers=4, 10 s (expected PASS)

```
RESULT: PASS
iterations=2,043    throughput=194.2 req/s
latency   mean=19.6ms   p50=18.4ms   p95=20.1ms   p99=34.0ms
mismatches=0    exceptions=0    engine_restarts=0
```

The HTTP path is serialized by the accept loop and stays correct under 4
concurrent clients.

## Bug found and fixed (2026-08-12)

**Symptom.** The first soak run with `--workers 1` failed: every time the
periodic restart fired (after `restart_every` `_request` calls), the request
immediately following the relaunch raised `RuntimeError: engine_error`.

**Root cause.** The periodic restart terminated the engine **at the end** of
the request that crossed the threshold. If that request was a `load`, the
paired `query` started on a freshly-launched, bare engine. The meta-interpreter
(`prove/3`, `proof_to_json/2`, and helpers) is provided **per load** by the
Python side (`translator.kb_to_decls_clauses`), so the first query raised
`existence_error` on `prove/3` → `engine_error`. Minimal repro confirmed:
`terminate → relaunch → query` always fails; `terminate → relaunch → load →
query` works.

**Fix.** `euclid_mcp/prolog_server.py` now fires the periodic restart **at the
start of the next `load`** instead of at the end of any crossing request. A
freshly-launched engine therefore always receives its workspace (including the
per-load meta-interpreter) before any query runs on it. Regression tests were
added in `tests/test_prolog_server.py`
(`test_restart_after_request_count`,
`test_periodic_restart_defers_to_next_load`), and the server suite passes.

## Atomicity gap — found 2026-08-12, fixed in v0.3.1

**Symptom.** Direct mode with `--workers 4` produced ~50% response mixing:
requests returned solutions from the **wrong tag** (Run 2 above, before the
fix).

**Root cause.** `prolog_bridge.execute` performed `load` and `query` as two
**separately-locked** pipe exchanges. Concurrent worker threads interleaved
the two steps of different requests: worker A loads its KB, worker B loads its
KB, worker A queries → A reads the solutions of B's KB.

**Fix (v0.3.1).** `PrologServer.load_and_query` holds the server lock across
`load` + `query`, making them a **single atomic exchange**. `execute` and the
direct benchmark use it, so concurrent workers can no longer interleave one
workspace between another request's load and query. Regression test:
`tests/test_prolog_server.py::test_load_and_query_is_atomic_under_concurrency`
(150 iterations × 2 threads on different tagged KBs, must return zero
mismatches).

## Consequent implementation choices

1. **Periodic-restart placement** (fixed): restart fires only before a `load`,
   so the engine that answers a query always has the workspace from its own
   paired load.
2. **Load+query atomicity** (fixed in v0.3.1): `load_and_query` makes the
   pair a single locked exchange; `euclid_bench.py` is the regression gate and
   must stay PASS at `--workers 4`.
3. **KB-persistence work item** (implemented in v0.3.1): the residual
   per-request reload cost measured here motivated the A+B decision (cache
   parse+translate + engine fingerprint skip). A repeated identical 20 000-fact
   KB drops from ~196 ms to ~18 ms per load.
