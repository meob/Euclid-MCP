# Benchmarks — Euclid-MCP

Catalog of the benchmark suite: what each script measures, the results, and
the implementation choices that followed. One detail page per benchmark lives
in [`docs/`](docs/).

**Environment (2026-08-12 runs):** SWI-Prolog 10.0.2 (arm64-darwin), Python
3.12.11, `.venv`.

## Index

| # | Script | Measures | Result | Detail |
|---|--------|----------|--------|--------|
| 1 | `reasoning_benchmark.py` | Small LLM vs cloud LLM vs LLM + Euclid-MCP, 5 small reasoning tasks | All equal (5/5) at small scale; Euclid adds input tokens | [01](docs/01-reasoning-vs-llm.md) |
| 2 | `rbac_1000.py` | Same comparison at scale (1 000 users, 1 053 facts) | LLMs 2/5, Euclid 5/5, faster (963 ms) and fewer output tokens | [02](docs/02-rbac-at-scale.md) |
| 3 | `persistent_engine_benchmark.py` | Stateless subprocess vs persistent engine | **12.1×** mean steady-state speedup | [03](docs/03-persistent-engine.md) |
| 4 | `solution_cap_benchmark.py` | Engine-side `max_solutions` cap stops work early | Capped time flat (0.6→23 ms); ratio vs uncapped grows 19×→54× | [04](docs/04-solution-cap.md) |
| 5 | `euclid_bench.py` | Stress & soak: mixing, pollution, restart, API under load | workers=1 & API **PASS**; direct workers=4 FAIL (known gap) | [05](docs/05-stress-soak.md) |

## Summary of results

1. **Reasoning at small scale (July 2026).** With 5–15 facts, LLM alone is
   sufficient: all three conditions scored 5/5. Euclid-MCP matches accuracy at
   slightly higher input tokens. **→** Use the engine only when facts outgrow
   reliable LLM context.

2. **RBAC at scale (July 2026).** At 1 053 facts both LLMs hallucinate
   systematically (2/5); Euclid-MCP is exact (5/5), faster (963 ms vs
   6 966 ms) and token-cheaper (12 vs 165 output tokens). **→** The engine's
   value proposition, referenced from the README.

3. **Persistent engine vs stateless (2026-08-12).** Reusing one long-lived
   `swipl` process instead of spawning one per call is **12.1×** faster in
   steady state. The gap narrows at large KBs because the per-call workspace
   reload dominates. **→** Persistent engine is the default path; reload cost
   motivates KB persistence (see work items).

4. **Solution cap (2026-08-12).** The Prolog-side cap keeps a capped query at
   ~flat cost (0.6 → 23.4 ms) while the uncapped cost scales with solutions
   (12 → 1 254 ms). **→** Cap enforced engine-side (`count_limit/2`), so
   dense queries cannot degenerate into full scans.

5. **Stress & soak (2026-08-12).**
   - `direct workers=1`, 1 200 it., restart_every=1000: **PASS**, 280 req/s,
     mean 3.4 ms, 2 restarts, 0 failures.
   - `direct workers=4`, 10 s: **FAIL**, 1 464/2 925 mismatches (~50%) — the
     known load+query atomicity gap.
   - `api workers=4`, 10 s: **PASS**, 194 req/s, 0 failures.
   **→** Found and fixed a real restart bug (see below); the direct
   multi-worker gap is documented and tracked.

## Consequent implementation choices

- **Persistent engine architecture** (`PrologServer` + JSON-lines pipe)
  validated by Benchmark 3; it replaced the per-call `swipl` subprocess.
- **Engine-side solution cap** (`count_limit/2`, `MAX_SOLUTIONS_LIMIT`)
  introduced by Benchmark 4 under the security-hardening work
  (commit `6b0295ba`).
- **Periodic-restart bug fixed** (Benchmark 5): the restart fired at the end
  of a crossing request and stranded the next query on a bare engine
  (`existence_error` on the per-load `prove/3`). It now fires at the start of
  the next `load` (`euclid_mcp/prolog_server.py`), with regression tests in
  `tests/test_prolog_server.py`.
- **Documented, not yet fixed:** direct-mode `--workers>1` load+query
  atomicity gap (~50% response mixing). `euclid_bench.py` is the regression
  detector — it must flip to PASS once load+query becomes a single atomic
  exchange.

## Exploratory measurement — KB reload cost (2026-08-12)

Ad-hoc profiling of a single engine call (parse → translate → load → query) on
a hot engine, to decide whether persisting the KB is worthwhile:

| KB | parse | translate | load (assert) | query |
|----|------:|----------:|--------------:|------:|
| 500 | 4.6 ms | 2.3 ms | 3.7 ms | 0.4 ms |
| 5 000 | 36 ms | 18 ms | 14 ms | 2.7 ms |
| 20 000 | 143 ms | 73 ms | 44 ms | 4.7 ms |

The engine reload is only ~17–25% of the cost; **Python-side parse dominates**
(~55%). Every tool call reloads the whole KB, and `what_if` does it twice.

**Decision (A+B, planned — not implemented):** cache parse+translate in Python
keyed by KB fingerprint, and skip the engine reload when the fingerprint is
unchanged. Target: repeated identical KB at 20 000 facts from ~260 ms to
~5 ms. The delta-based approach (keep base resident, apply/remove only session
facts) is deferred.
