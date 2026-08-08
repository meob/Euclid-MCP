# TODO

## Done

- [x] **Dev tooling upgrade**:
  - CI on push/PR (`.github/workflows/ci.yml`): Python 3.10-3.12 matrix, SWI-Prolog, ruff → mypy → pytest+cov, Codecov upload
  - Ruff clean across the whole repo (per-file-ignores for demo scripts), mypy on core + integrations
  - Coverage gate: `fail_under = 80` enforced by pytest-cov
  - Pre-commit hooks: ruff, mypy, pytest (`.pre-commit-config.yaml`)
  - Structured logging per tool call (`EUCLID_LOG_LEVEL` env var) + `X-Request-Id` tracing in the HTTP API
  - README badges (PyPI, Python versions, license, CI, coverage) + Development section
  - Integration tests for HTTP API and CLI (131 total, 82% coverage)
  - Dependabot (pip + GitHub Actions) and reproducible CI install via `uv sync --frozen --extra dev`
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
- [x] **IT Security & Compliance demo**: 3,869 facts, 3 layers
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
- [x] **Euclid-IR v1.0 stabilization**:
  - [x] **Case-insensitive identifiers**: `Human(ALICE)` → `human(alice)`, reserved keyword check
  - [x] **String literals**: UTF-8 `"..."` / `'...'`, preserves case/whitespace, safe with `IF`/`AND` inside
  - [x] **Generic inequality**: `!=` → `=\=`, `<=` → `=<`
  - [x] **Safe negation linting**: detects unbound variables in `NOT` (warning in `check_kb`)
  - [x] **Comments**: `%` accepted alongside `#` and `//`
  - [x] New module: `linter.py`, 21 new tests (110 total)

## Short term (usefulness)

- [ ] README examples with Ollama (test with Llama 3B, Qwen 2.5 7B)
- [ ] **Migrate to MCP SDK v2** (`mcp.server.mcpserver.MCPServer`): v2.0.0
      (2026-07-28) removed `mcp.server.fastmcp`; currently pinned `mcp>=1.27,<2`.
      Impact is minimal (2 lines in `server.py` + tests). Benefits to exploit:
      - In-memory testing: `Client(target)` → deterministic API tests without HTTP/ports
      - One server for both protocol eras (2025-era clients + 2026-07-28) — no version mismatch
      - Hardened stdio: stray output (e.g. from the SWI-Prolog subprocess) diverted off the wire
      - OpenTelemetry tracing built in (complements existing structured logging)
      - Official tool error semantics (`ToolError`, `result.is_error`)
      - Future: human-in-the-loop via `Resolve(fn)` / elicitation
      Decision (Aug 8): wait a few days for 2.0.x to stabilize before migrating;
      keep the `mcp>=1.27,<2` pin until then. No negative feedback found on 2.0.0.
- [ ] Policy Compiler

## Medium term (quality)

- [ ] Test coverage su server.py (error paths)
- [ ] **Named knowledge bases**: Save/load KBs for reuse across sessions
- [ ] **`explain` tool**: Convert proof tree to natural language via LLM

## Long term

- [ ] **Prolog-free mode**: Implement a naive deduction engine in Python for users without SWI-Prolog
- [ ] **Full Prolog features**: Implement all Prolog features in Euclid-IR: no! Implement all useful features
- [ ] **Answer Set Programming**: Add ASP backend (via Clingo) for constraint-heavy problems
- [ ] **Performance**: Daemon mode, optimizations
- [ ] **Long Term Memory**: For huge rule sets
- [ ] **Probabilistic facts**: `rain(0.7)` — attach confidence to facts
- [ ] **Web UI**: Simple playground for experimenting with the fact language
- [ ] **Benchmark suite**: Compare LLM-only vs LLM+Euclid reasoning accuracy
- [ ] **Multi-language client SDK**: TypeScript, Rust bindings alongside Python
- [ ] **Bibliography**: List of publications cited (done but in some articles)
