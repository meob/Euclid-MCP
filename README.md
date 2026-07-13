# Euclid-MCP

[![Euclid-MCP MCP server](https://glama.ai/mcp/servers/meob/Euclid-MCP/badges/score.svg)](https://glama.ai/mcp/servers/meob/Euclid-MCP)

**MCP server for logical reasoning** — turns facts into formal proofs.

<!-- mcp-name: io.github.meob/euclid-mcp -->


Euclid-MCP is a hybrid cognitive architecture: a lightweight LLM describes the world in facts, and a deterministic engine performs the actual deduction. The LLM never needs to reason — it only needs to describe.

## How it works

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────┐     ┌──────────────┐
│  LLM/Agent   │────▶│  Euclid-MCP      │────▶│  Translator  │────▶│  SWI-Prolog  │
│  (MCP Client)│◀────│  (FastMCP)       │◀────│  + Meta-IP   │◀────│ (subprocess) │
└──────────────┘     └──────────────────┘     └──────────────┘     └──────────────┘
```

1. Receive facts, rules, and a query in a simple intermediate language
2. Translate into Prolog with a meta-interpreter for proof tree capture
3. Execute via SWI-Prolog subprocess
4. Return solutions + proof trees as structured JSON

LLMs describe. Euclid MCP proves.  


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
| Implication | `IF` (uppercase) | `mortal($x) IF human($x)` |
| Conjunction | `AND` (uppercase) | `p($x) AND q($x)` |
| Negation | `NOT` (uppercase) | `NOT active($user)` |
| Query | `? predicate` | `? ancestor(tom, $who)` |
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

**Supported operators:** `>`, `>=`, `<`, `=<`, `=:=`, `=\=`, `is`

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

### `reason`

Main tool for verifiable deterministic reasoning.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `knowledge` | `string` | — | Facts & rules in text or YAML format |
| `query` | `string?` | — | Override query (optional) |
| `max_solutions` | `int` | `5` | Max solutions to return |
| `max_depth` | `int` | `30` | Max proof tree depth |

**Returns** `ReasonResult` with `solutions[]` — each containing variable bindings and a proof tree.

## Installation

```bash
# Prerequisites: Python ≥ 3.10, SWI-Prolog
brew install swi-prolog

# Install
pip install euclid-mcp
```

Or from source:
```bash
git clone https://github.com/meo/euclid-mcp
cd euclid-mcp
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

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
from euclid_mcp.server import reason

result = reason(knowledge="""
    human(socrates)
    mortal($x) IF human($x)
    ? mortal($who)
""")

for sol in result.solutions:
    print(sol.substitutions, sol.proof.type)
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
        "subproof": {"type": "fact", "goal": "parent(tom, bob)"}
      }
    },
    {
      "substitutions": {"who": "ann"},
      "proof": {
        "type": "rule",
        "goal": "ancestor(tom, ann)",
        "body": "parent(tom, bob), ancestor(bob, ann)",
        "subproof": {
          "type": "and",
          "left": {"type": "fact", "goal": "parent(tom, bob)"},
          "right": {
            "type": "rule",
            "goal": "ancestor(bob, ann)",
            "body": "parent(bob, ann)",
            "subproof": {"type": "fact", "goal": "parent(bob, ann)"}
          }
        }
      }
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


### Real-world examples

```bash
# Genealogy — recursive family tree reasoning
python3 examples/01_genealogy.py

# RBAC — Role-Based Access Control
python3 examples/02_rbac.py

# Classification — biological taxonomy
python3 examples/03_classification.py

# Business rules — loan eligibility
python3 examples/04_loan_eligibility.py

# Compliance auditor — cloud resource policy enforcement
python3 examples/05_compliance_auditor/auditor.py

# Loan officer — CSV-driven eligibility with detailed breakdown
python3 examples/06_loan_eligibility/loan_officer.py

# IT Security & Compliance — multi-layer policy reasoning
python3 examples/07_it_security_compliance/demo.py --small
```

Each example runs a complete reasoning session and prints solutions with proof trees — no LLM required.  
Use them as templates for integrating Euclid-MCP into your own agents.

The two newer examples (05, 06) demonstrate a **data-driven agent workflow**:
- Read external data (JSON, CSV) that simulates API/CRM exports
- Convert structured data to Euclid facts in Python
- Load policy rules from `.euclid` files (separated from data)
- Call `reason()` for deduction
- Format results into human-readable reports with proof chains

This mirrors how a real agent would work: collect data, describe it as facts, let Euclid reason, and present the results.

### Example 07: IT Security & Compliance

The most advanced example demonstrating:
- **3-layer architecture**: Standards (CIS, AWS IAM) → Company Policies → Data Facts
- **Arithmetic comparisons**: `$days > 90` for stale access detection
- **Multi-line rules**: Complex policies split across lines
- **Conjunction queries**: Combining multiple predicates
- **Negative tests**: Verifying empty results for invalid access patterns

```bash
# Quick test (30 users, 50 resources, ~578 facts)
python3 examples/07_it_security_compliance/demo.py --small

# Full dataset (200 users, 300 resources, ~3,872 facts)
python3 examples/07_it_security_compliance/demo.py
```

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

```
POST /reason  →  {"knowledge": "red(apple)\n? red($x)"}
GET  /health
```

Connect an **HTTP Request** node to `http://localhost:8080/reason`.

### CLI pipeline

```bash
echo '{"knowledge": "red(apple)\\n? red($x)"}' | python3 integrations/euclid_cli.py
```

See `integrations/README.md` for full details.


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
