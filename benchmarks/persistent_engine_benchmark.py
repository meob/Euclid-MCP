"""
Persistent Engine Benchmark: stateless subprocess vs persistent engine.

Replicates the pre-v0.3.0 stateless path (write ``to_prolog()`` output to a
temp file, spawn ``swipl -q -f <file> -t halt``, parse the JSON solution
lines) and compares it against the persistent engine
(``euclid_mcp.prolog_bridge.execute`` over a single long-lived swipl process
connected by a JSON-lines pipe).

Reports cold-start and steady-state per-query timings across KB sizes and
query shapes, plus the speedup factor of the persistent path.

Usage:
    python benchmarks/persistent_engine_benchmark.py            # full run
    python benchmarks/persistent_engine_benchmark.py --quick    # small run
"""
import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time

from euclid_mcp.models import KB
from euclid_mcp.prolog_bridge import execute as engine_execute
from euclid_mcp.translator import kb_to_decls_clauses, to_prolog

MAX_SOLUTIONS = 100_000

SIZES = [100, 1_000, 10_000]
REPEAT = 10

QUERIES = [
    ("ground", "user(u0042)", "single ground fact"),
    ("scan", "user($who)", "all facts (variable)"),
]


def _find_swipl() -> str:
    path = shutil.which("swipl")
    return path or "swipl"


SWIPL = _find_swipl()


def build_kb(size: int) -> KB:
    return KB(facts=[f"user(u{i:04d})" for i in range(size)], rules=[])


def legacy_execute(kb: KB, query: str, timeout: int = 120) -> int:
    """Stateless path: one swipl subprocess per call (pre-v0.3.0 behavior)."""
    kb.query = query
    code = to_prolog(kb, max_solutions=MAX_SOLUTIONS)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".pl", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(code)
        tmp_name = tmp.name
    try:
        proc = subprocess.run(
            [SWIPL, "-q", "-f", tmp_name, "-t", "halt"],
            capture_output=True, text=True, timeout=timeout,
        )
        count = 0
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and "solution" in data:
                count += 1
        return count
    finally:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass


def persistent_execute(kb: KB, query: str, timeout: int = 120) -> int:
    """Persistent path: load + query on a long-lived engine process."""
    decls, clauses = kb_to_decls_clauses(kb)
    solutions = engine_execute(
        decls, clauses, query,
        max_solutions=MAX_SOLUTIONS, timeout=timeout,
    )
    return len(solutions)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def run_case(runner, kb: KB, query: str, repeat: int, timeout: int) -> dict:
    cold_start = time.perf_counter()
    runner(kb, query, timeout)
    cold_ms = (time.perf_counter() - cold_start) * 1000

    samples = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        runner(kb, query, timeout)
        samples.append((time.perf_counter() - t0) * 1000)
    return {"cold_ms": cold_ms, "avg_ms": _mean(samples)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quick", action="store_true",
                        help="small sizes (100/1k facts), 3 repeats")
    parser.add_argument("--repeat", type=int, default=REPEAT)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    sizes = [100, 1_000] if args.quick else SIZES
    repeat = 3 if args.quick else args.repeat

    print("\n  PERSISTENT ENGINE BENCHMARK — stateless vs persistent")
    print(f"  KB sizes: {', '.join(str(s) for s in sizes)} facts · repeat={repeat}\n")

    rows = []
    for size in sizes:
        kb = build_kb(size)
        for qname, query, _desc in QUERIES:
            legacy = run_case(legacy_execute, kb, query, repeat, args.timeout)
            persist = run_case(persistent_execute, kb, query, repeat, args.timeout)
            rows.append({
                "size": size, "query": qname,
                "legacy_cold": legacy["cold_ms"],
                "legacy_avg": legacy["avg_ms"],
                "persist_cold": persist["cold_ms"],
                "persist_avg": persist["avg_ms"],
                "speedup": legacy["avg_ms"] / persist["avg_ms"],
            })

    # ── report ──
    header = (
        f"{'facts':>6} {'query':<7}"
        "│ " + f"{'legacy avg':>8}"
        " │ " + f"{'persist avg':>10}"
        " │ " + f"{'speedup':>7}"
        " │ " + f"{'legacy cold':>11}"
        " │ " + f"{'persist cold':>12}"
    )
    print("  " + "─" * 78)
    print("  " + header)
    print("  " + "─" * 78)

    speedups = []
    for r in rows:
        print(
            f"  {r['size']:>6} {r['query']:<7}" +
            f"│ {r['legacy_avg']:>8.1f}" +
            f" │ {r['persist_avg']:>10.1f}" +
            f" │ {r['speedup']:>6.1f}×" +
            f" │ {r['legacy_cold']:>10.0f}ms" +
            f" │ {r['persist_cold']:>11.0f}ms"
        )
        speedups.append(r["speedup"])
    print("  " + "─" * 78)

    overall = sum(speedups) / len(speedups)
    print(
        f"\n  Steady-state speedup (mean across cases): {overall:.1f}×\n"
        f"  Persistent cold start includes engine launch; steady-state per-call\n"
        f"  cost is dominated by the KB workspace reload over the pipe.\n"
    )


if __name__ == "__main__":
    main()
