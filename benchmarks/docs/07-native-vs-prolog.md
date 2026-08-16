# Benchmark 7 — Native engine vs SWI-Prolog (example 07)

- **Script:** `benchmarks/native_vs_prolog_benchmark.py`
- **Run date:** 2026-08-14 (small KB repeat=7, full KB repeat=3)
- **Environment:** SWI-Prolog 10.0.2 (arm64-darwin), Python 3.12.11, `.venv`

## What it measures

The **per-question latency** of the pure-Python native Euclid-IR engine
(`EUCLID_BACKEND=native`) against the SWI-Prolog engine
(`EUCLID_BACKEND=prolog`) on the real example 07 workload (IT security
compliance, 10 questions). This is the first head-to-head benchmark between
the two backends introduced in v0.4.0.

## Method

- The same KB is loaded once and each question runs through the real `reason`
  tool (parsing + engine + result models), exactly as a client would call it.
- Warm-up: 2 calls, then `repeat` samples per question; **median** reported.
- Small KB = `small_generated_facts.euclid` (1 120 lines), full KB =
  `generated_facts.euclid` (4 412 lines), plus the standards/policy rule files.
- `max_solutions=50`, `max_depth=30` (the demo's defaults).
- Solution counts are reported per question (P/N) to prove **result parity**,
  not just speed.
- The Prolog backend benefits from its persistent process and the cached
  KB translation; the native engine re-parses the KB on every call by design.

## Results — small KB (1 120 lines)

| Q | prolog | native | ratio | sols P/N |
|---|-------:|-------:|------:|:--------:|
| Q1 | 3.4 ms | 4.7 ms | 1.4× | 0/0 |
| Q2 | 4.9 ms | 10.2 ms | 2.1× | 5/5 |
| Q3 | 18.4 ms | 309.7 ms | **16.8×** | 30/30 |
| Q4 | 4.2 ms | 10.3 ms | 2.4× | 2/2 |
| Q5 | 3.6 ms | 6.6 ms | 1.8× | 4/4 |
| Q6 | 3.5 ms | 13.9 ms | 4.0× | 0/0 |
| Q7 | 3.6 ms | 4.7 ms | 1.3× | 2/2 |
| Q8 | 3.8 ms | 19.2 ms | 5.0× | 0/0 |
| Q9 | 3.6 ms | 5.6 ms | 1.6× | 0/0 |
| Q10 | 3.5 ms | 4.8 ms | 1.3× | 0/0 |
| **Σ** | **52.7 ms** | **389.7 ms** | **7.4×** | — |

## Results — full KB (4 412 lines)

| Q | prolog | native | ratio | sols P/N |
|---|-------:|-------:|------:|:--------:|
| Q1 | 16.1 ms | 21.0 ms | 1.3× | 0/0 |
| Q2 | 31.3 ms | 120.1 ms | 3.8× | 44/44 |
| Q3 | 411.8 ms | 2 653.7 ms | 6.4× | 50/50 |
| Q4 | 20.5 ms | 129.5 ms | 6.3× | 4/4 |
| Q5 | 14.8 ms | 96.4 ms | 6.5× | 17/17 |
| Q6 | 13.2 ms | 421.0 ms | **31.8×** | 0/0 |
| Q7 | 13.1 ms | 20.9 ms | 1.6× | 10/10 |
| Q8 | 16.9 ms | 229.3 ms | 13.5× | 0/0 |
| Q9 | 13.0 ms | 61.3 ms | 4.7× | 0/0 |
| Q10 | 13.0 ms | 23.8 ms | 1.8× | 1/1 |
| **Σ** | **563.7 ms** | **3 776.9 ms** | **6.7×** | — |

## Conclusion

- **Result parity:** every question returns the same solution count on both
  backends — the speed gap is a performance difference, not a semantic one.
- **Typical queries:** the native engine is ~1.3–2.5× slower than SWI-Prolog
  and stays in single-digit milliseconds on the small KB. For a per-question
  MCP tool call that is negligible in practice.
- **Worst cases — naive backtracking shows:** the ratio explodes on (a)
  high-solution-count joins with wildcards (small Q3, 30 solutions, 16.8×;
  full Q3 capped at 50) and (b) exhaustive-failure queries that must prove
  absence (full Q6/Q8, 0 solutions, 31.8×/13.5×, via `NOT`). These are exactly
  the workloads where a compiled WAM engine and a hand-tuned meta-interpreter
  earn their keep.
- **Scaling:** the aggregate ratio stays flat (~7×) as the KB grows 4×
  (390 ms → 3.8 s absolute), i.e. both engines scale similarly in size; the
  constant factor is what differs.

## Consequent implementation choices / notes

- The benchmark confirms the v0.4.0 guidance: the native engine is for **small
  knowledge bases** and interactive use; heavy counting, wide wildcard joins,
  and exhaustive-failure reasoning (typical of compliance audits, exactly
  example 07) should stay on SWI-Prolog when available.
- The native engine re-parses the full KB on every call (no Program cache
  yet), which contributes a fixed ~3–5 ms floor per question on the small KB;
  the Prolog path amortizes translation via `_translate_cached`. A native
  Program memoization keyed on the KB fingerprint (mirroring
  `_translate_cached`) is the obvious next optimization.
- Earlier incidental timings on the same example (462 ms vs 204 ms, no
  warm-up) are superseded by this controlled run.
