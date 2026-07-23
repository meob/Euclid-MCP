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

### Explainability

- Graphviz proof tree
- HTML explanations

### IR

- Typed predicates
- Temporal predicates