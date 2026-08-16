# IDEAS


## Principles
1. The LLM understands language
2. Euclid performs inference
3. Euclid IR is backend-independent
4. The backend is replaceable
5. Every answer must be verifiable
6. Proofs are first-class outputs

## Current tools
- `reason` — main deduction with proof trees
- `diagnose` — query analysis (why/why_not/what_needs)
- `what_if` — scenario testing with fact additions/removals
- `check_kb` — knowledge base validation

## Deployment
- Docker image (`swipl:stable` base) — MCP stdio + HTTP API modes


## NON GOALs
Euclid is not trying to:
- replace LLMs
- become a Prolog implementation
- become a planner
- become a knowledge graph
- become a vector database
- compete with RAG
- understand natural language


## Future ideas

The following ideas are not approved and maybe they will not be implemented

### Observability — (DONE — implemented in v0.4.1)

Full record in the session notes; implemented as approved:

1. **`euclid_mcp/metrics.py`** — stdlib-only `Counter`/`Gauge`/`Histogram`
   (fixed buckets) + `render()` in the Prometheus text exposition format.
   Metrics auto-register on construction; no `pyproject.toml` deps added.
2. **Instrumentation**
   - `prolog_server.py`: `euclid_engine_requests_total{command}`,
     `euclid_engine_restarts_total` (reasons: `periodic`/`timeout`/
     `broken_pipe`), `euclid_engine_timeouts_total`,
     `euclid_kb_skipped_loads_total`, gauge `euclid_kb_size{kind}`.
   - `server.py` (`_log_call`): `euclid_tool_calls_total{tool}`,
     `euclid_tool_errors_total{tool}`,
     `euclid_tool_call_duration_seconds{tool}` (also covers MCP stdio mode).
   - `integrations/euclid_api.py`: `GET /metrics` (open, read-only, never
     carries KB data) + per-request `euclid_http_requests_total{method,path,
     status}`, duration histogram per path, `euclid_solutions_total{path}`,
     `euclid_auth_failures_total`, `euclid_process_uptime_seconds`.
3. **Deep `/health` + graceful shutdown** — `/health` pings the engine and
   returns `stats` (`facts`, `rules`, `requests_since_restart`): `200` with an
   `engine` section (`reachable:true`, facts `null` on a cold process — the
   engine starts lazily), `503` only when an engine process exists but does
   not answer (wedged). SIGTERM/SIGINT handler: `server.shutdown()` (in a
   thread) + `server_close()` + `prolog_bridge.close()` so no `swipl` process
   is orphaned.
4. **`monitoring/` stack** — `docker-compose.monitoring.yml`
   (prometheus + grafana + cadvisor, attached to the shared `euclid-app`
   network; with `--scale` every replica exposes its own `/metrics`);
   `prometheus/prometheus.yml` (scrape euclid-api:8080/metrics + cadvisor) and
   `rules.yml` alerts (EuclidDown, error rate, p99 latency, engine restart
   spike, memory near limit); `grafana/provisioning/` datasource +
   `euclid.json` dashboard with HTTP API / Engine / Container (cAdvisor
   CPU-mem-net-IO) rows; `monitoring/README.md` (production + benchmark use).
5. **`euclid_bench.py`** — new `--api-url http://host:port` hammers the real
   (containerized) API instead of the in-process server (no local `swipl`
   needed); the final report reads engine restarts + process uptime from the
   API's `GET /metrics`.
6. **Tests** — `tests/test_metrics.py` (16 tests), `tests/test_api.py`
   (`/metrics`, deep `/health`, counters/gauge via scrape), and
   `tests/test_prolog_server.py` + `tests/test_prolog_bridge.py`
   (restart/timeout/skipped counters, `health_info`, `close()` idempotency).
7. **Docs & version** — `docs/MONITORING.md` Mode C, `docs/PRODUCTION.md`,
   `benchmarks/docs/08-monitoring.md`, `benchmarks/BENCHMARKS.md`,
   `CHANGELOG.md`, `pyproject.toml`, README; version bumped to **0.4.1**.
8. **Release** — `ruff check .`, `mypy`, `pytest` → branch + PR → CI green →
   merge to `main` → new tag (+ PyPI publish on request).

### Security (P3 — from 2026-08-12 hardening review)

- **Structural allowlist validation (post-parse)**: after translating a KB,
  validate that every predicate/arg conforms to the Euclid-IR grammar
  (predicates `\p{L}\w*`, args = atom/variable/number/string, only supported
  operators). Makes the contract explicit instead of relying on the blacklist;
  the blacklist stays as an early-reject/UX layer, not the security boundary.

### Backend

- Z3
- Soufflé
- ASP
- **Custom engine (SWI-Euclid)**: a self-contained Prolog engine embedded in the
  Euclid-MCP process (compile or distribute the SWI-Prolog runtime), removing the
  external `swipl` dependency for deployment (Docker images, standalone binaries).

### Performance

- **Conditional load (skip shipping clauses on unchanged KB)**: v0.3.1 already
  skips the workspace rebuild for repeated KBs, but the Python side still
  serializes the full clause text over the pipe (~17.8 ms at 20 000 facts). A
  two-phase exchange — send only the fingerprint, let the engine ask for the
  clauses only on mismatch — would cut the unchanged-KB case to ~1 ms.

### Scaling & parallelism

- **In-process engine pool**: run N persistent engines per instance and dispatch
  each request to an idle one (round-robin), enabling concurrent requests on a
  single process / HTTP API without cross-process coordination.
  I'm not sure it is a good idea...
- **Threaded HTTP API**: serve parallel requests via `ThreadingHTTPServer` so one
  instance can translate a new request while the engine works on another.
- **Horizontal scale-out**: stateless replicas behind a load balancer — no session
  affinity, any instance serves any request (see README "Scalability"). Document
  a reference architecture with nginx / Kubernetes.

### Knowledge

- Knowledge compiler
- RAG compiler

#### Persistent Prolog Engine (game-changer — needs enterprise project to validate)

**Status**: Done — implemented in v0.3.0 (`euclid_mcp/prolog_server.py`,
`euclid_mcp/prolog_engine.pl`), single persistent `swipl` process with
JSON-lines protocol, workspace reloaded per request. Benchmarks show ~3×–42×
steady-state speedup. In v0.3.1 the workspace is **skipped on unchanged
KBs**: Python caches parse+translate per source and the engine skips the
rebuild when the `load` carries the same `kb_hash` (repeated 20 000-fact KB:
~196 ms → ~18 ms per load). Roadmap items below.

**Motivation**: Each `reason()` call spawns a new SWI-Prolog process, loads the entire KB, and exits. For large KBs or repeated queries, this overhead is prohibitive.

**Goal**: A persistent Prolog process that:
- Loads the KB once at startup
- Accepts queries via stdin (JSON lines protocol)
- Supports incremental updates (assert/retract)
- Auto-restarts on crash with KB reload
- Falls back to stateless mode if unavailable

**Architecture**:
```
Python (PrologServer) ←── stdin/stdout (JSON lines) ──→ SWI-Prolog (persistent)
  assert(Fact)                                               |
  retract(Fact)                                              |
  query(Goal) ──────────────────────────────────────────────▶| findall
  load(KB) ─────────────────────────────────────────────────▶| parse + assert
```

**Protocol** (JSON lines on stdin/stdout):
| Command | Input | Output |
|---------|-------|--------|
| `load` | `{"command":"load","kb":"user(alice)...."}` | `{"status":"ok","facts":30,"rules":12,"predicates":8}` |
| `query` | `{"command":"query","goal":"has_role($who,admin)","max":50}` | `{"status":"ok","solutions":[{"who":"alice"}],"ms":3}` |
| `assert` | `{"command":"assert","fact":"user(bob)"}` | `{"status":"ok"}` |
| `retract` | `{"command":"retract","fact":"user(bob)"}` | `{"status":"ok"}` |
| `stats` | `{"command":"stats"}` | `{"status":"ok","facts":31,"rules":12}` |
| `halt` | `{"command":"halt"}` | (process exits) |

**Files**:
- `euclid_mcp/prolog_engine.pl` — Prolog server (~120 lines)
- `euclid_mcp/prolog_server.py` — Python wrapper with lifecycle management (~150 lines)
- `euclid_mcp/prolog_bridge.py` — Modified: add `persistent` mode + fallback
- `euclid_mcp/server.py` — Initialize engine at MCP startup

**Performance**:

| Scenario | Stateless (today) | Persistent | Improvement |
|----------|-------------------|------------|-------------|
| KB 44KB, 10 queries | 2s × 10 = 20s | 2s load + 5ms × 10 = 2.05s | ~10× |
| KB 1MB, 100 queries | 5s × 100 = 500s | 5s + 5ms × 100 = 5.5s | ~90× |
| What-if (assert/retract) | 2 subprocess | 2ms | ~500× |

**Implementation phases**:
1. `prolog_engine.pl` + `prolog_server.py` (persistent engine core)
2. Integrate into `prolog_bridge.py` (auto-detect + fallback)
3. Integrate into `server.py` (MCP lifecycle)
4. Tests + demo metrics

### Explainability

- Graphviz proof tree
- HTML explanations
- **Rule IDs in the proof tree** — `@rule RBAC-0043` directive; every `rule` node
  carries the source rule ID (audit trail: "this decision derives from rule 43")
- **Deterministic `explain_proof`** — proof tree → natural language, server-side,
  no LLM (cheaper + auditable; alternative to an LLM-based `explain`)
- **KB identity** — version + content hash per KB (compliance: "decision taken
  with KB v12")

### IR

It is important to keep Euclid-IR as simple as possible... 

- **Rule IDs** — `@rule <id>` directive attached to a rule, surfaced in the proof
  tree (see Explainability)- Typed predicates - Already implemented as trailing comments # RULE: id
- Temporal predicates
- **Schema / arity declarations** — `@predicate has_role(person, role)`; validator
  checks arity/args against the schema and gives the LLM a clear "contract" of
  available predicates (check_kb already collects arities internally)
- **`@use "kb_name"`** — reference a pre-loaded named KB from within Euclid-IR
  (complements the `kb_id` / `delta_knowledge` tool params)
- **Namespaces** — `rbac.user(alice)` to avoid collisions in large KBs
- **Metadata** — `@title`, `@description`, `@author`, `@domain` (enterprise)
- **Execution directives** — `@engine prolog`, `@max_depth 30`,
  `@max_solutions 10`, `@proof full` (metadata, not facts)
- **Aggregations COUNT/SUM** — DEFERRED (scope risk: violates "Euclid-IR must not
  become another Prolog"; tracked here so it stays a conscious rejection)



## External review: Gemini & ChatGPT (Jul 2026)

Independent reviews.

**Overall verdict: strongly positive.** Both models independently identify the
same core value — separating probabilistic understanding (LLM) from deterministic
inference (engine), with Euclid-IR as the auditable intermediate layer. Criticisms
are constructive extensions, not fundamental objections. No reviewer challenged
the architecture.

### Already implemented (comments now obsolete)

| Suggestion | Source | Where |
|---|---|---|
| String literals `"Alice Smith"` | Gemini P1, ChatGPT P3 | `"..."` / `'...'` UTF-8 |
| `!=` operator | Gemini P1, ChatGPT P3 | `!=` → `=\=` in translator |
| Safe negation / unbound-variable check | Gemini P1, ChatGPT P3 | `linter.py` + `check_kb` warning |
| Persistent-KB teaser in README | ChatGPT | README "Knowledge Base" section |
| "LLMs describe, Euclid proves" | ChatGPT | README tagline (short form) |
| Convenience operators `==`/`!=`/`<=` | ChatGPT P1 | canonical forms, mapped by translator |

### Still open — prioritized

Strategic framing (enterprise/consulting angle) lives in an unpublished internal doc.

| # | Idea | Source | Priority |
|---|---|---|---|
| 1 | Rule IDs (`@rule`) in proof tree | ChatGPT P1 | HIGH — audit trail |
| 2 | KB identity (version + hash) | ChatGPT P2 | HIGH — compliance |
| 3 | `@use "kb_name"` / `kb_id` + `delta_knowledge` | Gemini P1/P2, ChatGPT P2/P3 | HIGH — persistent KB (in roadmap) |
| 4 | Schema/arity declarations (`@predicate`) | ChatGPT P1/P3, Gemini P3 | HIGH — LLM contract + validation |
| 5 | Deterministic `explain_proof` (no LLM) | Gemini P1 | MEDIUM — decide vs LLM-based `explain` |
| 6 | Confidence split (translation vs inference) | ChatGPT P1 | MEDIUM — positioning/docs |
| 7 | "Less expressive by design" stated | ChatGPT P1 | MEDIUM — docs |
| 8 | Stateful MCP / persistent engine | Gemini P2, ChatGPT P2 | HIGH — already the "game-changer" below |
| 9 | COUNT/SUM aggregations | Gemini P1 | DEFERRED — scope risk |
| 10 | Rename "Why External Inference?" | ChatGPT | LOW — cosmetic |

### Rule IDs — design

Origin: ChatGPT P1 — an auditor should be able to say *"this decision derives from
rule 43"*. Today the proof tree emits `rule` nodes but the rule has no identity.

**Syntax** (optional directive, backward compatible — rules without ID behave
exactly as today):

```
@rule RBAC-0043
can_access($u, $r) IF has_role($u, $role) AND role_perm($role, $r)
```

`@rule` binds to the immediately following rule. Multiple rules may share a head
predicate; each keeps its own ID. Duplicate IDs → `check_kb` warning.

**Two candidate implementations** (decision pending):

1. **Prolog-native (ID carried through the proof)** — the meta-interpreter
   recovers the ID of the exact clause that fired and `proof_to_json` emits it
   on the `rule` node. Most trustworthy attribution, survives any engine work,
   but requires translator + meta-interpreter + `proof_to_json` changes.
   Output shape stays byte-identical when no IDs are present.
2. **Python post-processing** — the server matches each proof `rule` node's
   `goal`/`body` against the translated KB rules and attaches the ID afterwards.
   No Prolog changes, minimal risk; but attribution is inferred, not carried.

## Euclid-IR Language Evolution - Design philosophy

Euclid-IR is intentionally **not** a simplified Prolog.

It is a backend-independent intermediate representation designed for:

- Humans
- LLMs
- Deterministic inference engines

The language should describe **knowledge**, never **inference strategy**.

Whenever possible, complexity belongs in the translator or the backend, not in Euclid-IR itself.

## Version 1.0 stabilization

These changes should be completed before Euclid-IR is considered stable.

### 1. Case-insensitive identifiers

### 2. String literals

### 4. Safe Negation


## Language principles

Prefer modern conventions over historical Prolog syntax.

Examples:

| Euclid-IR | Instead of |
|-----------|------------|
| `$user` | `User` |
| `IF` | `:-` |
| `AND` | `,` |
| `NOT` | `\+` |
| `# comment` | `% comment` |

The language should feel natural to developers familiar with Markdown, YAML and modern programming languages.

## Documentation

`#` is the preferred comment syntax.

Comments may also be used as Markdown headings to organize knowledge bases.

Example:

```text
# Users

user(alice)

# Roles

has_role(alice, admin)
```

## Language future evolution

Future features should satisfy at least one of these goals:

- simplify LLM generation
- improve readability
- improve auditability
- remain backend-independent

Features that mainly expose backend-specific behavior should generally be avoided.
Backward compatibility should be maintaned when possible.

**"Euclid-IR should remain as simple as possible for reliable logical reasoning, but no simpler ."**

