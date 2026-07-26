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

- Huge rule size: daemon mode, knowledge preload, Databases
- Knowledge compiler
- RAG compiler

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

## Future evolution

Future features should satisfy at least one of these goals:

- simplify LLM generation
- improve readability
- improve auditability
- remain backend-independent

Features that mainly expose backend-specific behavior should generally be avoided.

**"Euclid-IR should remain as simple as possible, but no simpler for reliable logical reasoning."**

**"Everything should be made as simple as possible, but not simpler"**

**"Entia non sunt moltiplicanda praeter necessitatem"**
