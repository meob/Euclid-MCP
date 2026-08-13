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
                    ┌──────────────┐    ┌───────────────────────┐
  n8n/Zapier/Make ─▶│   HAProxy    │───▶│ replica 1: euclid-api │──▶ swipl
  (TLS, rate limit, │ (LB + health │   ┌┴──────────────────────┐
   timeouts)        │  + circuit   )──▶│ replica 2: euclid-api │──▶ swipl
                    │  breaking)   │   └───────────────────────┘
                    └──────────────┘   replica N ...
```

- Each replica runs `integrations/euclid_api.py` (or the Docker image) and owns
  a single persistent `swipl` engine process.
- Any replica can serve any request: the KB travels with the request.
- A replica handles one request at a time (serialized by `PrologServer`'s lock);
  concurrency comes from horizontal scale-out.

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

The edge hardening — health checks on `/health`, rate limiting, backend
timeouts + circuit breaking on `status:timeout`, per-container CPU/memory
limits, and a max body size — is documented in the sections above and the
reference config below.

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
- **Authenticate every client.** The HTTP API ships with opt-in API-key auth
  and TLS (see [Authentication & TLS](#authentication--tls) below). Plain HTTP
  with no auth is only safe on a trusted loopback, never over the network.
- Keep `CORS` as needed: the API sets `Access-Control-Allow-Origin: *`.

## Authentication & TLS

Plain HTTP is **not sufficient** for remote access: anyone who can reach the
port can query any KB or hammer the engine, and credentials (or the KBs
themselves) travel in cleartext. Remote exposure requires **HTTPS
(encryption) + strong authentication**. SWI-Prolog needs no extra protection:
it only listens on the container's local JSON-lines pipe, so guarding the API
boundary guards the whole engine.

The API (`integrations/euclid_api.py`) supports both directly, or you can
terminate TLS at the load balancer (HAProxy) and keep the API on plain HTTP
inside the trusted network.

### API-key authentication (opt-in)

Set `EUCLID_API_KEY` (or `--api-key`):

```bash
export EUCLID_API_KEY="$(openssl rand -hex 32)"
python3 integrations/euclid_api.py --api-key "$EUCLID_API_KEY" --port 8080
```

Every POST must then carry the key; otherwise the API answers `401`:

```bash
curl -s https://host:8080/reason \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $EUCLID_API_KEY" \
  -d '{"knowledge": "red(apple)\n? red($x)"}'
```

- The comparison is **constant-time** (`hmac.compare_digest`), so timing cannot
  leak the key.
- `GET /health` stays open so load balancers can probe replicas.
- Without a key the API logs a startup warning and runs open — fine on a
  trusted loopback, not when exposed.
- **An API key over plain HTTP is not enough**: it can be read in transit.
  Always pair it with HTTPS (below).

### TLS

Terminate TLS at the load balancer (the reference `haproxy.cfg` already binds
`:443 ssl`), **or** let the API serve HTTPS directly:

```bash
python3 integrations/euclid_api.py \
    --certfile /etc/euclid/cert.pem \
    --keyfile  /etc/euclid/key.pem \
    --port 8080
```

Env-var equivalent: `EUCLID_TLS_CERT` / `EUCLID_TLS_KEY`. Use a certificate
from your internal CA (or Let's Encrypt); self-signed certs force clients to
disable verification. In Docker:

```yaml
services:
  euclid-api:
    image: euclid-mcp:latest
    command: ["python3", "integrations/euclid_api.py", "--port", "8080"]
    environment:
      EUCLID_API_KEY: ${EUCLID_API_KEY}
      EUCLID_TLS_CERT: /etc/euclid/cert.pem
      EUCLID_TLS_KEY: /etc/euclid/key.pem
    volumes:
      - ./certs:/etc/euclid:ro
```

### Stronger alternatives (edge)

- **mTLS** at the load balancer: the HAProxy terminates TLS and validates the
  client certificate before the request reaches the API. With mTLS you can
  leave the API-key off (the LB is the only allowed client) or keep both.
- **OIDC / SSO** at the edge (Authelia, Keycloak) for human users; the API
  itself stays API-key-only.

### Recommended production posture

| Exposure | HTTPS | Auth | Notes |
|----------|-------|------|-------|
| Loopback only (`localhost`) | optional | optional | default; safe for local automation |
| Trusted internal network | optional | API key | terminate TLS at the LB if in place |
| Internet / untrusted network | **required** | API key **and/or mTLS** | never plain HTTP, never no-auth |

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
| HTTP 401 from the API | none (clients hold the key) | check the client secret / key rotation |
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
  item for concurrent requests within one instance.

## References

- Internal monitoring: `docs/MONITORING.md`
- HTTP API endpoints: `integrations/README.md`, `integrations/euclid_api.py`
- Benchmarks: `benchmarks/BENCHMARKS.md`, `benchmarks/solution_cap_benchmark.py`
