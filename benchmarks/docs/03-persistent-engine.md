# Benchmark 3 — Persistent engine vs stateless subprocess

- **Script:** `benchmarks/persistent_engine_benchmark.py`
- **Run date:** 2026-08-12 (full run, repeat=10)
- **Environment:** SWI-Prolog 10.0.2 (arm64-darwin), Python 3.12.11, `.venv`

## What it measures

The performance cost of the **pre-v0.3.0 stateless path** (write `to_prolog()`
output to a temp file, spawn `swipl -q -f <file> -t halt`, parse the JSON
solution lines) versus the **persistent engine** (a single long-lived `swipl`
process connected by a JSON-lines pipe, `prolog_bridge.execute`).

## Method

Two KB sizes × two query shapes, each measured for cold start and 10
steady-state repeats on both paths:

- KB sizes: 100, 1 000, 10 000 facts (`user(u0000)` …)
- Query shapes: `ground` (single fact) and `scan` (variable over all facts)
- Metrics: cold-start time, steady-state average per call, speedup factor

## Results

| facts | query | legacy avg | persist avg | speedup | legacy cold | persist cold |
|------:|-------|-----------:|------------:|--------:|------------:|-------------:|
| 100 | ground | 105.9 ms | 2.6 ms | 41.0× | 147 ms | 83 ms |
| 100 | scan | 57.1 ms | 3.8 ms | 15.1× | 49 ms | 4 ms |
| 1 000 | ground | 66.2 ms | 8.0 ms | 8.3× | 86 ms | 9 ms |
| 1 000 | scan | 96.3 ms | 22.9 ms | 4.2× | 126 ms | 22 ms |
| 10 000 | ground | 180.5 ms | 64.7 ms | 2.8× | 180 ms | 69 ms |
| 10 000 | scan | 311.7 ms | 216.5 ms | 1.4× | 320 ms | 219 ms |

**Steady-state speedup (mean across cases): 12.1×**

## Conclusion

The persistent engine is an order of magnitude faster in steady state on small
and medium KBs, where the per-call `swipl` startup dominates the stateless
path. The gap narrows at 10 000 facts with a full scan, where the per-call
workspace reload over the pipe becomes the dominant cost of the persistent
path.

## Consequent implementation choices

- The persistent engine architecture (`euclid_mcp/prolog_server.py` +
  `prolog_bridge.execute`) is the default execution path.
- The scan cases are the motivation behind the engine-side solution cap (see
  Benchmark 4): a full scan over 10 000 facts costs ~216 ms even on the
  persistent path, so unbounded solution enumeration must be capped.
- The residual reload cost is the motivation for the **KB-persistence
  work item (planned, not yet implemented)**: cache parse+translate in Python
  and skip the engine reload when the KB fingerprint is unchanged (decision
  A+B, recorded 2026-08-12).
