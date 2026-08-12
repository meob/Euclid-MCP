# RESUME — Euclid-MCP session handoff

Written 2026-08-12 (session closed due to high context / 99% FS usage).
Pick up here.

## 1. Repo state

- HEAD `2c7c6522` "docs: fold pending changes into released 0.3.0 changelog"
  (v0.3.0 released; Unicode atoms merged). Working tree clean.
- Session opened with 229 tests passing; `ruff check .` and
  `mypy euclid_mcp` clean. Re-run before committing:
  ```
  ruff check .
  mypy euclid_mcp integrations
  pytest --cov=euclid_mcp --cov=integrations
  ```

## 2. What the project is

Euclid-MCP: deterministic logical reasoning engine. Euclid IR → Prolog,
solutions with proof trees. MCP tools: `reason`, `explain`, `diagnose`,
`what_if`, `check_kb`. Persistent SWI-Prolog engine (v0.3.0) over a JSON-lines
protocol; meta-interpreter `prove/3` + `proof_to_json/2` injected by Python on
every load; `RULE: <id>` markers surface as `rule_id` in proofs.

## 3. Next task (resume point): security hardening

A code-verified security review was completed; verdict = sound model, gaps are
performance/robustness. Full plan with verified facts and acceptance criteria:
**`docs/PLANS/security-hardening.md`**.

**P1 is DONE (2026-08-12, uncommitted).** See the plan doc for details:

- **P1-1** solution cap enforced Prolog-side via `nb_setval/2` counter in
  `build_query_snippet` (and legacy `_generate_output`). Benchmark:
  `benchmarks/solution_cap_benchmark.py` (capped time flat, uncapped scales).
- **P1-2** `MAX_QUERY_LENGTH = 5_000` enforced in `reason` (covers
  `explain`/`diagnose`/`what_if`). Also fixed: the `query` param now passes the
  sanitizer (it previously bypassed it).
- **P1-3** `PrologServer(restart_every=N)` — restart after N requests
  (default 1000, `0` disables) and drop engine after a `status:timeout`.
- **P1-4** sanitizer masks string literals before the blacklist scan
  (false positives gone); YAML facts/rules/query re-scanned post-parse in
  `_parse_yaml` so directive injection is still caught.

**Next step: P2 (HAProxy battery)** — reference architecture only, no in-repo
code planned: stateless replicas, `ping`/`/health` checks, edge rate limiting,
backend timeouts + circuit breaking on `status:timeout`, per-container
CPU/memory limits. Verify the working tree with `ruff check .`,
`mypy euclid_mcp integrations`, `pytest --cov=euclid_mcp --cov=integrations`
before committing.

## 4. Key architecture pointers (for fast re-orientation)

- `euclid_mcp/prolog_engine.pl` — JSON-lines engine. `load` clears workspace +
  declares dynamics + asserts; `query` runs the snippet under
  `call_with_time_limit` (prolog_engine.pl:92), replies `status:timeout` on
  exceed; streaming JSON array via `euclid_array_first/0` + `array_separator/0`.
- `euclid_mcp/prolog_server.py` — persistent subprocess, RLock-serialized;
  self-healing: relaunch on crash, relaunch-once on broken pipe, select
  backstop (`timeout + 5`) → terminate + raise.
- `euclid_mcp/translator.py` — IR→Prolog; `build_query_snippet` (line 350) is
  the P1-1 fix site.
- `euclid_mcp/server.py` — limits: `MAX_KNOWLEDGE_LENGTH=500_000`,
  `MAX_DEPTH_LIMIT=500`, `MAX_SOLUTIONS_LIMIT=1000`, timeout=30;
  `sanitize()` on knowledge (line 47) and query (line 52); truncation at 459.
- `euclid_mcp/sanitizer.py` — blacklist of Prolog directives + dangerous
  built-ins; skips `#`/`//`/`%` comments and `@version`. Applied pre-translation.
- `euclid_mcp/prolog_bridge.py` — `execute()`: start → load → query → close.

## 5. Session notes / caveats

- **Tool-output corruption was observed** (duplicated lines, injected/FIXME
  text, wrong-file reads from `read`). Prefer `git diff`/`git show` to verify
  any suspicious file content. Nothing was actually edited in this session.
- **`euclid_mcp/sanitizer.py` appeared "modified" mid-session though untouched**
  (user confirmed they did not edit it). Restored with `git checkout --`.
  If it reappears modified, restore and investigate — do NOT commit blindly.
- Session kept no uncommitted changes except this handoff + the plan doc +
  the IDEAS.md/AGENTS.md additions, which are intentionally uncommitted.

## 6. Docs inventory (relevant to restart)

- `docs/PLANS/security-hardening.md` — P1 + P2 (new).
- `docs/PLANS/` — was empty; future plans go here.
- `IDEAS.md` — P3 added; contains v0.3.0 engine history + review notes.
- `docs/EXAMPLES.md`, `docs/EUCLID_IR.md`, `docs/MONITORING.md`,
  `docs/EVALUATION.md` — existing.
- `CHANGELOG.md` — 0.3.0 released.
