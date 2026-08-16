# Benchmark 8 — Remote API mode + monitoring surface (v0.4.1)

- **Script:** `benchmarks/euclid_bench.py --api-url URL`
- **Run date:** 2026-08-16
- **Environment:** local `integrations/euclid_api.py` on port 8999
  (SWI-Prolog 10.0.2 arm64-darwin, Python 3.12.11, `.venv`), remote client
  `--api-url http://127.0.0.1:8999`

## What it measures

`euclid_bench.py` has a third mode: instead of spawning the engine
(`direct`) or an in-process `HTTPServer` (`api`), `--api-url URL` hammers an
**already-running** Euclid-MCP API — the containerized deployment from
`docker-compose.yml`, or any replica behind the load balancer. The engine then
lives in the remote process (including a containerized `swipl`), which is the
real production shape.

The final report reads **engine restarts** and **process uptime** from the
API's `GET /metrics` endpoint — the same Prometheus text surface the
monitoring stack scrapes (`monitoring/`).

## Method

- `--workers 4 --duration 8s --tags 2 --facts 20`: four concurrent clients
  POST tagged KBs to `/reason` and verify each response carries exactly its
  own KB's solutions (no mixing, no pollution — the atomicity guarantee must
  hold over real HTTP).
- Restarts/uptime are parsed from `GET /metrics`
  (`euclid_engine_restarts_total{...}` summed, `euclid_process_uptime_seconds`).

## Results

```
mode=api workers=4 duration=8.2s
iterations=5,394    throughput=658.7 req/s
latency   mean= 5.9ms   p50= 5.0ms   p95= 6.0ms   p99= 8.4ms
api_uptime=10s
mismatches=0    exceptions=0    engine_restarts=10
RESULT: PASS
```

- **658.7 req/s** through real TCP to a remote API (the local API mode logged
  ~194 req/s at workers=4 on the older run — throughput now includes the
  engine periodic restarts, which the report surfaces).
- **0 failures** across 5 394 requests: no response mixing, no KB pollution.
- **10 engine restarts** reported from `/metrics` — the periodic
  `restart_every=1000` window firing under sustained load, visible without any
  container introspection.
- `api_uptime=10s` matches wall-clock for the remote process — the gauge works
  end to end and is the same one Prometheus scrapes.

## Why this matters

1. **Deployment-shaped benchmarking.** `direct` proves the engine core, `api`
   proves the in-process HTTP path; `--api-url` proves the shipped artifact —
   the exact image/container/network a production fleet runs. A broken image,
   a missing `swipl` on `PATH` inside the container, or a `ports:`/network
   misconfiguration all fail here before they reach users.
2. **Observability as the benchmark's eyes.** The report's restart/uptime
   numbers come from the public `/metrics` endpoint — the benchmark and the
   monitoring stack (Prometheus rules `EuclidEngineRestarting`, uptime dashboards)
   read the same source of truth.
3. **No special privileges.** The remote runner needs only HTTP: it is the
   natural way to soak-test a staging/QA deployment without shelling into it.

## Consequent implementation choices

- `--api-url` implies `--mode api` and does **not** require a local `swipl`
  (the engine lives remotely), so it can run from a laptop or CI host.
- The runner parses the Prometheus text format minimally (name/value lines);
  it reads only the two numbers the report needs, keeping the dependency on
  the monitoring surface explicit and tiny.
