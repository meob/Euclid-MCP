# Euclid-MCP in Production

Reference architecture and operational guidance for running Euclid-MCP behind a
load balancer (HTTP API mode), with scalability, security, and monitoring notes.

Euclid-MCP is **stateless by design**: every request carries its own knowledge
base (or uses the preloaded one), instances share nothing, and there is no
session affinity. This makes a battery of replicas behind a reverse proxy a
sufficient production architecture once the in-process hardening is in place
(see [Security hardening](#security-hardening) below).

## Architecture

```
                    ┌──────────────┐   ┌──────────────────────┐
  n8n/Zapier/Make ─▶│   HAProxy    │──▶│ replica 1: euclid-api │──▶ swipl
  (TLS, rate limit,│ (LB + health │  ┌┴──────────────────────┐
   timeouts)        │  + circuit   )──▶│ replica 2: euclid-api │──▶ swipl
                    │  breaking)   │  └──────────────────────┘
                    └──────────────┘   replica N ...
```

- Each replica runs `integrations/euclid_api.py` (or the Docker image) and owns
  a single persistent `swipl` engine process.
- Any replica can serve any request: the KB travels with the request.
- A replica handles one request at a time (serialized by `PrologServer`'s lock);
  concurrency comes from horizontal scale-out. An in-process engine pool is on
  the roadmap (see `IDEAS.md`).

## Prerequisites (already in the codebase)

The limits below are enforced in-process; the proxy layer only adds edge
defenses on top:

| Guard | Value | Where |
|---|---|---|
| Knowledge size | 500 000 bytes | `server.MAX_KNOWLEDGE_LENGTH` |
| Query size | 5 000 characters | `server.MAX_QUERY_LENGTH` |
| Max solutions | 1000 (engine stops early) | `server.MAX_SOLUTIONS_LIMIT` |
| Max proof depth | 500 | `server.MAX_DEPTH_LIMIT` |
| Engine per-call timeout | 30 s (`status:timeout`) | `prolog_engine.pl` |
| Engine restart | every 1000 requests + after timeout | `prolog_server.PrologServer(restart_every=...)` |
| Input sanitizer | directives / dangerous built-ins | `euclid_mcp/sanitizer.py` (via `parse`) |

## Deployment

### Docker

```bash
docker compose up --scale euclid-api=3 -d
```

Set per-container limits so one pathological query cannot starve the host:

```yaml
services:
  euclid-api:
    image: euclid-mcp:latest
    command: ["python3", "integrations/euclid_api.py", "--port", "8080"]
    environment:
      EUCLID_LOG_LEVEL: INFO
      # Same file MUST be preloaded on every replica for consistent answers:
      EUCLID_KB_PATH: /kb/policies.euclid
    volumes:
      - ./policies.euclid:/kb/policies.euclid:ro
    mem_limit: 512m
    cpus: "1.0"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
```

> `--scale` works with `docker compose up`, but when scaling **remove the
> `ports:` mapping** from the `euclid-api` service (the load balancer reaches the
> replicas over the compose network; a published host port would conflict across
> replicas). In Swarm or Kubernetes, deploy the same container as a
> `Service` / `Deployment` with `replicas: N`.

### Preloaded-KB consistency (important)

`EUCLID_KB_PATH` is read **at startup** and validated with `check_kb` (fail-fast).
If you preload a KB, the **same file must be present on every replica**;
otherwise replicas will answer differently for the same request. Either bake it
into the image or mount the same read-only file everywhere.

## Load balancing (HAProxy reference)

`docs/PLANS/security-hardening.md` defines P2 as: health check on the engine
`ping`/`/health`, rate limiting at the edge, backend timeouts + circuit breaking
on `status:timeout`, per-container CPU/memory limits, and a max body size.

Reference `haproxy.cfg`:

```haproxy
global
    log stdout format raw local0
    maxconn 4096

defaults
    mode http
    log global
    option httplog
    option dontlognull
    timeout connect 5s
    timeout client  30s
    timeout server  35s          # > 30s engine budget + small margin
    timeout http-request 35s

frontend fe_euclid
    bind :443 ssl crt /etc/haproxy/certs/euclid.pem
    bind :80
    http-request redirect scheme https unless { ssl_fc }

    # Edge rate limit: 100 requests / 10 s per client IP
    stick-table type ip size 100k expire 60s store http_req_rate(10s)
    http-request track-sc0 src
    http-request deny deny_status 429 if { sc_http_req_rate(0) gt 100 }

    # Max request body: 1 MiB (the app itself caps knowledge at 500 KB)
    http-request deny deny_status 413 \
        if { req.hdr(content-length),str2int gt 1048576 }

    use_backend be_euclid_api

backend be_euclid_api
    option httpchk GET /health
    default-server inter 5s fall 3 rise 2 maxconn 32
    server euclid-1 euclid-1:8080 check
    server euclid-2 euclid-2:8080 check
    server euclid-3 euclid-3:8080 check
```

Behavior notes:

- **Health check**: `GET /health` returns `{"status": "ok", "service": "euclid-mcp"}`.
  HAProxy removes a replica after `fall 3` consecutive failures and re-adds it
  after `rise 2` successes.
- **Circuit breaking**: a pathological query raises `status:timeout` after 30 s;
  the replica is dropped and restarted by the engine's own restart policy. The
  proxy's `timeout server` + health checks keep the rest of the fleet healthy.
  **The proxy is NOT a substitute for the in-process hardening** — it makes each
  backend recoverable, it does not bound a single backend's work.
- **Rate limiting** is at the edge so a burst cannot even reach the replicas.

## Security hardening

The security model is defense-in-depth:

1. **Real boundary = the meta-interpreter** (`prolog_engine.pl`): user goals are
   only matched via `clause/2`; the only goals executed directly are arithmetic
   comparisons from a closed operator set. The engine never builds or `call/1`s
   arbitrary terms.
2. **Sanitizer** (`sanitizer.py`): rejects Prolog directives and dangerous
   built-ins in both knowledge and query, before translation. Applied to KB text
   and to the `query` parameter.
3. **Bounded work**: per-call timeout (30 s), Prolog-side solution cap
   (`max_solutions`), knowledge/query length caps, and depth limit.
4. **Bounded memory**: the engine restarts every 1000 requests and after every
   timeout, capping SWI's atom table and stack growth.

At the network edge, additionally:

- Terminate TLS at the load balancer; use `X-Request-Id` (echoed on responses)
  to correlate requests across replicas and logs.
- Authenticate clients (API key / mTLS) if the API is reachable outside a
  trusted network; the HTTP API itself has no auth by design — it is meant for
  internal automation (n8n, Zapier, Make).
- Keep `CORS` as needed: the API sets `Access-Control-Allow-Origin: *`.

## Monitoring & observability

See `docs/MONITORING.md` for the MCP Inspector and per-call log details.

### Logs

Enable structured logs:

```bash
EUCLID_LOG_LEVEL=INFO python3 integrations/euclid_api.py --port 8080
```

Every tool call emits `tool=... elapsed_ms=... solutions=...` (or `error=...`).
The HTTP API access log includes `request_id=...` when the client sent
`X-Request-Id`.

### Metrics to watch

| Signal | Good | Investigate |
|---|---|---|
| `elapsed_ms` per call | < 100 ms steady-state | growth in p95/p99 |
| `status:timeout` in engine logs | 0 | pathological queries reaching the 30 s cap |
| Engine restarts (`restart_every=1000`, after-timeout) | expected, cheap | frequent timeouts → fix queries, not restart policy |
| `/health` failures at the proxy | all replicas up | replica crash / swipl not launched |
| HTTP 429 at the edge | none for legitimate traffic | tighten rate limit or scale out |
| Replica memory (e.g. `mem_limit`) | well under limit | long-lived drift → rely on restart policy |

## Troubleshooting

- **Every request times out**: check the replicas actually launch `swipl`
  (`swipl` must be on `PATH` inside the container). Run
  `docker compose run --rm euclid-mcp python3 -c "from euclid_mcp.server import reason; ..."`
  to smoke-test the image.
- **Inconsistent answers across replicas**: preloaded-KB mismatch — verify
  `EUCLID_KB_PATH` resolves to the same file everywhere.
- **A slow client holds a replica**: the engine is single-request at a time; set
  `timeout client` at the proxy and consider the in-process engine pool roadmap
  item (`IDEAS.md`) for concurrent requests within one instance.

## References

- Plan + hardening review: `docs/PLANS/security-hardening.md`
- Internal monitoring: `docs/MONITORING.md`
- HTTP API endpoints: `integrations/README.md`, `integrations/euclid_api.py`
- Roadmap (engine pool, threaded HTTP API): `IDEAS.md`
- Benchmarks: `benchmarks/BENCHMARKS.md`, `benchmarks/solution_cap_benchmark.py`
