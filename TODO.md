# TODO

## Done

- [x] Publish on GitHub
- [x] MCP inspector testing (`mcp dev`)
- [x] 57/57 tests: parsing, translation, Prolog execution, security
- [x] Edge cases: comments, booleans, YAML, max_depth, underscores, integers + AND
- [x] OpenCode integration: `opencode.json`, `AGENTS.md`, `.opencodeignore`
- [x] Bug fix: `substitutions` type `dict[str, str]` → `dict[str, Any]` (integer values)
- [x] Bug fix: prolog_bridge.py try/except per righe malformate
- [x] Import relativi → assoluti in server.py
- [x] Istruzioni FastMCP: italiano → inglese
- [x] Error messages: italiano → inglese
- [x] **Short real cases**: genealogia, RBAC, classificazione biologica, loan eligibility
- [x] **Esempi complessi (data-driven agent workflow)**: compliance_auditor, loan_eligibility
- [x] **Integrazioni**: opencode.json, HTTP API, CLI wrapper
- [x] **PyPI release** (`pip install euclid-mcp`) — v0.1.3 published
- [x] **Negation support**: `NOT` keyword → Prolog `\+`
- [x] **Arithmetic constraints**: `$x > 90`, `$x >= $y` in rules
- [x] **Multi-line rules**: body on next lines
- [x] **Conjunction queries**: `pred1($x) AND pred2($x)` with variable dedup
- [x] **IT Security & Compliance demo**: 3,872 facts, 3 layers
- [x] CI pipeline (GitHub Actions: PyPI publish on release)
- [x] MCP Registry: `io.github.meob/euclid-mcp` v0.1.3
- [x] Awesome MCP Servers: PR [#10007](https://github.com/punkpeye/awesome-mcp-servers/pull/10007)
- [x] **Security hardening**:
  - Input sanitization: rejects Prolog directives (`:- shell`, `halt`, `consult`, etc.)
  - Hard limits: `max_solutions ≤ 1000`, `max_depth ≤ 500`, knowledge ≤ 500KB
  - Error sanitization: strips temp file paths from error messages
  - 28 security tests (injection, DoS, limits, error sanitization)
- [x] **`docs/EUCLID_IR.md`**: comprehensive language reference (~300 lines)
- [x] **`@version` directive**: `@version 1.0` in Euclid-IR, parser + model + 4 tests
- [x] **Documentation refresh**: README (tools overview, all 4 tools with examples), AGENTS (concrete examples), EUCLID_IR (quick reference, multi-tool workflow)
- [x] **Docker image**: `swipl:stable` base, non-root user, MCP stdio + HTTP API modes, docker-compose, .dockerignore
- [x] **Lint + type checking**: ruff (0 errors) + mypy (0 errors), `types-PyYAML`, config in `pyproject.toml`

## Short term (usefulness)

- [ ] README examples with Ollama (test with Llama 3B, Qwen 2.5 7B)
- [ ] Policy Compiler

## Medium term (quality)

- [ ] Test coverage su server.py (error paths)
- [ ] **Named knowledge bases**: Save/load KBs for reuse across sessions
- [ ] **`explain` tool**: Convert proof tree to natural language via LLM

## Long term

- [ ] **Prolog-free mode**: Implement a naive deduction engine in Python for users without SWI-Prolog
- [ ] **Answer Set Programming**: Add ASP backend (via Clingo) for constraint-heavy problems
- [ ] **Performance**: Daemon mode, optimizations
- [ ] **Long Term Memory**: For huge rule sets
- [ ] **Probabilistic facts**: `rain(0.7)` — attach confidence to facts
- [ ] **Web UI**: Simple playground for experimenting with the fact language
- [ ] **Benchmark suite**: Compare LLM-only vs LLM+Euclid reasoning accuracy
- [ ] **Multi-language client SDK**: TypeScript, Rust bindings alongside Python
- [ ] **Bibliography**: List of publications cited
