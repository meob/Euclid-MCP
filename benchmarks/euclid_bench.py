"""
Euclid Stress & Soak Benchmark: does the persistent engine stay correct under load?

Each request loads a *tagged* knowledge base (``item(<tag>, <x>)`` facts plus
an ``answer/2`` rule) and must return exactly that KB's solutions. Any response
whose solutions come from a different tag — or that differs from the expected
set — is request mixing or workspace pollution and fails the run. The preload
semantics are covered implicitly: the tagged KBs rotate in a fixed order, so a
KB that is "polluted" by the previous one can never verify.

Modes
-----
direct (default) — hammers the persistent engine (``PrologServer``) directly.
    ``--workers N`` must always pass: ``load``+``query`` run as a single
    atomically-locked exchange (``PrologServer.load_and_query``), so concurrent
    workers cannot interleave one workspace between another request's load and
    query. This benchmark is the regression detector for that atomicity.
api              — stresses the real HTTP API (``HTTPServer``, single-threaded).
    Concurrent clients are serialized by the accept loop, so queuing is
    exercised and correctness must hold at any ``--workers`` value.

Usage:
    python benchmarks/euclid_bench.py                              # 30 s soak
    python benchmarks/euclid_bench.py --duration 3600 --workers 1  # 1 h soak
    python benchmarks/euclid_bench.py --mode api --workers 8       # HTTP load
    python benchmarks/euclid_bench.py --iterations 5000 --workers 4
"""
import argparse
import hashlib
import json
import shutil
import statistics
import sys
import threading
import time
from pathlib import Path

from euclid_mcp.models import KB
from euclid_mcp.prolog_server import PrologServer
from euclid_mcp.translator import build_query_snippet, kb_to_decls_clauses

ROOT = Path(__file__).resolve().parent.parent
MAX_SOLUTIONS = 1000
TIMEOUT = 30


def _mean(values: list[float]) -> float:
    return statistics.mean(values) if values else 0.0


def _percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(int(q * len(sorted_values)), len(sorted_values) - 1)
    return sorted_values[idx]


# ── tagged knowledge bases ────────────────────────────────────────────────

def build_direct_kb(tag: int, n_facts: int) -> tuple[list[str], list[str]]:
    kb = KB(
        facts=[f"item({tag},{x})" for x in range(n_facts)],
        rules=["answer($t,$x) IF item($t,$x)"],
        query="answer($t,$x)",
    )
    return kb_to_decls_clauses(kb)


def build_api_kb_text(tag: int, n_facts: int) -> str:
    lines = [f"item({tag},{x})" for x in range(n_facts)]
    lines.append("answer($t,$x) IF item($t,$x)")
    lines.append("? answer($t,$x)")
    return "\n".join(lines)


def expected_set(tag: int, n_facts: int) -> set[tuple[int, int]]:
    return {(tag, x) for x in range(n_facts)}


# ── runners ───────────────────────────────────────────────────────────────

class _CountingServer(PrologServer):
    """PrologServer that counts engine launches (to report periodic restarts)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.launches = 0

    def _launch(self) -> None:
        super()._launch()
        self.launches += 1


class DirectRunner:
    def __init__(self, restart_every: int):
        self.server = _CountingServer(restart_every=restart_every)
        self.server.ping()

    @property
    def restarts(self) -> int:
        return max(0, self.server.launches - 1)

    def request(self, tag: int, n_facts: int) -> bool:
        decls, clauses = build_direct_kb(tag, n_facts)
        # Content-derived fingerprint: lets the engine skip the workspace
        # rebuild when the same KB is loaded again (as server.py does).
        kb_hash = hashlib.sha256(
            ("\n".join(decls) + "\0" + "\n".join(clauses)).encode()
        ).hexdigest()
        snippet = build_query_snippet(
            "answer($t,$x)", max_depth=30, max_solutions=MAX_SOLUTIONS
        )
        # load+query is one atomic (locked) exchange — no workspace mixing
        # between concurrent requests.
        resp = self.server.load_and_query(
            decls, clauses, snippet, timeout=TIMEOUT, kb_hash=kb_hash
        )
        got = {
            (s["solution"]["t"], s["solution"]["x"])
            for s in resp.get("solutions", [])
        }
        return got == expected_set(tag, n_facts)

    def close(self) -> None:
        self.server.close()


class ApiRunner:
    def __init__(self):
        sys.path.insert(0, str(ROOT))
        from http.server import HTTPServer

        from integrations.euclid_api import ReasonHandler

        self._server = HTTPServer(("127.0.0.1", 0), ReasonHandler)
        self._port = self._server.server_address[1]
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True
        )
        self._thread.start()

    @property
    def restarts(self) -> int:
        return 0  # the API server is a separate process boundary

    def request(self, tag: int, n_facts: int) -> bool:
        from http.client import HTTPConnection

        body = json.dumps({
            "knowledge": build_api_kb_text(tag, n_facts),
            "max_solutions": MAX_SOLUTIONS,
        })
        conn = HTTPConnection("127.0.0.1", self._port, timeout=TIMEOUT)
        status = 0
        data: dict = {}
        try:
            conn.request(
                "POST", "/reason", body=body,
                headers={"Content-Type": "application/json"},
            )
            resp = conn.getresponse()
            status = resp.status
            data = json.loads(resp.read().decode())
        finally:
            conn.close()
        if status != 200 or "solutions" not in data:
            raise RuntimeError(f"HTTP {status}: {data.get('error')}")
        got = {
            (s["substitutions"]["t"], s["substitutions"]["x"])
            for s in data["solutions"]
        }
        return got == expected_set(tag, n_facts)

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


class _Stats:
    __slots__ = ("iterations", "mismatches", "exceptions", "latency", "errors")

    def __init__(self):
        self.iterations = 0
        self.mismatches = 0
        self.exceptions = 0
        self.latency: list[float] = []
        self.errors: list[str] = []

    def merge(self, other: "_Stats") -> None:
        self.iterations += other.iterations
        self.mismatches += other.mismatches
        self.exceptions += other.exceptions
        self.latency.extend(other.latency)
        self.errors.extend(other.errors)


def _worker(
    runner,
    worker_id: int,
    tags: list[int],
    n_facts: int,
    iterations: int,
    deadline,
    stats: _Stats,
) -> None:
    count = 0
    while True:
        if deadline[0] is not None and time.monotonic() > deadline[0]:
            break
        if iterations and count >= iterations:
            break
        tag = tags[count % len(tags)]
        t0 = time.perf_counter()
        try:
            ok = runner.request(tag, n_facts)
            stats.latency.append((time.perf_counter() - t0) * 1000)
            stats.iterations += 1
            if not ok:
                stats.mismatches += 1
                if len(stats.errors) < 5:
                    stats.errors.append(
                        f"worker{worker_id}: mixing/pollution on tag {tag}"
                    )
        except Exception as exc:
            stats.exceptions += 1
            stats.latency.append((time.perf_counter() - t0) * 1000)
            if len(stats.errors) < 5:
                stats.errors.append(
                    f"worker{worker_id}: {type(exc).__name__}: {exc}"
                )
        count += 1


# ── report ────────────────────────────────────────────────────────────────

def _print_report(
    args, total: int, mismatches: int, exceptions: int, restarts: int,
    latency: list[float], errors: list[str], elapsed: float,
) -> None:
    sorted_latency = sorted(latency)
    rps = total / elapsed if elapsed else 0.0
    ok = mismatches == 0 and exceptions == 0
    verdict = "PASS" if ok else "FAIL"

    print("\n" + "  " + "─" * 68)
    print(f"  RESULT: {verdict}")
    print("  " + "─" * 68)
    print(f"  mode={args.mode} workers={args.workers} duration={elapsed:.1f}s")
    print(f"  iterations={total:,}    throughput={rps:.1f} req/s")
    print(
        f"  latency   mean={_mean(sorted_latency):7.1f}ms"
        f"   p50={_percentile(sorted_latency, 0.50):7.1f}ms"
        f"   p95={_percentile(sorted_latency, 0.95):7.1f}ms"
        f"   p99={_percentile(sorted_latency, 0.99):7.1f}ms"
    )
    print(f"  mismatches={mismatches:,}    exceptions={exceptions:,}"
          f"    engine_restarts={restarts}")
    for err in errors[:5]:
        print(f"    - {err}")
    print("  " + "─" * 68)

    if ok:
        print("  No response mixing, no KB pollution, no engine errors.\n")
    else:
        print(
            "  Response mixing / pollution detected — inspect the errors above.\n"
        )


# ── main ──────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=["direct", "api"], default="direct",
                        help="engine core (direct) or HTTP API (api)")
    parser.add_argument("--workers", type=int, default=1,
                        help="concurrent worker threads")
    parser.add_argument("--duration", type=float, default=30.0,
                        help="max seconds to run (0 = no time cap)")
    parser.add_argument("--iterations", type=int, default=0,
                        help="max requests per worker (0 = no count cap)")
    parser.add_argument("--tags", type=int, default=4,
                        help="distinct tagged KBs to rotate")
    parser.add_argument("--facts", type=int, default=50,
                        help="facts per tagged KB")
    parser.add_argument("--restart-every", type=int, default=1000,
                        help="engine periodic restart window (direct mode)")
    parser.add_argument("--progress", type=float, default=5.0,
                        help="seconds between progress lines (0 = off)")
    args = parser.parse_args()

    if shutil.which("swipl") is None:
        print("SWI-Prolog (swipl) not installed; benchmark skipped.")
        return

    runner = DirectRunner(restart_every=args.restart_every) if args.mode == "direct" \
        else ApiRunner()
    tags = list(range(args.tags))

    deadline = [time.monotonic() + args.duration if args.duration > 0 else None]
    stats = [_Stats() for _ in range(args.workers)]
    threads = [
        threading.Thread(
            target=_worker,
            args=(runner, i, tags, args.facts, args.iterations, deadline, stats[i]),
        )
        for i in range(args.workers)
    ]

    print("\n  EUCLID STRESS & SOAK BENCHMARK")
    print(
        f"  mode={args.mode} workers={args.workers} tags={args.tags}"
        f" facts={args.facts}"
        f" duration={args.duration}s iterations/worker={args.iterations}"
    )
    if args.mode == "direct":
        print(f"  engine restart_every={args.restart_every} requests")
    print("  " + "─" * 68)

    started = time.monotonic()
    for t in threads:
        t.start()

    try:
        last_progress = time.monotonic()
        while any(t.is_alive() for t in threads):
            time.sleep(0.2)
            now = time.monotonic()
            if args.progress and now - last_progress >= args.progress:
                total_now = sum(s.iterations for s in stats)
                bad = sum(s.mismatches for s in stats) + sum(
                    s.exceptions for s in stats
                )
                print(
                    f"  [{now - started:6.1f}s] iterations={total_now:,}"
                    f"  failures={bad}",
                    flush=True,
                )
                last_progress = now
    except KeyboardInterrupt:
        print("\n  Interrupted — reporting partial results.")
        deadline[0] = time.monotonic()
    finally:
        for t in threads:
            t.join(timeout=10)
        runner.close()

    elapsed = time.monotonic() - started
    merged = _Stats()
    for s in stats:
        merged.merge(s)

    _print_report(
        args, merged.iterations, merged.mismatches, merged.exceptions,
        runner.restarts, merged.latency, merged.errors, elapsed,
    )
    if merged.mismatches or merged.exceptions:
        sys.exit(1)


if __name__ == "__main__":
    main()
