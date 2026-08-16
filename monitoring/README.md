# Euclid-MCP monitoring stack

Prometheus + Grafana + cAdvisor for the Euclid-MCP HTTP API. The API itself
exposes Prometheus metrics on `GET /metrics` (open, read-only, never carries
KB content) plus a deep `GET /health` that pings the Prolog engine.

## What is scraped

| Source | Metrics |
|--------|---------|
| `euclid-api:8080/metrics` | HTTP traffic, tool calls, engine lifecycle, solutions, auth failures, uptime |
| `cadvisor:8080/metrics` | per-container CPU / memory / network / I/O for `euclid-api` |

Metric reference (all prefixed `euclid_`):

| Metric | Type | Labels | Meaning |
|--------|------|--------|---------|
| `euclid_http_requests_total` | counter | `method`, `path`, `status` | HTTP requests by outcome |
| `euclid_http_request_duration_seconds` | histogram | `path` | HTTP latency |
| `euclid_solutions_total` | counter | `path` | solutions returned by reasoning endpoints |
| `euclid_auth_failures_total` | counter | — | rejected requests (401) |
| `euclid_process_uptime_seconds` | gauge | — | seconds since the API process started |
| `euclid_tool_calls_total` | counter | `tool` | MCP tool invocations (all entrypoints) |
| `euclid_tool_errors_total` | counter | `tool` | tool invocations that errored |
| `euclid_tool_call_duration_seconds` | histogram | `tool` | tool latency |
| `euclid_engine_requests_total` | counter | `command` | engine JSON-lines requests |
| `euclid_engine_restarts_total` | counter | `reason` | engine relaunches (`periodic`, `timeout`, `broken_pipe`) |
| `euclid_engine_timeouts_total` | counter | — | engine requests that hit the time limit |
| `euclid_kb_skipped_loads_total` | counter | — | loads skipped because the KB hash was unchanged |
| `euclid_kb_size` | gauge | `kind` | facts / rules loaded in the engine workspace |

## Usage

```bash
# 1. Start the API (from the repo root)
docker compose up -d euclid-api

# 2. Start the monitoring stack
docker compose -f monitoring/docker-compose.monitoring.yml up -d

# 3. Open
open http://localhost:9090   # Prometheus
open http://localhost:3000   # Grafana (default admin/admin, override GF_ADMIN_PASSWORD)
```

Verification:

```bash
curl -s localhost:8080/metrics | head
curl -s localhost:8080/health   # {"status":"ok","service":"euclid-mcp","engine":{...}}
```

## Scaling out

Both compose files attach to the shared `euclid-app` network, so you can
replicate the API and every replica exposes its own metrics:

```bash
docker compose up -d --scale euclid-api=3 euclid-api
```

Prometheus discovers each replica's `euclid-api:8080` (one target per
container, same static config — extend with `dns_sd_configs` or a load
balancer for dynamic discovery).

## Alerts

`prometheus/rules.yml` defines alert rules (EuclidDown, error rate, p99
latency, engine restart storm, memory pressure). They evaluate in Prometheus;
route them by pointing the `-alertmanager.url` flag (or Alertmanager config)
at your instance, or view them in Grafana → Alerting. Configure a contact
point in Grafana (email, Slack, webhook, …) to get notified.

## Deep health checks

`GET /health` now probes the engine itself:

- 200 `{"status":"ok", "engine":{"backend":"prolog", "reachable":true,
  "facts":N, "rules":M, "requests_since_restart":K}}` — engine alive.
- 200 with `engine.facts = null` — cold process, engine not started yet (it
  starts lazily on the first request; still healthy).
- 503 `{"status":"degraded", "engine":{"reachable":false}}` — an engine
  process exists but does not answer (wedged; the next request relaunches it
  from a clean state).
- 200 with `engine.backend="native"` — native backend, no engine process.

Point the load balancer / orchestrator at `/health` (not just TCP) so
instances with a wedged engine are taken out of rotation and restarted by
the healthcheck (`restart: unless-stopped` + the docker-compose healthcheck).

## Tearing down

```bash
docker compose -f monitoring/docker-compose.monitoring.yml down -v
```
