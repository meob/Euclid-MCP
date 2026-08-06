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

### Backend

- Z3
- Soufflé
- ASP

### Knowledge

- Knowledge compiler
- RAG compiler

#### Persistent Prolog Engine (game-changer — needs enterprise project to validate)

**Status**: Planned

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

### IR

- Typed predicates
- Temporal predicates



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

**"Euclid-IR should remain as simple as possible, but no simpler for reliable logical reasoning."**

**"Everything should be made as simple as possible, but not simpler"**

**"Entia non sunt moltiplicanda praeter necessitatem"**


## Demo (examples/10_llm_vs_euclid/)

Side-by-side comparison: plain LLM vs LLM + Euclid-MCP, same model, same KB.

### Completed
- Interactive CLI with Ollama tool calling (llama3.1:8b)
- IT Security KB (30 users, 50 resources, recursive role hierarchy)
- Language-agnostic: works in any language without hardcoded mappings
- Text-based tool call fallback for models with inconsistent tool calling
- Query syntax auto-correction (`$who=value` → `value`)

### Improvements backlog
- Token tracking (per-call and progressive)
- JSON-lines log for post-session analysis
- Proof tree ASCII visualization
- What-if interactive mode
- Multiple model comparison (llama3.1 vs qwen vs mistral)
- Additional KB scenarios (Oracle EMP table, RPG game, startup)
