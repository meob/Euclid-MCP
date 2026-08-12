"""
Solution-Cap Benchmark: prove the Prolog-side max_solutions cap stops work early.

A dense query (variable over all facts) is run on KBs of increasing size with a
fixed small ``max_solutions`` cap. If the cap is enforced in the engine, the
capped time stays roughly flat as the total solution count grows, while the
uncapped time scales with the number of solutions.

Usage:
    python benchmarks/solution_cap_benchmark.py             # full run
    python benchmarks/solution_cap_benchmark.py --quick     # small run
"""
import argparse
import shutil
import time

from euclid_mcp.models import KB
from euclid_mcp.prolog_server import PrologServer
from euclid_mcp.translator import build_query_snippet, kb_to_decls_clauses

SIZES = [1_000, 10_000, 100_000]
CAP = 5          # capped max_solutions
UNCAPPED = 1_000_000  # effectively-uncapped
REPEAT = 5
TIMEOUT = 60


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def build(size: int) -> tuple[list[str], list[str], str]:
    kb = KB(facts=[f"item({i})" for i in range(size)], rules=[])
    decls, clauses = kb_to_decls_clauses(kb)
    return decls, clauses, "item($x)"


def time_query(server: PrologServer, decls, clauses, query, cap, repeat) -> float:
    server.load(decls, clauses, timeout=TIMEOUT)
    snippet = build_query_snippet(query, max_solutions=cap)
    samples = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        server.query(snippet, timeout=TIMEOUT)
        samples.append((time.perf_counter() - t0) * 1000)
    return _mean(samples)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quick", action="store_true",
                        help="smaller KB sizes, 3 repeats")
    parser.add_argument("--repeat", type=int, default=REPEAT)
    parser.add_argument("--timeout", type=int, default=TIMEOUT)
    args = parser.parse_args()

    if shutil.which("swipl") is None:
        print("SWI-Prolog (swipl) not installed; benchmark skipped.")
        return

    sizes = [1_000, 10_000] if args.quick else SIZES
    repeat = 3 if args.quick else args.repeat

    server = PrologServer(restart_every=0)
    try:
        server.ping()
        print("\n  SOLUTION-CAP BENCHMARK — engine stops at max_solutions")
        print("  Query-phase only (KB loaded once); "
              f"KB sizes: {', '.join(str(s) for s in sizes)} facts · repeat={repeat}\n")
        print("  " + "─" * 70)
        print("  " + f"{'facts':>7} │ " + f"{'capped(5)':>10}"
              + " │ " + f"{'uncapped':>10}" + f" │ {'ratio':>7}")
        print("  " + "─" * 70)

        for size in sizes:
            decls, clauses, query = build(size)
            capped = time_query(server, decls, clauses, query, CAP, repeat)
            uncapped = time_query(server, decls, clauses, query, UNCAPPED, repeat)
            print(
                f"  {size:>7,} │ {capped:>9.1f}ms"
                f" │ {uncapped:>9.1f}ms"
                f" │ {uncapped / capped:>6.1f}×"
            )
        print("  " + "─" * 70)
        print(
            "  Capped time should stay ~flat as the KB grows; uncapped time grows "
            "with the\n  solution count. A rising ratio proves work stops early.\n"
        )
    finally:
        server.close()


if __name__ == "__main__":
    main()

