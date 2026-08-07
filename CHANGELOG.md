# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed
- Pin `mcp>=1.27,<2`: MCP Python SDK 2.0 (2026-07-28) removed the
  `mcp.server.fastmcp` module, breaking the server import and all CI tests.
  Migration to `MCPServer`/standalone `fastmcp` is tracked in TODO
- License detection: replaced the short header-only `LICENSE` with the full
  Apache-2.0 text so GitHub resolves the license (badge + repo metadata)
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

## [0.1.5] — 2026-08-07

### Fixed
- `check_kb` reported spurious "recursive rule without base case" errors when a
  rule body referenced a predicate whose name contains another predicate as a
  substring (e.g. `role_level(...) IF deploy_role_level(...)`). Recursive-rule
  detection now matches exact predicate names.
- Example 07 KB: removed six rules in `aws_iam_patterns.euclid` that referenced
  undefined predicates (`last_used_days/2`, `cross_account_role/1`, `iam_user/1`,
  `rotate_keys_90d/1`, `has_wildcard_permission/2`), keeping the KB `check_kb`
  clean (`valid: True`, no errors or warnings).
- Example 07 generated data: duplicate `has_role/2` facts removed
  (`dat_0003`, `sre_0067`, `plf_0142`); `generate_rbac_data.py` now guards
  `secondary_role != primary_role`.
- Example 10 demo readability: darker cyan/gray colors for light terminals,
  "Tools called:" in magenta, aligned banner, scripted mode asks for Enter
  before questions 2..n instead of after the first.

### Added
- `examples/10_llm_vs_euclid/generate_kb_markdown.py` + committed
  `kb_markdown.md`: the condensed markdown digest of the IT Security KB used by
  Bot A in example 10 is now persisted for review instead of being built only
  in memory at startup.

## [0.1.4] — 2026-08-06

### Fixed
- Arithmetic comparisons (`>`, `>=`, `<`, `<=`, `=:=`, `=\=`) silently returned 0
  solutions because the generated Prolog used `member/2` in the meta-interpreter's
  `is_arith_goal/1` without importing `library(lists)`. Thanks to @eddyscanlan for
  the report with root-cause analysis and fix suggestion.

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
