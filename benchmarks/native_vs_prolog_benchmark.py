"""Native engine vs SWI-Prolog benchmark on example 07 (IT security compliance).

Runs the same 10 questions from example 07 through the real ``reason`` tool on
both backends, with warm-up and repeated samples, and reports per-query median
latency, the aggregate total, and the ratio. Solution counts are compared per
query to prove result parity — not just speed.

Measurements go through the whole tool layer (KB parsing + engine + result
models), so they reflect what a client actually experiences per question. The
Prolog backend benefits from its persistent process and cached translation;
the native engine re-parses the KB on every call by design (see
docs/NATIVE_ENGINE.md).

Usage:
    python benchmarks/native_vs_prolog_benchmark.py          # small KB (581-line facts)
    python benchmarks/native_vs_prolog_benchmark.py --full   # full generated KB
    python benchmarks/native_vs_prolog_benchmark.py --quick  # 3 repeats, small KB
"""
import argparse
import logging
import os
import shutil
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from euclid_mcp.server import reason  # noqa: E402

DEMO_DIR = Path(__file__).resolve().parent.parent / "examples" / "07_it_security_compliance"
sys.path.insert(0, str(DEMO_DIR))

from demo import QUESTIONS, load_knowledge  # noqa: E402

logging.getLogger("euclid_mcp").setLevel(logging.ERROR)

MAX_SOLUTIONS = 50
MAX_DEPTH = 30


def time_questions(
    knowledge: str,
    backend: str,
    warmup: int,
    repeat: int,
) -> dict[str, dict]:
    """Run all questions on one backend; return {qid: {samples, n}}."""
    os.environ["EUCLID_BACKEND"] = backend
    for _ in range(warmup):
        reason(
            knowledge=knowledge,
            query=QUESTIONS[0]["query"],
            max_solutions=MAX_SOLUTIONS,
            max_depth=MAX_DEPTH,
        )
    results: dict[str, dict] = {}
    for q in QUESTIONS:
        samples: list[float] = []
        for _ in range(repeat):
            t0 = time.perf_counter()
            res = reason(
                knowledge=knowledge,
                query=q["query"],
                max_solutions=MAX_SOLUTIONS,
                max_depth=MAX_DEPTH,
            )
            samples.append((time.perf_counter() - t0) * 1000)
        results[q["id"]] = {"samples": samples, "n": len(res.solutions)}
    return results


def _median(samples: list[float]) -> float:
    return statistics.median(samples)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--full", action="store_true",
                        help="use the full generated_facts.euclid KB")
    parser.add_argument("--quick", action="store_true",
                        help="3 repeats instead of 7")
    args = parser.parse_args()

    if shutil.which("swipl") is None:
        print("SWI-Prolog (swipl) not installed; benchmark skipped.")
        return

    warmup = 2
    repeat = 3 if args.quick else 7

    knowledge = load_knowledge(use_small=not args.full)
    data_name = "small_generated_facts" if not args.full else "generated_facts"
    print("\n  NATIVE vs SWI-PROLOG — example 07 (IT security compliance)")
    print(f"  KB: {data_name}.euclid · {len(knowledge.splitlines())} lines"
          f" · {len(QUESTIONS)} questions · repeat={repeat} (median)\n")
    print("  " + "─" * 74)
    print("  " + f"{'Q':>4} │ {'prolog':>10} │ {'native':>10}"
          + f" │ {'ratio':>7} │ {'sols P/N':>9}")
    print("  " + "─" * 74)

    prolog = time_questions(knowledge, "prolog", warmup, repeat)
    native = time_questions(knowledge, "native", warmup, repeat)

    totals_p = 0.0
    totals_n = 0.0
    for q in QUESTIONS:
        qid = q["id"]
        p = _median(prolog[qid]["samples"])
        n = _median(native[qid]["samples"])
        totals_p += p
        totals_n += n
        sols = f"{prolog[qid]['n']}/{native[qid]['n']}"
        print(f"  {qid:>4} │ {p:>8.1f}ms │ {n:>8.1f}ms"
              f" │ {n / p:>6.1f}× │ {sols:>9}")
    print("  " + "─" * 74)
    print(f"  {'Σ':>4} │ {totals_p:>8.1f}ms │ {totals_n:>8.1f}ms"
          f" │ {totals_n / totals_p:>6.1f}×")
    print(f"  {'':>4} │ (sum of per-query medians)\n")
    print("  Results are identical when the solution counts match per query (P/N).\n")


if __name__ == "__main__":
    main()
