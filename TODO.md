# TODO

## Done

- [x] Publish on GitHub
- [x] MCP inspector testing (`mcp dev`)
- [x] 17/17 tests: parsing, translation, Prolog execution (Socrates, ancestor, proof tree, edge cases)
- [x] Edge cases: comments, booleans, YAML, max_depth, underscores, integers + AND
- [x] OpenCode integration: `opencode.json`, `AGENTS.md`, `.opencodeignore`
- [x] Bug fix: `substitutions` type `dict[str, str]` → `dict[str, Any]` (integer values)
- [x] Bug fix: prolog_bridge.py try/except per righe malformate
- [x] Import relativi → assoluti in server.py
- [x] Istruzioni FastMCP: italiano → inglese
- [x] Error messages: italiano → inglese

## Short term (usefulness)

- [x] **Short real cases**: genealogia, RBAC, classificazione biologica, loan eligibility
  - `examples/01_genealogy.py` — ricorsione, soluzioni multiple, proof tree
  - `examples/02_rbac.py` — gerarchia ruoli, ereditarietà permessi, audit trail
  - `examples/03_classification.py` — tassonomia, proprietà per ereditarietà
  - `examples/04_loan_eligibility.py` — regole aziendali, trasparenza decisioni
- [x] **Esempi complessi (data-driven agent workflow)**:
  - `examples/05_compliance_auditor/` — cloud resource compliance via JSON-to-facts
  - `examples/06_loan_eligibility/` — CSV applicant data + policy rules + decision breakdown
- [x] **Integrazioni**:
  - `.opencode.json` — MCP server + `reasoning-engine` agent config
  - `integrations/euclid_api.py` — HTTP API per n8n/Zapier/Make
  - `integrations/euclid_cli.py` — CLI wrapper per shell pipeline
  - `integrations/README.md` — documentazione integrazioni
- [x] **PyPI release** (`pip install euclid-mcp`) — v0.1.1 published
- [x] **Negation support**: `NOT` keyword → Prolog `\+`
- [x] **Arithmetic constraints**: `$x > 90`, `$x >= $y` in rules
- [x] **Multi-line rules**: body on next lines
- [x] **Conjunction queries**: `pred1($x) AND pred2($x)` with variable dedup
- [x] **IT Security & Compliance demo**: `examples/07_it_security_compliance/` — 3,872 facts, 3 layers (standards, policies, data)
- [x] MCP server `instructions` updated with new capabilities
- [x] README updated: Euclid-IR syntax reference, arithmetic, multi-line, NOT
- [x] Unit tests: 25/25 passing (17 original + 8 new)
- [ ] README examples with Ollama (test with Llama 3B, Qwen 2.5 7B)
- [ ] Policy Compiler

## Medium term (quality)

- [x] CI pipeline (GitHub Actions: PyPI publish on release)
- [ ] Lint + type checking (ruff, mypy)
- [ ] Test coverage su server.py (error paths)
- [ ] Docker image with bundled SWI-Prolog
- [ ] **Security**: Sanitize input, sandbox, limits
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
