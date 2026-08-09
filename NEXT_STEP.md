# Euclid-MCP — Session Checkpoint (Aug 8, 2026)

## Completed in this session
- **Case-insensitive keywords** (5 commits): `IF`/`AND`/`NOT`/`@VERSION` now work
  with any casing (parser lowercases normalized lines), `is` added as a reserved
  keyword, `what_if` splits `AND` case-insensitively.
- **Operator alignment**: `==` replaces `=:=` in docs and examples (`=:=` still
  accepted for backward compatibility); `==`→`=:=`, `!=`→`=\=`, `<=`→`=<` in the
  translator with string-literal protection; queries also go through operator
  translation.
- **Docs**: EUCLID_IR.md simplified "subset of Horn-clause logic" phrasing, operator
  table updated; AGENTS.md, README.md, CHANGELOG.md aligned.
- **Tests**: 141 passing, coverage 81.94%, ruff + mypy clean. A/B verified all
  example demos byte-identical before/after the changes.
- **GitHub sync**: `main` fully aligned (0/0 with origin). PR #9 (session work),
  PR #10 (4 pending local commits incl. release v0.1.5), PR #11 (doc fix) merged;
  tag v0.1.5 pushed; work branches deleted.

## Previous sessions
- **Aug 6**: Dev tooling upgrade — CI matrix, ruff/mypy/pytest gate, structured
  logging + `X-Request-Id` tracing, pre-commit hooks, README badges, HTTP API + CLI
  integration tests (131 tests, 82% coverage)
- **Jul 26**: Euclid-IR v1.0 stabilization (case-insensitive identifiers, string literals,
  generic inequality, safe negation linting, `%` comments) — 110 tests
- **Jul 22**: Docker container, lint + type checking (89 tests)
- **Jul 21**: Documentation refresh (tools, examples, EUCLID_IR quick reference)
- **Jul 13**: Security hardening, `diagnose`/`what_if`/`check_kb` tools, PyPI v0.1.3, MCP Registry

## Status
- Tests: 141/141 passing (ruff + mypy clean, coverage 81.94%)
- Working tree clean; local `main` == `origin/main` at `3bc46370`
- CHANGELOG "Unreleased" section holds this session's entries — not yet released

## Next priorities
- [ ] Update this checkpoint + TODO.md on every session end (keep them truthful)
- [ ] Rule IDs (`# rule:` syntax) — language feature → release **v0.2.0**
      (design: `docs/PLANS/rule_ids.md`)
- [ ] Release decision: tag v0.1.6 (unreleased changes accumulated on main) prima,
      poi v0.2.0 con rule IDs
- [ ] Migrate to MCP SDK v2 (currently pinned `mcp>=1.27,<2`)
- [ ] `explain` tool: proof tree → natural language
- [ ] Named knowledge bases: save/load for reuse
- [ ] README examples with Ollama (Llama 3B, Qwen 2.5 7B)
