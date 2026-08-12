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

- `direct` — hammers the persistent engine (`PrologServer`) directly.
  `--workers 1` matches the shipped single-threaded architecture.
  `--workers N>1` surfaces the known load+query atomicity gap (see below).
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

### Run 2 — `direct`, workers=4, 10 s (expected FAIL)

```
RESULT: FAIL
iterations=2,925    throughput=286.7 req/s
latency   mean=13.7ms   p50=12.9ms   p95=14.0ms   p99=14.8ms
mismatches=1,464    exceptions=0    engine_restarts=5
```

~50% of requests return solutions from the **wrong tag**. This is the
documented load+query atomicity gap, not a new regression.

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

## Known gap (documented, not yet fixed)

**Direct mode with `--workers N>1`.** `prolog_bridge.execute` performs `load`
and `query` as two **separately-locked** pipe exchanges. Concurrent worker
threads can interleave the two steps of different requests: worker A loads its
KB, worker B loads its KB, worker A queries → A reads the solutions of B's KB.
The result is the ~50% response-mixing seen in Run 2.

- The **production path is unaffected**: the MCP/API servers are
  single-threaded and serialize every request, and `--workers 1` matches that
  architecture.
- The fix is to make load+query a **single atomic exchange** (one engine
  command that loads and queries, or a held lock across both steps). Until
  then, a FAIL at `--workers>1` in `direct` mode is the *expected* outcome,
  and this benchmark is the regression detector for the fix.

## Consequent implementation choices

1. **Periodic-restart placement** (fixed): restart fires only before a `load`,
   so the engine that answers a query always has the workspace from its own
   paired load.
2. **Regression detection:** `euclid_bench.py` is the gate for the atomicity
   fix — it must flip from FAIL to PASS at `--workers 4` once load+query
   becomes atomic.
3. **KB-persistence work item (planned)**: the residual per-request reload
   cost measured here motivated the A+B decision (cache parse+translate +
   engine fingerprint skip), recorded 2026-08-12, not yet implemented.
