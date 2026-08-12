# Euclid-MCP

[![Euclid-MCP MCP server](https://glama.ai/mcp/servers/meob/Euclid-MCP/badges/score.svg)](https://glama.ai/mcp/servers/meob/Euclid-MCP)
[![PyPI version](https://img.shields.io/pypi/v/euclid-mcp?color=blue)](https://pypi.org/project/euclid-mcp/)
[![Python versions](https://img.shields.io/pypi/pyversions/euclid-mcp)](https://pypi.org/project/euclid-mcp/)
[![License](https://img.shields.io/github/license/meob/Euclid-MCP?cacheSeconds=86400)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/meob/Euclid-MCP/ci.yml?branch=main&label=CI)](https://github.com/meob/Euclid-MCP/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/codecov/c/github/meob/Euclid-MCP)](https://codecov.io/gh/meob/Euclid-MCP)

**MCP server for logical reasoning** — turns facts into formal proofs.

<!-- mcp-name: io.github.meob/euclid-mcp -->

Euclid-MCP is a hybrid cognitive architecture: a lightweight LLM describes the world in facts, and a deterministic engine performs the actual deduction. The LLM never needs to reason — it only needs to describe.

With Euclid-MCP, an 8B model can solve reasoning tasks that stump even 400B+ cloud models — because the engine handles deduction deterministically. Every answer comes with a proof tree, so you can trace *why* a conclusion holds, not just *what* it is. Use it to enforce RBAC policies, audit cloud compliance, validate loan eligibility rules, or reason over any domain where answers must be explainable and verifiable.

Euclid-MCP is written in Python and uses **Euclid-IR**, a human-readable intermediate language designed for both AI agents and humans. It currently uses **SWI-Prolog** as its inference engine and can be consumed in multiple ways: via **MCP** by AI agents (OpenCode, Claude, Cursor), via **HTTP** by tools and automation platforms (n8n, Zapier, Make), and via **Python API** for direct integration. Euclid-IR rules can also be used to **augment RAG** pipelines with deterministic policy enforcement.


## How it works

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  LLM/Agent   │────▶│  Euclid-MCP      │────▶│  Translator  │────▶│  SWI-Prolog     │
│  (MCP Client)│◀────│  (MCPServer)     │◀────│  + Meta-IP   │◀────│ (persistent)    │
└──────────────┘     └──────────────────┘     └──────────────┘     └─────────────────┘
```

1. Receive facts, rules, and a query in a simple intermediate language
2. Translate into Prolog with a meta-interpreter for proof tree capture
3. Execute via a persistent SWI-Prolog engine process (JSON-lines protocol on stdin/stdout; the workspace is reloaded per call, no process spawn overhead)
4. Return solutions + proof trees as structured JSON

Additional tools (`explain`, `diagnose`, `what_if`, `check_kb`) extend this core flow with natural-language explanations, analysis, scenario testing, and validation.

LLMs describe. Euclid MCP proves.  


### Knowledge Base

For small knowledge bases, facts and rules can be provided with each request.

Since v0.2.0 a knowledge base can be loaded at server startup and reused across
calls, so agents only pass the session-specific facts for the current query.

This minimizes token usage, improves performance, and allows small LLMs to reason over large rule sets without reconstructing the entire knowledge base for every request.


## Intermediate Language

Even if currently Euclid-MCP uses a Prolog Engine, no Prolog syntax is required.  
**Euclid-IR** (Intermediate Representation) is a declarative intermediate representation for logical inference.
Variables use `$name`, implication is `IF`, conjunction is `AND`.

**Text format:**
```
human(socrates)
mortal($x) IF human($x)

? mortal($who)
```

**YAML format:**
```yaml
facts:
  - parent(tom, bob)
  - parent(bob, ann)
  - parent(tom, liz)
rules:
  - ancestor($x, $y) IF parent($x, $y)
  - ancestor($x, $y) IF parent($x, $z) AND ancestor($z, $y)

query: ancestor(tom, $who)
```

Full language reference: [`docs/EUCLID_IR.md`](docs/EUCLID_IR.md)


### Euclid-IR Syntax Reference

| Element | Syntax | Example |
|---------|--------|---------|
| Facts | `predicate(args)` | `parent(tom, bob)` |
| Variables | `$name` (lowercase) | `$who`, `$x`, `$count` |
| Implication | `IF` | `mortal($x) IF human($x)` |
| Conjunction | `AND` | `p($x) AND q($x)` |
| Negation | `NOT` | `NOT active($user)` |
| Query | `? predicate` | `? ancestor(tom, $who)` |
| String literals | `"..."` or `'...'` | `"alice@example.com"` |
| Multi-line rules | Body on next line | `rule($x) IF\n    body($x)` |

### Arithmetic Comparisons

Rules support arithmetic comparisons that are evaluated during deduction:

```
# Stale access: users who haven't logged in for 90+ days
stale_access($user) IF
    user($user) AND last_login_days($user, $days) AND $days > 90

# Excessive permissions: more than 15 direct permissions
excessive_permissions($user, $count) IF
    user($user) AND permission_count($user, $count) AND $count > 15

# Clearance check: user clearance >= resource classification
can_access($user, $resource) IF
    user($user) AND resource($resource, _, _, _, _, $cls) AND
    classification($cls, $cls_level, _) AND
    user_clearance($user, $user_level) AND $user_level >= $cls_level
```

**Supported operators:** `>`, `>=`, `<`, `<=`, `==`, `is`, `!=`

### Multi-line Rules

Rules can span multiple lines for readability:

```
can_deploy($user, $env) IF
    user($user) AND
    has_role($user, $role) AND
    deploy_requires_level($env, $min) AND
    deploy_role_level($role, $level) AND
    $level >= $min AND
    user_has_permission($user, deploy_code)
```

### Conjunctions in Queries

Queries can combine multiple predicates:

```
? can_access_resource($who, $res) AND resource($res, _, _, _, _, secret)
```

This returns solutions where both conditions are satisfied simultaneously.

## Why External Inference?

The external inference gives several advantages:
- deterministic
- explainable
- verifiable
- inexpensive
- replaceable backend

In the current implementation Euclid-MCP uses Prolog.  
Prolog is a 50-year-old battle-tested logic engine. Using it as a "deduction coprocessor" lets small LLMs perform complex multi-step reasoning without needing larger, more expensive models. The intermediate language strips away Prolog's syntax quirks while keeping its logical core.

Some internal [benchmarks](benchmarks/BENCHMARKS.md) demonstrate the difference: with 1 000+ facts, LLMs alone score 2/5 while Euclid-MCP scores 5/5 — and runs 7× faster while outputting 14× fewer tokens.


## Tools

Euclid-MCP exposes **5 tools**, each with a specific purpose:

| Tool | Purpose |
|------|---------|
| `reason` | Main deduction — get solutions + proof trees |
| `explain` | Readable, natural-language reasoning steps |
| `diagnose` | Understand why a query succeeds or fails |
| `what_if` | Test modifications before applying them |
| `check_kb` | Validate KB consistency before reasoning |

### `reason`

Main tool for verifiable deterministic reasoning.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `knowledge` | `string` | — | Facts & rules in text or YAML format |
| `query` | `string?` | — | Override query (optional) |
| `max_solutions` | `int` | `5` | Max solutions to return |
| `max_depth` | `int` | `30` | Max proof tree depth |

**Returns** `ReasonResult` with `solutions[]` — each containing variable bindings and a proof tree.

### `explain`

Deterministic proof-tree → natural-language reasoning steps. No LLM involved: it
walks the proof tree of each solution and renders every step in plain language,
citing the rule ID (`# RULE: <id>`) when a rule has one. Use it to turn a proof
into an auditable, human-readable explanation.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `knowledge` | `string?` | — | Facts & rules in text or YAML format |
| `query` | `string?` | — | Override query (optional) |
| `max_solutions` | `int` | `5` | Max solutions to return |
| `max_depth` | `int` | `30` | Max proof tree depth |

**Returns** `ExplanationResult` with `explanations[]` — each containing variable
bindings and an ordered list of natural-language `steps`.

### `diagnose`

Query analysis — understand why a query succeeds or fails.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `knowledge` | `string` | — | Facts & rules in text or YAML format |
| `query` | `string` | — | Query to diagnose |
| `mode` | `string` | `why` | One of: `why`, `why_not`, `what_needs` |
| `max_solutions` | `int` | `5` | Max solutions to return |
| `max_depth` | `int` | `30` | Max proof tree depth |

**Modes:**
- `why` — explain why a query holds (or that it doesn't)
- `why_not` — explain why a query fails (missing facts/rules)
- `what_needs` — suggest what would make a false query true

**Returns** `DiagnosisResult` with `holds`, `findings[]`, `conclusion`, and optionally `proof`.

### `what_if`

Scenario analysis — apply modifications to a knowledge base and compare results.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `base_knowledge` | `string` | — | Base facts & rules |
| `modifications` | `string` | — | `+ fact(...)` to add, `- fact(...)` to remove |
| `query` | `string` | — | Query to evaluate |
| `max_solutions` | `int` | `5` | Max solutions to return |
| `max_depth` | `int` | `30` | Max proof tree depth |

**Returns** `WhatIfResult` with `before_count`, `after_count`, `delta`, `solutions_before`, `solutions_after`, `conclusion`.

### `check_kb`

Knowledge base validator — check for consistency before running deduction.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `knowledge` | `string` | — | Facts & rules in text or YAML format |

**Returns** `KBCheckResult` with `valid`, `errors[]`, `warnings[]`, `facts_count`, `rules_count`, `predicates_count`.


#### KB Preload (v0.2.0)

Since v0.2.0 a knowledge base can be loaded **once at server startup** and reused across
calls, so agents only pass the session-specific facts for the current query.

Preload a KB by file path, via the `EUCLID_KB_PATH` environment variable or a
`--kb-path` CLI flag:

```bash
# Environment variable
EUCLID_KB_PATH=/path/to/policies.euclid python3 -m euclid_mcp

# CLI flag (MCP stdio, console script, and HTTP API)
python3 -m euclid_mcp --kb-path /path/to/policies.euclid
python3 integrations/euclid_api.py --kb-path /path/to/policies.euclid --port 8080
```

Behavior:

- The file is **validated with `check_kb` at startup** and the server fails fast
  with a clear message if the file is missing, unreadable, oversized, or invalid.
- `knowledge`/`base_knowledge` on `reason`, `explain`, `diagnose`, `what_if`, and
  `check_kb` become **optional**: an explicit value always wins, an empty value
  falls back to the preloaded KB. With neither, tools return a clear
  "No knowledge provided" error.
- A **markdown digest** of the preloaded KB (fact/rule/predicate counts, predicate
  inventory, rules with their IDs) is appended to the server instructions, so
  agents can see what the KB covers without extra tool calls.

Backward compatible: passing `knowledge` explicitly behaves exactly as before.


## Installation

### pip

```bash
# Prerequisites: Python ≥ 3.10, SWI-Prolog
brew install swi-prolog

# Install
pip install euclid-mcp
```

### From source

```bash
git clone https://github.com/meob/Euclid-MCP
cd Euclid-MCP
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

### Docker

No local SWI-Prolog installation needed — the image bundles everything.

```bash
# Build
docker build -t euclid-mcp .

# MCP stdio mode (for local MCP clients)
docker compose run --rm euclid-mcp

# HTTP API mode (for n8n, Zapier, remote access)
docker compose up euclid-api
# API available at http://localhost:8080
```

See [Docker in Integrations](#docker) for full details.

## Usage

### Via MCP (OpenCode, Claude, etc.)

```json
{
  "mcpServers": {
    "euclid-mcp": {
      "command": "python3",
      "args": ["-m", "euclid_mcp"],
      "cwd": "/path/to/euclid-mcp"
    }
  }
}
```

### Via Python

```python
from euclid_mcp.server import reason, explain, diagnose, what_if, check_kb

# Reasoning
result = reason(knowledge="""
    human(socrates)
    mortal($x) IF human($x)
    ? mortal($who)
""")
for sol in result.solutions:
    print(sol.substitutions, sol.proof.type)

# Explanation — readable reasoning steps (cites rule IDs when present)
expl = explain(
    knowledge="human(socrates)\nmortal($x) IF human($x)  # RULE: BIO-001",
    query="mortal($who)"
)
for e in expl.explanations:
    print(e.substitutions, e.steps)

# Diagnosis — why does a query fail?
diag = diagnose(
    knowledge="human(socrates)\nmortal($x) IF human($x)",
    query="mortal(plato)",
    mode="why_not"
)
print(diag.conclusion)

# What-if — how does adding a fact change results?
scenario = what_if(
    base_knowledge="human(socrates)\nmortal($x) IF human($x)",
    modifications="+ human(plato)",
    query="mortal($who)"
)
print(f"Before: {scenario.before_count}, After: {scenario.after_count}")

# KB validation
check = check_kb(knowledge="human(socrates)\nmortal($x) IF human($x)")
print(f"Valid: {check.valid}, Errors: {check.errors}")
```

### Example output

```json
{
  "query": "ancestor(tom, $who)",
  "solutions": [
    {
      "substitutions": {"who": "bob"},
      "proof": {
        "type": "rule",
        "goal": "ancestor(tom, bob)",
        "body": "parent(tom, bob)",
        "rule_id": "GEN-1",
        "subproof": {"type": "fact", "goal": "parent(tom, bob)"}
      }
    },
    {
      "substitutions": {"who": "ann"},
      "proof": {
        "type": "rule",
        "goal": "ancestor(tom, ann)",
        "body": "parent(tom, bob), ancestor(bob, ann)",
        "rule_id": "GEN-2",
        "subproof": {
          "type": "and",
          "left": {"type": "fact", "goal": "parent(tom, bob)"},
          "right": {
            "type": "rule",
            "goal": "ancestor(bob, ann)",
            "body": "parent(bob, ann)",
            "rule_id": "GEN-1",
            "subproof": {"type": "fact", "goal": "parent(bob, ann)"}
          }
        }
      }
    }
  ]
}
```

Rules can carry an audit-trail ID via a trailing `# RULE: <id>` comment; the ID
is surfaced as `rule_id` on the `rule` nodes of the proof tree, so a decision
can be cited ("this derives from rule GEN-2").

#### Diagnose output

```json
{
  "query": "mortal(plato)",
  "mode": "why_not",
  "holds": false,
  "findings": [
    {
      "type": "satisfied",
      "predicate": "human",
      "detail": "Facts exist for 'human' (1 facts)"
    }
  ],
  "conclusion": "The query fails. Check rule conditions."
}
```

#### What-if output

```json
{
  "query": "mortal($who)",
  "modifications": "+ human(plato)",
  "before_count": 1,
  "after_count": 2,
  "delta": "more",
  "solutions_before": [{"substitutions": {"who": "socrates"}}],
  "solutions_after": [
    {"substitutions": {"who": "plato"}},
    {"substitutions": {"who": "socrates"}}
  ],
  "conclusion": "Solutions increased: 1 -> 2."
}
```

#### Explain output

```json
{
  "query": "mortal($who)",
  "explanations": [
    {
      "substitutions": {"who": "socrates"},
      "steps": [
        "mortal(socrates) is derived by rule BIO-001 from: human(socrates).",
        "human(socrates) is asserted as a fact in the knowledge base."
      ]
    }
  ]
}
```


## Use cases

- **Small LLM reasoning**: Offload deduction from LLMs (3-8B) to a deterministic engine
- **Explainable decisions**: Every answer comes with a proof tree which allows explanation, reasoning trace, and justification
- **Business rules**: Validate logic chains (permissions, workflows, compliance)
- **Dependency analysis**: Circular dependency detection, topological ordering
- **Education**: Interactive logic tutoring with visible proof chains
- **Knowledge preload**: Complex business rules can be loaded in Euclid instead of using a vector database
- **Query diagnosis**: Understand why queries fail and what facts/rules are missing
- **Scenario analysis**: Test "what-if" modifications before applying them to production
- **KB validation**: Check knowledge bases for consistency before reasoning


### Real-world examples

There are several examples provided as samples: Genealogy, RBAC, Classification, Loan Eligibility,
Cluedo Detective, IT Security & Compliance, LLM vs Euclid-MCP, ...
Most interesting ones are the **IT Security & Compliance** (with
CIS, AWS, IAM Standards enforcement, Company Policies implementation, hundreds of Data Facts)
and side-by-side **LLM vs Euclid-MCP**.

Examples full description: [`docs/EXAMPLES.md`](docs/EXAMPLES.md)


## Integrations

### OpenCode

Euclid-MCP includes a pre-configured agent in `.opencode.json`:

```json
{
  "mcpServers": {
    "euclid-mcp": {
      "command": "python3",
      "args": ["-m", "euclid_mcp"],
      "cwd": "."
    }
  },
  "agents": {
    "reasoning-engine": {
      "description": "Deterministic logic engine",
      "instructions": "Write facts in Euclid IR, use the reason tool...",
      "mcpServers": ["euclid-mcp"]
    }
  }
}
```

### n8n / Zapier / Make

Run the HTTP API:

```bash
python3 integrations/euclid_api.py --port 8080
```

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/reason` | POST | Deduction with proof trees |
| `/explain` | POST | Natural-language reasoning steps |
| `/diagnose` | POST | Query failure analysis |
| `/what-if` | POST | Scenario testing |
| `/check-kb` | POST | KB validation |
| `/health` | GET | Health check |

```bash
# Reasoning
curl -X POST http://localhost:8080/reason \
  -H "Content-Type: application/json" \
  -d '{"knowledge": "human(socrates)\nmortal($x) IF human($x)\n? mortal($who)"}'

# Explanation
curl -X POST http://localhost:8080/explain \
  -H "Content-Type: application/json" \
  -d '{"knowledge": "human(socrates)\nmortal($x) IF human($x)\n? mortal($who)"}'

# Diagnosis
curl -X POST http://localhost:8080/diagnose \
  -H "Content-Type: application/json" \
  -d '{"knowledge": "human(socrates)\nmortal($x) IF human($x)", "query": "mortal(plato)", "mode": "why_not"}'

# What-if
curl -X POST http://localhost:8080/what-if \
  -H "Content-Type: application/json" \
  -d '{"base_knowledge": "human(socrates)\nmortal($x) IF human($x)", "modifications": "+ human(plato)", "query": "mortal($who)"}'

# KB validation
curl -X POST http://localhost:8080/check-kb \
  -H "Content-Type: application/json" \
  -d '{"knowledge": "human(socrates)\nmortal($x) IF human($x)"}'
```

### Docker

The Docker image bundles SWI-Prolog + Python, so no local prerequisites are needed.
Base image: [`swipl:stable`](https://hub.docker.com/_/swipl) (Debian Bookworm).

**Two modes via docker-compose:**

```bash
# MCP stdio — pipe to a local MCP client
docker compose run --rm euclid-mcp

# HTTP API — expose REST endpoints on port 8080
docker compose up euclid-api
```

**Standalone usage:**

```bash
# Build
docker build -t euclid-mcp .

# Run HTTP API
docker run --rm -p 8080:8080 euclid-mcp \
  python3 integrations/euclid_api.py --port 8080

# Run MCP stdio (interactive)
docker run --rm -i euclid-mcp

# Quick test — reason directly from CLI
docker run --rm euclid-mcp python3 -c "
from euclid_mcp.server import reason
r = reason(knowledge='human(socrates)\nmortal(\$x) IF human(\$x)\n? mortal(\$who)')
print(r.solutions[0].substitutions)
"
```

**Docker image size:** ~370 MB (SWI-Prolog + Python 3.11 + dependencies).

### CLI pipeline

```bash
echo '{"knowledge": "red(apple)\\n? red($x)"}' | python3 integrations/euclid_cli.py
```

See `integrations/README.md` for full details.


## Scalability

The engine is **persistent** since v0.3.0 — a single long-lived SWI-Prolog
process per server instance, reloaded per request over a JSON-lines pipe
instead of booting Prolog for every call. Requests stay **stateless**: each one
brings its own knowledge base (or uses the preloaded one), so instances share
nothing.

This makes Euclid-MCP horizontally scalable:

- **HTTP API** — run any number of instances behind a load balancer (nginx, a
  Kubernetes Service, …). No session affinity needed: any instance can serve any
  request.
- **MCP stdio** — each MCP client spawns its own instance by design, giving
  natural isolation and parallelism across clients.
- **Resource footprint** — one `swipl` process per instance (~tens of MB)
  instead of one short-lived process per request, so a single instance serves
  many requests cheaply.

A single instance handles one request at a time; an in-process engine pool for
concurrent requests is on the roadmap (see `IDEAS.md`).

Reference production architecture — load balancing, resource limits, security
hardening, and monitoring for a replica battery behind HAProxy:
[`docs/PRODUCTION.md`](docs/PRODUCTION.md).


## Development

Requirements: Python ≥ 3.10, SWI-Prolog.

```bash
# Install in editable mode with dev dependencies
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Lint
ruff check .

# Type check
mypy euclid_mcp integrations

# Tests with coverage
pytest --cov=euclid_mcp --cov=integrations
```

The CI workflow ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs these
same checks on push and pull request, across Python 3.10–3.12.

### Logging & tracing

Every tool call is logged with its name, elapsed time, and outcome. Enable
structured logs by setting `EUCLID_LOG_LEVEL` (one of `DEBUG`, `INFO`,
`WARNING`, `ERROR`, `CRITICAL`) — e.g. `EUCLID_LOG_LEVEL=INFO`. Without the
variable, only warnings and errors are emitted.

The HTTP API also supports request tracing: send an `X-Request-Id` header and
it is echoed back on the response and included in the access logs.


## How is Euclid?

**Euclid** was an ancient Greek mathematician. Living and teaching in Alexandria, he built the foundations of geometry and number theory using rigorous logical proofs.

**Euclid-MCP** is not:
- an LLM
- a knowledge base
- a vector database
- an agent framework
- a planner

**Euclid-MCP** is a deterministic inference engine that can be used by any of them.  
Euclid-MCP allows deterministic and explainable replies from small LLMs on Edge hardware too.


## License

Apache 2.0
