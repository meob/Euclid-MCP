# Euclid-MCP

**MCP server for logical reasoning** — turns facts into formal proofs.

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

Even if currently Euclid-MCP uses a Prolog Engine, no Prolog syntax required.  
Euclid IR (Intermediate Representation) is a declarative intermediate representation for logical inference.
Variables use `$name`, implication is `IF`, conjunction is `AND`.

**Text format:**
```
mortal(socrates)
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
    mortal(socrates)
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
- **Knowledge preload**: Complex business rules can be loaded in Euclid instead of using a RAG query

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

## Why External Inference?

The external inference gives several advantages:
- deterministic
- explainable
- verifiable
- inexpensive
- replaceable backend

In the current implementation Euclid-MCP uses Prolog.  
Prolog is a 50-year-old battle-tested logic engine. Using it as a "deduction coprocessor" lets small LLMs perform complex multi-step reasoning without needing larger, more expensive models. The intermediate language strips away Prolog's syntax quirks while keeping its logical core.


## How is Euclid?

**Euclid** was an ancient Greek mathematician. Living and teaching in Alexandria, he built the foundations of geometry and number theory using rigorous logical proofs.

Euclid MCP is not:
- an LLM
- a knowledge base
- a vector database
- an agent framework
- a planner

**Euclid MCP** is a deterministic inference engine that can be used by any of them.  
Euclid MCP allows deterministic and explainable replies from small LLMs on Edge hardware too.


## License

Apache 2.0
