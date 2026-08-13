# Benchmark 4 — Engine-side `max_solutions` cap

- **Script:** `benchmarks/solution_cap_benchmark.py`
- **Run date:** 2026-08-12 (full run, repeat=5)
- **Environment:** SWI-Prolog 10.0.2 (arm64-darwin), Python 3.12.11, `.venv`

## What it measures

Whether the Prolog-side `max_solutions` cap **stops work early**, i.e. that a
capped query costs roughly the same regardless of how many solutions exist in
the KB, instead of enumerating them all.

## Method

A dense query (variable over all facts) is run on KBs of increasing size. The
KB is loaded once; only the query phase is timed (5 repeats, averaged).

- KB sizes: 1 000, 10 000, 100 000 facts (`item(0)` …)
- `capped(5)`: `max_solutions = 5` — the caller-visible default cap
- `uncapped`: `max_solutions = 1 000 000` (effectively unbounded)

The cap is enforced inside the generated query snippet (`count_limit/2` in
`translator.build_query_snippet`), so the engine's outer solver stops after the
first `max_solutions` answers.

## Results

| facts | capped(5) | uncapped | ratio |
|------:|----------:|---------:|------:|
| 1 000 | 0.6 ms | 12.4 ms | 19.4× |
| 10 000 | 3.0 ms | 119.7 ms | 40.2× |
| 100 000 | 23.4 ms | 1 253.6 ms | 53.7× |

## Conclusion

Capped time stays roughly flat as the KB grows (0.6 → 23.4 ms), while the
uncapped time scales with the solution count (12.4 → 1 253.6 ms). The
**rising ratio** (19× → 54×) proves that work stops early: the cap prevents a
dense query from degenerating into a full scan of the KB.

## Consequent implementation choices

- Introduced with the security-hardening work (commit `6b0295ba`,
  2026-08-12): the solution cap and the `MAX_SOLUTIONS_LIMIT` guard are
  enforced **engine-side**, not only in the Python layer.
- Without this cap, `max_solutions` would only trim results after the engine
  had already produced all of them (see Benchmark 3 scan cases for the cost of
  full enumeration).
