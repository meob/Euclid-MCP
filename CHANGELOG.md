# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.4.0] — 2026-08-14

### Added
- **Exposed KB identity (C4)** — every tool result (`ReasonResult`,
  `ExplanationResult`, `DiagnosisResult`, `WhatIfResult`, `KBCheckResult`) now
  carries `content_hash` (sha256 of the KB text payload) and `version` (from the
  `@version` directive, when present), on **every** return path including error
  branches. `kb_fingerprint` (`euclid_mcp/engine.py`) is now public. The HTTP
  API exposes both fields on `/reason`, `/explain`, `/diagnose`, `/what-if`,
  and `/check-kb`. Anyone with the `.euclid` text can recompute the hash and
  verify which exact KB a result was computed from — the foundation for KB
  versioning, signatures, and audit trails.
- **Native Euclid-IR engine** (`euclid_mcp/ir_parser.py`, `euclid_mcp/ir_engine.py`):
  a pure-Python engine that interprets Euclid-IR directly — facts, rules,
  recursive rules, conjunctions, negation as failure (`NOT`), arithmetic
  (`> >= < <= == != is =` with `+ - * /`), rule ids, string literals and
  wildcards — and produces the same proof trees as the Prolog backend.
  Designed for small knowledge bases where SWI-Prolog cannot be installed
  (e.g. minimal containers); full semantics, limitations and the supported
  test matrix are documented in `docs/NATIVE_ENGINE.md`.
- **Inference-backend dispatcher** (`euclid_mcp/engine.py`): a single `execute`
  dispatch point selects the backend via `EUCLID_BACKEND` (`auto` | `prolog` |
  `native`, default `auto` → SWI-Prolog when on `PATH`, otherwise native) or
  the new `--backend` CLI flag. All tools (`reason`, `explain`, `diagnose`,
  `what_if`, `check_kb`) route through it, so swapping the engine never
  touches the tool layer.
- **Native engine tests** (`tests/test_native_engine.py`): 23 tests covering
  deduction, recursion, negation, arithmetic, strings, wildcards, limits
  (`max_solutions`, depth, timeout) and the dispatcher — run in every CI matrix
  even without SWI-Prolog.
- **First native-vs-Prolog benchmark** (`benchmarks/native_vs_prolog_benchmark.py`
  + `benchmarks/docs/07-native-vs-prolog.md`): head-to-head on example 07 with
  result parity (all solution counts match); native ~7× slower aggregate but
  only ~1.3–2.5× on typical queries, blowing up (17–32×) on high-solution
  wildcard joins and exhaustive-failure `NOT` queries.

### Fixed
- Example 08 (Cluedo) game-state KB rewritten from Prolog-style
  `.`-terminated facts (one per line) to idiomatic Euclid-IR, so it also runs
  on the native engine.

## [0.3.1] — 2026-08-13

### Added
- **HTTP API authentication & TLS** (`integrations/euclid_api.py`): opt-in
  `EUCLID_API_KEY` (or `--api-key`) requires `Authorization: Bearer <key>` on
  every POST (constant-time check, `401` otherwise, `/health` stays open for
  load balancers), and `EUCLID_TLS_CERT` / `EUCLID_TLS_KEY` (or
  `--certfile` / `--keyfile`) serve HTTPS directly. Setup and posture
  documented in `docs/PRODUCTION.md` → "Authentication & TLS".
- **Python 3.13 and 3.14 support**: verified end-to-end (lint, mypy, and the
  full test suite) on CPython 3.13 and 3.14. New PyPI classifiers advertise
  both, and the CI matrix now runs on Python 3.10–3.14.
- **Stress & soak benchmark** (`benchmarks/euclid_bench.py`): detects response
  mixing, KB pollution, and engine errors across periodic restarts; it is the
  regression detector for the load+query atomicity and the periodic-restart
  policy (must stay PASS at `--workers 4`).
- **Benchmark documentation**: one detail page per benchmark
  (`benchmarks/docs/`) plus a catalog of results and consequent
  implementation choices (`benchmarks/BENCHMARKS.md`).
- **SWI-Prolog compatibility matrix** (`benchmarks/docs/06-swi-prolog-versions.md`):
  the full suite passes on SWI-Prolog 8.4.2, 9.0.4, 9.2.9, and 10.0.2 —
  verified after the 9.x autoloader bug below was fixed.

### Performance
- **KB preload optimization**: repeated loads of the same knowledge base now
  skip re-parsing and re-asserting. Python-side parse+translate results are
  cached per KB source (`_translate_cached`), and the engine skips the
  workspace rebuild when the `load` carries the same `kb_hash` (reply
  `skipped:true` with the stored stats). A repeated identical KB at 20 000
  facts drops from ~196 ms to ~18 ms per load (and the query still runs);
  `explain`, `diagnose`, and `what_if` inherit the win through `reason`, and
  the HTTP API benefits as well. `assert`/`retract` invalidate the
  fingerprint so the next load rebuilds the workspace.

### Fixed
- **Engine workspace sweep is SWI-Prolog 9.x-safe**: `clear_workspace/0`
  retracted every dynamic predicate, including SWI-Prolog's own dynamic
  bookkeeping (e.g. `$search_path_file_cache/3`, `prolog_file_type/2`,
  `$autoload_nesting/1`). On SWI-Prolog 9.x those are dynamic too, so the
  sweep corrupted the autoloader and the next library autoload (e.g.
  `maplist/2`) died with `domain_error(file_type, prolog)` — every tool call
  failed with "Euclid engine error". The engine now tracks the loaded
  workspace in an explicit predicate registry (`workspace_predicate/1`) and
  clears only that; `stats` counts only the registered user predicates. The
  engine is now portable across SWI-Prolog 9.x (CI/Ubuntu) and 10.x.
- **Periodic engine restart**: the restart fired at the end of the request
  that crossed the threshold, stranding the paired query on a bare engine
  (`existence_error` on the per-load `prove/3` → `engine_error`). It now
  fires before the next `load`, so a relaunched engine always receives its
  workspace first. Regression coverage in `tests/test_prolog_server.py`.
- **Load+query atomicity gap**: `prolog_bridge.execute` ran `load` and `query`
  as two separately-locked pipe exchanges, so concurrent workers could
  interleave one request's workspace into another's query (~50% response
  mixing at `--workers 4` in `euclid_bench.py`). `PrologServer.load_and_query`
  now holds the server lock across both steps — a single atomic exchange.
  Regression coverage in `tests/test_prolog_server.py` and the benchmark
  flips from FAIL to PASS at `--workers 4`.

## [0.3.0] — 2026-08-12

### Added
- **Unicode atoms** (`\p{L}`): predicate names, arguments, and rule IDs can now
  be any Unicode letter (CJK, Cyrillic, Greek, …), e.g. `父(张三)` or
  `Бог(Иван)`. Case folding is ASCII-only — `Parent(TOM)` still normalizes to
  `parent(tom)`, while `БОГ(иван)` and `бог(иван)` stay distinct predicates.
  Non-ASCII and uppercase-initial atoms are single-quoted on the Prolog side so
  the engine can never misread them as variables. Covered end-to-end in
  `tests/test_unicode_atoms.py`.

### Changed
- **Persistent SWI-Prolog engine**: replaces the per-call subprocess model. A
  single long-lived `swipl` process is started once and kept alive, connected
  to the server by a JSON-lines pipe (`euclid_mcp/prolog_server.py`,
  `euclid_mcp/prolog_engine.pl`). Each request reloads only the workspace
  (dynamic predicates are cleared and re-asserted over the pipe) instead of
  booting Prolog and consulting a temp file, and the meta-interpreter and
  proof serializer stay resident. Same external API and identical solution
  ordering — pure performance work.
- **Streaming query results**: the generated query snippet writes the JSON
  array of solutions directly to the engine's output via `forall/2` +
  `json_write/3` instead of collecting them in a `findall/3` term, and the
  engine returns the array as a string that the client decodes. No
  double-serialization, low memory on large result sets.
- **Benchmark**: `benchmarks/persistent_engine_benchmark.py` compares the
  stateless (pre-0.3.0) path against the persistent engine across KB sizes
  (100/1k/10k facts) and query shapes (ground / full scan). Measured on the
  reference machine: ~3×–42× steady-state speedup, mean ~14× across cases;
  the persistent path is faster in every measured configuration.
- **Canonical rule-ID marker is now `# RULE:`** (uppercase). The parser remains
  case-insensitive (`# rule:`, `# Rule:` all work), but documentation and
  examples now use `# RULE: <id>` to match the Euclid-IR keyword convention.
  Tests keep exercising the lowercase forms to pin case-insensitivity.
- **README**: new "Scalability" section — persistent engine, stateless
  requests, horizontal scale-out behind a load balancer.

## [0.2.0] — 2026-08-10

### Added
- **`explain` tool**: deterministic proof-tree → natural-language reasoning
  steps (`euclid_mcp/explain.py`). Walks each solution's proof tree and renders
  readable steps in plain language, citing the rule ID when a rule has one —
  no LLM involved, so explanations stay auditable. Exposed over MCP
  (`euclid-mcp_explain`) and HTTP (`POST /explain`).
- **Knowledge Base preload**: a KB can be loaded once at server startup via the
  `EUCLID_KB_PATH` env var or a `--kb-path` CLI flag (`python -m euclid_mcp`,
  console script, and `integrations/euclid_api.py`). The file is validated with
  `check_kb` at import time and fails fast with a clear message on a missing,
  unreadable, oversized, or invalid file. A generic markdown digest of the
  preloaded KB (new `euclid_mcp/kb_summary.py`: fact/rule/predicate counts,
  predicate inventory with arities, rules with their IDs) is appended to the
  server `instructions`, so agents see what the preloaded KB covers without
  extra tool calls. The HTTP API accepts requests without a `knowledge` field
  when a KB is preloaded.
- **Rule IDs**: rules can carry an audit-trail ID via a trailing `# rule: <id>`
  comment (case-preserving, also on the last body line of multi-line rules).
  The ID is surfaced as `rule_id` on `rule` nodes of proof trees, so a decision
  can be cited ("this derives from rule RBAC-0043"). Backward compatible: rules
  without an ID behave exactly as before and their proofs omit the field.
  `check_kb` warns on duplicate rule IDs; `# rule:` on a fact/query is a parse
  error; the reserved internal marker `euclid_rule_id/1` is rejected by the
  sanitizer. Rule bodies in proof output no longer leak the internal marker.
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
- `is` is now validated as a reserved keyword and rejected as a predicate name

### Changed
- **Optional knowledge**: `knowledge`/`base_knowledge` on `reason`, `explain`,
  `diagnose`, `what_if`, and `check_kb` are now optional
  (`str | None = None`). An explicit value always wins; an empty value falls back
  to the KB preloaded from `EUCLID_KB_PATH` (or a `--kb-path` flag). With neither
  provided, tools return a clear "No knowledge provided" error. Backward
  compatible: passing `knowledge` explicitly behaves exactly as before.
- Migrated to **MCP Python SDK v2** (`mcp>=2.0`): `FastMCP` → `MCPServer`
  (`mcp.server.mcpserver`), explicit server name preserved (`Euclid-MCP`).
  Unlocks in-memory testing via `Client(mcp)` (no stdio/ports), hardened stdio,
  stricter protocol validation, and structured `output_schema` on all tools.
  The previous `mcp>=1.27,<2` pin (which blocked SDK 2.0 after it removed
  `mcp.server.fastmcp`) is lifted.
- **Examples**: example 07 (`it_security_compliance`) gained an `--mode explain`
  demonstrating readable reasoning steps with rule ID citations; its policy and
  standard rules carry `# rule:` IDs.
- **Docs**: README, `docs/EUCLID_IR.md`, `AGENTS.md`, and
  `integrations/README.md` now document the `explain` tool, KB preload
  (`EUCLID_KB_PATH` / `--kb-path`), and the `# rule:` syntax with `rule_id` in
  proof output. `.opencode.json`'s `reasoning-engine` agent covers all 5 tools.
- README: shields.io badges (PyPI, Python versions, license, CI, coverage) and
  a Development section with the standard check commands
- `==` replaces `=:=` as the documented arithmetic-equality operator (`=:=` is
  still accepted for backward compatibility); `==` now also works in queries,
  and `==`/`!=`/`<=` inside quoted strings are no longer rewritten
- Keywords (`IF`/`AND`/`NOT`) and the `@version` directive are now
  case-insensitive (`if`/`and`/`not` and `@VERSION` are accepted)
- `what_if` modifications now split on `AND`/`and` case-insensitively

### Fixed
- License detection: replaced the short header-only `LICENSE` with the full
  Apache-2.0 text so GitHub resolves the license (badge + repo metadata)
- CI: bump `actions/checkout@v4`→`v5`, `actions/setup-python@v5`→`v6`,
  `codecov/codecov-action@v5`→`v6` (Node 20 runtime is deprecated on runners)
- Fixed lint issues across examples, benchmarks, and integrations (ruff clean)
- Fixed `mypy` type errors in HTTP API and CLI wrappers

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
