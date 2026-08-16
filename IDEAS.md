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
- `explain` — readable reasoning steps derived from the proof tree
- `diagnose` — query analysis (why/why_not/what_needs)
- `what_if` — scenario testing with fact additions/removals
- `check_kb` — knowledge base validation
- `register_kb` — register a named KB under a `kb_id`
- `unregister_kb` — remove a named KB from the registry
- `list_kbs` — list registered named KBs (metadata)

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

### Security (from 2026-08-12 hardening review)

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
  Euclid-MCP process (compile or distribute the SWI-Prolog runtime) for
  full-fidelity Prolog workloads. The pure-Python **native engine** (v0.4.0,
  see `docs/NATIVE_ENGINE.md`) already removes the external `swipl` dependency
  for small knowledge bases; SWI-Euclid would extend that to large KBs.

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
  affinity, any instance serves any request (see README "Scalability").
  Documented for HAProxy in `docs/PRODUCTION.md`; nginx / Kubernetes reference
  docs are still open.

### Knowledge

- Knowledge compiler
- RAG compiler

### Explainability

- Graphviz proof tree
- HTML explanations

### IR

It is important to keep Euclid-IR as simple as possible... 

- Typed predicates
- Temporal predicates
- **Schema / arity declarations** — `@predicate has_role(person, role)`; validator
  checks arity/args against the schema and gives the LLM a clear "contract" of
  available predicates (check_kb already collects arities internally)
- **`@use "kb_name"`** — reference a pre-loaded named KB from within Euclid-IR
  (`kb_id` + `delta_knowledge` already ship the session overlay; `@use` would be
  its in-IR counterpart)
- **Namespaces** — `rbac.user(alice)` to avoid collisions in large KBs
- **Metadata** — `@title`, `@description`, `@author`, `@domain` (enterprise)
- **Execution directives** — `@engine prolog`, `@max_depth 30`,
  `@max_solutions 10`, `@proof full` (metadata, not facts)
- **Aggregations COUNT/SUM** — DEFERRED (scope risk: violates "Euclid-IR must not
  become another Prolog"; tracked here so it stays a conscious rejection)



## External review: by Gemini & ChatGPT (Jul 2026)

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
| 1 | `@use "kb_name"` within Euclid-IR | Gemini P1/P2, ChatGPT P2/P3 | MEDIUM — `kb_id` + `delta_knowledge` already shipped |
| 2 | Schema/arity declarations (`@predicate`) | ChatGPT P1/P3, Gemini P3 | HIGH — LLM contract + validation |
| 3 | Confidence split (translation vs inference) | ChatGPT P1 | MEDIUM — positioning/docs |
| 4 | "Less expressive by design" stated | ChatGPT P1 | MEDIUM — docs |
| 5 | COUNT/SUM aggregations | Gemini P1 | DEFERRED — scope risk |
| 6 | Rename "Why External Inference?" | ChatGPT | LOW — cosmetic |

## Euclid-IR Language Evolution - Design philosophy

Euclid-IR is intentionally **not** a simplified Prolog.

It is a backend-independent intermediate representation designed for:

- Humans
- LLMs
- Deterministic inference engines

The language should describe **knowledge**, never **inference strategy**.

Whenever possible, complexity belongs in the translator or the backend, not in Euclid-IR itself.

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

