# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed
- Pin `mcp>=1.27,<2`: MCP Python SDK 2.0 (2026-07-28) removed the
  `mcp.server.fastmcp` module, breaking the server import and all CI tests.
  Migration to `MCPServer`/standalone `fastmcp` is tracked in TODO
- CI: bump `actions/checkout@v4`→`v5`, `actions/setup-python@v5`→`v6`,
  `codecov/codecov-action@v5`→`v6` (Node 20 runtime is deprecated on runners)

### Added
- Dependabot (`.github/dependabot.yml`): weekly update PRs for pip and GitHub Actions
- Reproducible CI install: `uv sync --frozen --extra dev` from `uv.lock` instead of
  floating `pip install` (prevents unpinned upgrades like `mcp` 1.x → 2.x breaking CI)
- Test coverage for HTTP API (`tests/test_api.py`) and CLI (`tests/test_cli.py`)
- `per-file-ignores` in ruff config for demo scripts (`examples/`, `benchmarks/`)
- `mypy` coverage extended to `integrations/`
- CI workflow on push/PR: Python 3.10-3.12 matrix, ruff, mypy, pytest with coverage,
  Codecov upload (`.github/workflows/ci.yml`)
- Structured logging: every tool call logs name, elapsed time, and outcome;
  controllable via the `EUCLID_LOG_LEVEL` env var
- Request tracing in the HTTP API: `X-Request-Id` header is echoed on the response
  and included in access logs
- Pre-commit hooks (`.pre-commit-config.yaml`): ruff, mypy, pytest
- Coverage gate: `fail_under = 80` enforced by pytest-cov
- `pre-commit` added to dev dependencies

### Changed
- Fixed lint issues across examples, benchmarks, and integrations (ruff clean)
- Fixed `mypy` type errors in HTTP API and CLI wrappers
- README: shields.io badges (PyPI, Python versions, license, CI, coverage) and
  a Development section with the standard check commands

## [0.1.3] — 2026-07-13

### Added
- `diagnose` tool: query analysis with `why`, `why_not`, `what_needs` modes
- `what_if` tool: scenario analysis with fact additions/removals
- `check_kb` tool: knowledge base validator (syntax, undefined predicates, circular rules, duplicates)
- `max_solutions` parameter exposed in MCP tool (passed to translator)
- Input sanitizer: rejects dangerous Prolog directives (`shell()`, `halt()`, `:-` injection)
- Hard limits: max 500 KB input, max 500 depth, max 1000 solutions, 30 s timeout
- Error message sanitization (strips internal file paths from Prolog errors)
- Glama registry metadata (`glama.json`)
- EUCLID_IR.md language reference document

### Changed
- Security hardening across the full pipeline (sanitize → parse → translate → execute)

## [0.1.2] — 2026-07-13

### Added
- `max_solutions` parameter to translator and server
- Security hardening: input sanitization, hard limits, error sanitization
- EUCLID_IR.md language reference

### Fixed
- Translator passes `max_solutions` through to Prolog query limits

## [0.1.1] — 2026-07-12

### Added
- Arithmetic comparisons in rules (`>`, `>=`, `<`, `<=`, `=:=`, `=\=`)
- Negation operator (`NOT` → Prolog `\+`)
- Multi-line rule parsing (body on next lines)
- Conjunction queries with variable deduplication
- IT Security & Compliance demo (3,872 facts, 10 questions)
- Unit tests for new features (25 total, all passing)
- MCP Registry metadata (`server.json`)
- GitHub Actions workflow for PyPI publishing

### Changed
- Updated MCP server `instructions` with new capabilities
- Translated `pyproject.toml` description to English

### Fixed
- Meta-interpreter now handles built-in arithmetic operators
- Query conjunctions correctly wrapped in Prolog parentheses
- NOT operator converted to Prolog negation (`\+`)
- Multi-line rules no longer split into separate statements

## [0.1.0] — 2026-07-01

### Added
- Initial release
- Euclid IR parser (text + YAML formats)
- Prolog translator with meta-interpreter for proof trees
- MCP server with `reason` tool
- Examples: genealogy, RBAC, classification, loan eligibility, compliance auditor
