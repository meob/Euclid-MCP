# Plan: Euclid-MCP core integration for Euclid-Studio (semantic phase)

**Status**: done — FASE 1 (C4), FASE 2 (C5), and FASE 3 (C3) all committed inside v0.4.0.
**References**: `staff/euclid-studio-design.md`, `staff/euclid-studio-mockup.html`, `README.md`,
`AGENTS.md`, `docs/EUCLID_IR.md`, `euclid_mcp/` (engine source).
**Scope**: the three core-side items agreed with the Euclid-Studio designer — named KBs
(`kb_id` + `delta_knowledge`), structured (language-independent) `explain`, and exposed
verifiable KB identity. Explicitly **out of scope**: namespaces (C6) and `@predicate`
i18n labels (C2 — arity-only, later phase).

---

## Session log

> Updated at the end of each working session so a fresh (context-reduced) session
> can resume without re-reading the whole repo.

- **Session 3 (2026-08-15) — FASE 3 (C3: named KBs): DONE & COMMITTED.**
  - Same version decision as FASE 1/2: ships inside **v0.4.0**, no `uv.lock` bump;
    CHANGELOG entry folded into the existing `[0.4.0]` section.
  - Commit: the one created in this session — verify with `git log --oneline -3`
    (parent was the C5 commit **36eb80ae**).
  - What was done: new `euclid_mcp/kb_store.py` (`KB_ID_PATTERN`, `KBRecord`,
    `KbStore` with `RLock` + `max_kbs=32`, no internal validation);
    `server.py` (`_kb_store` global, `_resolve` resolver replacing
    `_resolve_knowledge` on all 5 tools, new params `kb_id`/`delta_knowledge`,
    3 new MCP tools `register_kb`/`unregister_kb`/`list_kbs`);
    `integrations/euclid_api.py` (3 new POST endpoints `/register-kb`,
    `/unregister-kb`, `/list-kbs`, param forwarding + guard updates on the 5
    reasoning endpoints); tests (`tests/test_kb_store.py` new,
    `test_security.py` kb_id/delta injection, `test_tools.py` precedence +
    `Unknown kb_id` + tool listing now 8 tools, `test_api.py` new endpoints);
    docs (README, AGENTS.md, integrations/README.md, docs/EUCLID_IR.md,
    docs/MONITORING.md, CHANGELOG under `[0.4.0]`).
  - Design decisions confirmed during the session:
    - `what_if` signature places `kb_id`/`delta_knowledge` next to
      `base_knowledge` (per plan); the 8 positional `what_if(base, mods, query)`
      test call-sites were updated to keyword form (README/examples/CLI already
      used keyword args, so no external call-site breaks).
    - `list_kbs` returns **metadata only** (no `source`) to keep responses
      bounded; there is no read-back of a registered KB's source (Studio keeps
      its own copy and re-registers per replica).
    - `delta_knowledge` without a `kb_id` is an explicit error
      ("delta_knowledge requires a kb_id") — it only overlays a registered base.
    - `register_kb` capacity overflow returns an error (not silent).
  - Pre-existing flake still: `tests/test_api.py::TestApiAuth` intermittent
    `ConnectionResetError` — run with `-k "not TestApiAuth"` for a stable run.
  - Verification at commit time: `ruff check .`, `mypy euclid_mcp integrations`,
    `pytest --cov=euclid_mcp --cov=integrations -k "not TestApiAuth"` →
    369 passed, coverage 84.92%.
  - **Plan complete**: all three confirmed phases (C4 → C5 → C3) are shipped.
    C2 (`@predicate` arity) remains scheduled as a later phase (FASE 4, not in
    the confirmed order).

- **Session 4 (2026-08-15) — flaky `TestApiAuth`: FIXED & COMMITTED.**
  - Ships inside **v0.4.0** (no version/lock bump, same policy as F1–F3);
    CHANGELOG `Fixed` entry added under the existing `[0.4.0]` section.
  - Commit: the one created in this session — verify with
    `git log --oneline -3` (parent was the C3 commit **c6c5f15b**).
  - Reproduced first: `TestApiAuth` failed **5/8** consecutive runs with
    `ConnectionResetError: [Errno 54]` on `resp.read()` (confirmed pre-existing
    on the clean tree in earlier sessions).
  - Applied the agreed three-level defense in depth:
    1. **Server `_send`** (`integrations/euclid_api.py`): added explicit
       `Content-Length` + `Connection: close` (client frames the body without
       the EOF-vs-RST ambiguity) and wrapped `self.wfile.write(body)` in
       `try/except (BrokenPipeError, ConnectionResetError, OSError)` logged at
       debug — a client dropping mid-response is normal TCP, not an error.
    2. **Teardown** (`_TestServer.__exit__` in `tests/test_api.py`): reordered
       to `shutdown()` → `thread.join(timeout=5)` → `server_close()`, so the
       serve loop fully drains before the listening socket closes (kills the
       RST window on the accept backlog / in-flight handler).
    3. **Test client `_request`** (`tests/test_api.py`): single bounded retry on
       `ConnectionResetError`/`RemoteDisconnected` (correct consumer behavior;
       a persistently broken server still fails on the retry).
  - Verification: `TestApiAuth` **15/15** consecutive green (was 5/8 failing),
    `tests/test_api.py` 5/5 green, then the full suite **without** the
    `-k "not TestApiAuth"` skip → **375 passed**, coverage **85.17%**
    (fail_under 80 ok). `ruff check .` and `mypy euclid_mcp integrations`
    both clean.
  - **Plan complete**: all three confirmed phases (C4 → C5 → C3) shipped in
    v0.4.0 and the pre-existing auth flake is fixed. C2 (`@predicate` arity)
    remains scheduled as FASE 4 (not in the confirmed order).

- **Next up — FASE 4 (later, NOT in the confirmed order) — C2 `@predicate`
  arity**, per the FASE 4 stub below. Standard verification + coverage ≥ 80.

- **Session 2 (2026-08-14) — FASE 2 (C5: structured explain): DONE & COMMITTED.**
  - Same version decision as FASE 1: ships inside **v0.4.0**, no `uv.lock` bump;
    CHANGELOG entry folded into the existing `[0.4.0]` section.
  - Commit: parent of this session log line was **86449152** (the C4 commit);
    the C5 commit is the one created in this session — verify with
    `git log --oneline -3`.
  - What was done: `models.py` (`ExplainStep` + `Explanation.structured_steps`),
    `explain.py` (two-layer refactor: `explain_solution_typed` + `_render_step`;
    `explain_solution` is now `[_render_step(s) for s in explain_solution_typed(...)]`
    — English strings byte-identical; `_humanize_body` split into
    `_humanize_parts`), `server.py` (`explain()` populates `structured_steps`),
    `integrations/euclid_api.py` (`/explain` adds `structured_steps`), tests
    (`tests/test_explain.py::TestExplainStructured`, `tests/test_api.py`
    `test_explain_structured_steps`), docs (README, AGENTS.md,
    integrations/README.md, docs/EUCLID_IR.md, CHANGELOG under `[0.4.0]`).
  - Structured steps verified identical on **both** backends (SWI-Prolog and
    native `EUCLID_BACKEND=native`): kinds `rule`/`fact`/`neg`/`true`, `rule_id`
    on rule nodes, `body` as conjunct list (marker stripped, `\+`→NOT),
    typed count == English count.
  - Verification (all green at commit time): `ruff check .`, `mypy euclid_mcp integrations`,
    `pytest --cov=euclid_mcp --cov=integrations -k "not TestApiAuth"`.
  - **Next up — FASE 3 (C3: named KBs `kb_id` + `delta_knowledge`)**, per the
    order C4 → C5 → C3. Files to touch: new `euclid_mcp/kb_store.py`
    (`KbStore`, `KBRecord`, `KB_ID_PATTERN`, `max_kbs`), `euclid_mcp/server.py`
    (3 new tools `register_kb`/`unregister_kb`/`list_kbs` + `_resolve`
    resolver with `kb_id`/`delta_knowledge` on all 5 tools),
    `integrations/euclid_api.py` (3 new endpoints + param forwarding),
    tests (`test_kb_store.py`, `test_security.py` kb_id/delta injection,
    `test_tools.py` precedence + `Unknown kb_id`, `test_api.py`),
    docs (README, AGENTS.md, integrations/README.md, EUCLID_IR.md, CHANGELOG
    under `[0.4.0]`). Standard verification + coverage ≥ 80.

- **Session 1 (2026-08-14) — FASE 1 (C4: exposed KB identity): DONE & COMMITTED.**
  - **Version decision (user, binding)**: all phases of this plan ship inside
    **v0.4.0** — no version bump to 0.5.0, no `uv.lock` bump. CHANGELOG entry folded
    into the existing `[0.4.0]` section.
  - Commit: **3af8b05e (native engine, v0.4.0)** was the parent; the C4 commit is
    the one created in this session — verify with `git log --oneline -3`.
  - What was done: `models.py` (5 result models + `content_hash`/`version`),
    `engine.py` (`_kb_fingerprint` → public `kb_fingerprint`), `server.py`
    (`_fill_identity` on every return incl. error branches; `_run_check_kb` sets
    identity), `integrations/euclid_api.py` (5 endpoints expose both fields),
    tests (`test_tools.py::TestKBIdentity`, `test_preload.py` hash test,
    `test_api.py::TestApiIdentity`), docs (README, AGENTS.md, integrations/README.md,
    docs/EUCLID_IR.md, CHANGELOG under `[0.4.0]`).
  - Verification (all green at commit time): `ruff check .`, `mypy euclid_mcp integrations`,
    `pytest --cov=euclid_mcp --cov=integrations` → 309 passed, coverage 84.71%.
  - **Known pre-existing flake**: `tests/test_api.py::TestApiAuth` intermittently fails
    with `ConnectionResetError` (reproduced on the clean tree with `git stash`) —
    unrelated to FASE 1. Run the suite with `-k "not TestApiAuth"` for a stable green run.
  - **Next up — FASE 2 (C5: structured explain)**, per the order C4 → C5 → C3.
    Files to touch: `euclid_mcp/models.py` (ExplainStep + Explanation.structured_steps),
    `euclid_mcp/explain.py` (typed two-layer refactor, existing `steps` strings byte-identical),
    `euclid_mcp/server.py` (`explain()` populates `structured_steps`),
    `integrations/euclid_api.py` (`/explain` adds `structured_steps`),
    tests `test_explain.py` (existing assertions unchanged + new typed-step tests),
    then docs (README, AGENTS.md, integrations/README.md, EUCLID_IR.md, CHANGELOG under `[0.4.0]`).
    Standard verification: `ruff check . && mypy euclid_mcp integrations && pytest --cov=euclid_mcp --cov=integrations`.

---

## 0. Binding decisions (confirmed)

| # | Decision | Consequence |
|---|----------|-------------|
| D1 | **C4 in core** — `content_hash` + `version` exposed on all result models. Hash = sha256 of the **text payload** (`.euclid`), computed by whoever produces the response | Verifiable identity: anyone with `.euclid` + Euclid-MCP can recompute the hash; Studio builds versions/signatures/approvals on top |
| D2 | **C5 in core** — typed, **language-independent** steps; the English `steps: list[str]` remain **derived** from the same steps (backward compatible); Studio renders with localized templates (S6) | Multi-language unlocked without Studio duplicating the proof-tree walk |
| D3 | **C3 in core** — Python **in-memory per-instance registry**; **Prolog engine unchanged**; `kb_id` addresses base + merged `delta_knowledge`; Studio re-registers on every replica | Preserves decision D2 of `euclid-studio-design.md` (no shared files) and the README scale-out story |
| D4 | **C2** — only **arity + declaration + `check_kb` validation + digest** in core; **no i18n labels** (handled with comments) | Later phase, outside the confirmed order |
| D5 | **C6** — no namespaces; prefix at assembly time in Studio | Zero language changes |

**Development order: C4 → C5 → C3.**

---

## FASE 1 — C4: exposed KB identity (Effort S)

### 1.1 `euclid_mcp/models.py`
Add to **all 5 result models** (`ReasonResult`, `ExplanationResult`, `DiagnosisResult`,
`WhatIfResult`, `KBCheckResult`):
```python
content_hash: Optional[str] = None
version: Optional[str] = None
```

### 1.2 `euclid_mcp/engine.py`
Rename `_kb_fingerprint` → `kb_fingerprint` (public) and update the single internal
call site (line 106). No test imports the private name → rename is safe.

### 1.3 `euclid_mcp/server.py`
Single helper (sets identity on any result, including error branches):
```python
def _fill_identity(result, kb_source) -> None:
    result.content_hash = kb_fingerprint(kb_source)
    try:
        result.version = _parse_cached(kb_source).version
    except Exception:
        result.version = None
```
- `reason`: call `_fill_identity` on every return after knowledge resolution.
- `explain` / `diagnose`: same pattern (they already resolve `kb_source`).
- `what_if`: identity of the **base_knowledge**.
- `_run_check_kb`: set `content_hash`/`version` (it already parses `kb` internally).

### 1.4 `integrations/euclid_api.py`
⚠️ The API builds response dicts **field by field** (not `model_dump()` of the whole
model) — C4 requires explicit edits to `/reason`, `/explain`, `/diagnose`, `/what-if`,
`/check-kb` to add `content_hash` and `version`.

### 1.5 Tests
- `tests/test_tools.py`: `reason` returns `content_hash == sha256(knowledge)`; `version`
  from `@version`.
- `tests/test_preload.py`: preload → `content_hash` of the file content.
- `tests/test_api.py`: `/reason`, `/check-kb` expose both fields.
- New: identity present on error branches too (e.g. missing query).

---

## FASE 2 — C5: structured explain (Effort M)

### 2.1 `euclid_mcp/models.py`
```python
class ExplainStep(BaseModel):
    kind: str                    # "fact" | "rule" | "neg" | "true" | "unknown"
    goal: Optional[str] = None
    rule_id: Optional[str] = None
    body: list[str] = Field(default_factory=list)   # conjuncts, already split

class Explanation(BaseModel):
    substitutions: dict[str, Any] = ...
    steps: list[str] = ...
    structured_steps: list[ExplainStep] = Field(default_factory=list)
```

### 2.2 `euclid_mcp/explain.py`
Two-layer refactor (same step count, existing tests stay green):
- `explain_solution_typed(solution) -> list[ExplainStep]`: `_explain_node` now produces
  typed steps (`and` nodes expand into left+right, as today; `_humanize_parts` splits the
  body into conjuncts after stripping `euclid_rule_id` and converting `\+`→NOT).
- `_render_step(step) -> str`: produces **exactly** the current English strings.
- `explain_solution(solution) -> list[str]`: `[_render_step(s) for s in explain_solution_typed(solution)]`
  — signature unchanged.

### 2.3 `euclid_mcp/server.py`
`explain()` populates `Explanation(steps=[...], structured_steps=explain_solution_typed(sol))`.

### 2.4 `integrations/euclid_api.py`
`/explain` adds `structured_steps` to the response (besides `steps`).

### 2.5 Tests
- `tests/test_explain.py`: existing `steps` assertions must stay identical.
- New: `structured_steps` — kinds for fact/rule/neg/true, `rule_id` on rule nodes,
  `body` as conjunct list, typed step count == English step count.

---

## FASE 3 — C3: named KBs `kb_id` + `delta_knowledge` (Effort L)

### 3.1 New `euclid_mcp/kb_store.py`
- `KB_ID_PATTERN = re.compile(r"^[a-z0-9_-]{1,64}$")`.
- `@dataclass KBRecord`: `kb_id, source, content_hash, version=None, facts=0, rules=0, predicates=0`.
- `class KbStore`: `dict[kb_id, KBRecord]` + `RLock`; methods `register(record)`, `get(kb_id)`,
  `unregister(kb_id)`, `list()`, bound `max_kbs` (default 32).
- **No internal validation** (avoids circular import with `server.py`): the `register_kb`
  tool validates first, the registry stays "dumb".

### 3.2 `euclid_mcp/server.py`
- Global instance `_kb_store = KbStore()`.
- **3 new MCP tools**:
  - `register_kb(kb_id, knowledge) -> dict` — validate `kb_id` (allowlist), size
    (≤ `MAX_KNOWLEDGE_LENGTH`), then `_run_check_kb` (reject invalid); build `KBRecord`
    (with `kb_fingerprint`, `version`, counts from `check`), register (overwrite allowed),
    return the record.
  - `unregister_kb(kb_id) -> dict` — remove, `false` if absent.
  - `list_kbs() -> dict` — record list.
- **New params** on `reason`, `explain`, `diagnose`, `what_if`, `check_kb`:
  `kb_id: str | None = None`, `delta_knowledge: str | None = None` (in `what_if` next to
  `base_knowledge`).
- Single resolver:
  ```python
  def _resolve(knowledge, kb_id=None, delta_knowledge=None) -> tuple[str | None, str | None]:
      # (kb_source, error)
      # 1. explicit knowledge wins
      # 2. kb_id: rec=_kb_store.get(); if None → error "Unknown kb_id: X"
      #    else source = rec.source (+ delta_knowledge concatenated if present)
      # 3. fallback _PRELOADED_KB
  ```
  The 5 tools replace `_resolve_knowledge` with `_resolve` and propagate `Unknown kb_id`.

### 3.3 `integrations/euclid_api.py`
- New POST endpoints: `/register-kb`, `/unregister-kb`, `/list-kbs`.
- Forward `kb_id`/`delta_knowledge` on `/reason`, `/explain`, `/diagnose`, `/what-if`, `/check-kb`.
- `register-kb` authenticated like the other POSTs (nothing on `/health`).

### 3.4 Tests
- New `tests/test_kb_store.py`: register/get/unregister/list, overwrite, `max_kbs` bound,
  unknown kb_id.
- `tests/test_security.py`: kb_id injection (`../`, `admin`, spaces, length >64), delta
  oversized, invalid KB rejected.
- `tests/test_tools.py`: `reason(kb_id=...)`; `reason(kb_id=..., delta_knowledge=...)`;
  precedence explicit knowledge > kb_id > preload; `Unknown kb_id` error.
- `tests/test_api.py`: new endpoints + params.

---

## FASE 4 (later, NOT in the confirmed order) — C2 `@predicate` arity
- Directive `@predicate pred(arity)` in the parser (`language.py`).
- `check_kb`: use with undeclared arity → error; used but not declared → warning.
- Arity digest in `kb_summary` (for agents).
- **Arity only — no description/label** (comments cover those). Re-scheduled in a dedicated session.

---

## Verification (every phase)
```bash
ruff check .
mypy euclid_mcp integrations
pytest --cov=euclid_mcp --cov=integrations   # fail_under 80
```

## Docs to update (per phase)
`README.md` (tool table + `kb_id`/`delta_knowledge` params + identity in results),
`AGENTS.md`, `integrations/README.md`, `docs/EUCLID_IR.md`, `CHANGELOG.md`; bump version
`pyproject.toml` (0.5.0) + `uv.lock` at the end of Fase 3.

## Resolved points
1. `register_kb` on an existing `kb_id`: **overwrite allowed** (update semantics, chosen for
   idempotency) — confirmed.
2. Precedence when **both** explicit `knowledge` and `kb_id` are given → `knowledge` wins
   (already planned). Implicitly confirmed.
