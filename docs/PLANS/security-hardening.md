# Security Hardening — P1 (in-process) + P2 (scale/HAProxy)

Session of 2026-08-12 did a code-verified security review. Verdict: the
security model is sound; the gaps below are performance/robustness, not
code-execution. Resume here.

## Review baseline (verified against source)

- **Real security boundary = meta-interpreter** (`euclid_mcp/prolog_engine.pl`):
  user goals are only matched with `clause/2` (SWI raises `permission_error` on
  built-ins); the only goals executed directly are arithmetic comparisons gated
  by `is_arith_goal/1` (closed set of operators, args evaluated as numeric
  expressions). The engine never builds or `call/1`s arbitrary terms.
- **Sanitizer** (`euclid_mcp/sanitizer.py`, 58 lines): blacklist of Prolog
  directives (`:- ...`), dangerous built-ins (`shell`, `halt`, `consult`,
  `assert`, `retract`, `retractall`, `process_create`, `open_process`,
  `set_prolog_flag`, `load_files`, `use_module`) and reserved `euclid_rule_id`.
  Comment lines (`#`, `//`, `%`) and `@version` are skipped. Applied to BOTH
  knowledge and query (`euclid_mcp/server.py:47` and `:52`).
- **Prolog-side time limit EXISTS**: `call_with_time_limit(Timeout, ...)` in
  `prolog_engine.pl:92` (default 30 s, request-driven); engine replies
  `{"status":"timeout"}` on `time_limit_exceeded`.
- **Engine self-healing EXISTS**: relaunch on crash, relaunch-once-and-retry on
  broken pipe, and `_read_response` select backstop (`timeout + 5` s) terminates
  the engine if the Prolog time limit fails to fire
  (`euclid_mcp/prolog_server.py:114-165`).

Earlier session notes claiming "no time limit / no watchdog / placeholder
`_is_pure_comment`" were based on corrupted tool output and are RETRACTED.

---

## P1 — in-process hardening

### P1-1 (main gap): cap solutions in the Prolog snippet, not only in Python

- Today: `solutions[:max_solutions]` in `euclid_mcp/server.py:459` is the ONLY
  cap. `build_query_snippet` (`euclid_mcp/translator.py:350-387`) emits
  `forall(prove(Query, MaxDepth, Proof), ...)` which enumerates EVERY solution;
  the engine buffers the whole result set as one string
  (`with_output_to(string(Json), call(Snippet))`, `prolog_engine.pl:93`).
- Explosive queries (dense cross-products, ungrounded recursion) burn engine
  CPU and memory up to the 30 s limit even though the caller only wants 5
  results.
- **Fix (DONE, 2026-08-12)**: a counter in the generated snippet stops the
  enumeration after `MaxSolutions`. Implemented with SWI's non-backtrackable
  globals (`nb_setval/2` + `nb_getval/2`) rather than a dynamic
  `retractall`/`assertz` counter: no workspace pollution (stats stay clean),
  no engine change needed. Applies to `build_query_snippet` and to the legacy
  single-shot `_generate_output`:
  ```prolog
  nb_setval(euclid_solution_count, 0),
  forall(
      ( prove(Query, MaxDepth, Proof),
        nb_getval(euclid_solution_count, C0),
        C0 < MaxSolutions,
        C1 is C0 + 1,
        nb_setval(euclid_solution_count, C1) ),
      ( proof_to_json(Proof, JProof), array_separator, Result..., json_write(...) )
  )
  ```
  Kept the `forall` streaming shape (JSON array output unchanged). The
  Python-side `solutions[:max_solutions]` slice stays as a cheap guard.
- **Acceptance (DONE)**: `benchmarks/solution_cap_benchmark.py` shows the
  capped query-phase time stays flat while uncapped scales
  (10k facts: 3.1 ms capped vs 122 ms uncapped, ~39× and rising);
  engine-level test `test_query_caps_solutions` + `test_max_solutions_capped_in_engine`.

### P1-2: add a query-length cap

- `server.py` caps KB size (`MAX_KNOWLEDGE_LENGTH = 500_000`, `server.py:89-90`)
  but there is no cap on the `query` parameter.
- **Fix (DONE, 2026-08-12)**: `MAX_QUERY_LENGTH = 5_000` added and enforced in
  `reason` (which `explain`/`diagnose`/`what_if` delegate to) next to the
  `max_solutions`/`max_depth` bounds checks. Also fixed a defense-in-depth
  gap found during the work: the `query` parameter previously bypassed the
  sanitizer (only the KB text was sanitized, inside `parse`); it is now
  sanitized too.

### P1-3: bound the long-lived engine's memory

- Each `load` clears dynamic predicates (`clear_workspace`,
  `prolog_engine.pl:148-154`), so no fact/rule leak between requests. Remaining
  drift is SWI's atom table and stack growth over a long-lived process.
- **Fix (DONE, 2026-08-12)**: `PrologServer` gains a `restart_every` policy
  (default 1000 requests, `0` disables). The engine is terminated after N
  requests (relaunched lazily on the next request) and always dropped after a
  `status:timeout` recovery — the relaunch resets the atom table. Tests:
  `test_restart_after_request_count`, `test_restart_after_timeout`.

### P1-4 (optional): reduce sanitizer false positives

- Blacklist word-boundary tokens match inside legitimate atoms/strings
  (`open_ai`, `"write a review"`). Optionally tighten to call-form only
  (token followed by `(`) or post-parse structural checks. Non-blocking.
- **Fix (DONE, 2026-08-12)**: string literals (`"..."` / `'...'`) are now
  masked before the blacklist scan — they are inert data, never parsed as
  calls. A YAML-value directive is re-scanned post-parse in `_parse_yaml`
  (the raw YAML text masks it), so the `test_parse_rejects_yaml_injection`
  guarantee is preserved. Call-form rejection outside strings is unchanged.

---

## P2 — scale & availability behind HAProxy

- Requests are **stateless** (the KB travels with the request), so no session
  affinity: N replicas behind a load balancer, any instance serves any request.
  (Already documented in README "Scalability" and IDEAS.md.)
- Reference architecture: HAProxy frontend →
  - health check = engine `ping` endpoint (or HTTP API `/health`)
  - rate limiting at the edge
  - backend timeouts + circuit breaking on `status:timeout`
  - per-container CPU/memory limits; max body size on the HTTP API
- **DONE (2026-08-12)**: consolidated as `docs/PRODUCTION.md` (deployment,
  HAProxy reference config, security hardening, monitoring, troubleshooting);
  README "Scalability" links to it. No in-repo code beyond the doc.
- **HAProxy is NOT a substitute for P1**: a pathological query still ties up
  one backend; P1 (timeout + solution cap + restart) is what makes each backend
  recoverable. With P1 in place, a replica battery behind HAProxy is a
  sufficient production architecture.
- Optional later (already in IDEAS.md): in-process engine pool +
  `ThreadingHTTPServer` for concurrency inside one instance.

---

## Acceptance checklist

- [x] P1-1 snippet counter: explosive query returns ≤ N solutions, benchmark
      shows early stop (`benchmarks/solution_cap_benchmark.py`)
- [x] P1-2 query-length cap enforced + tested
- [x] P1-3 periodic restart + restart-after-timeout, tested via
      `test_restart_after_request_count` / `test_restart_after_timeout`
- [x] P1-4 sanitizer false-positive case reviewed (string literals masked;
      YAML re-scanned post-parse)
- [x] Full suite: `ruff check .`, `mypy euclid_mcp integrations`,
      `pytest --cov=euclid_mcp --cov=integrations` (fail_under 80) — 239 passed,
      84.4% coverage
