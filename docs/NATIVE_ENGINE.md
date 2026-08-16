# Native Engine

Euclid-MCP's primary inference engine is **SWI-Prolog**. A pure-Python
**native engine** interprets **Euclid-IR** directly as a fallback for small
knowledge bases where SWI-Prolog cannot be installed.

It is **not** a full replacement for SWI-Prolog: it targets small, well-formed
knowledge bases and deliberately implements a subset of the semantics (Horn
clauses, negation as failure, arithmetic). The full test suite always runs
against the Prolog backend; the native engine adds its own test suite and a
compatibility matrix (see below).

## Activation

The backend is selected by the `EUCLID_BACKEND` environment variable or the
`--backend` CLI flag:

| Value    | Behavior                                                       |
|----------|----------------------------------------------------------------|
| `auto`   | SWI-Prolog if `swipl` is on `PATH`, otherwise the native engine (default) |
| `prolog` | Always the persistent SWI-Prolog engine                        |
| `native` | Always the native engine                                       |

All tools (`reason`, `explain`, `diagnose`, `what_if`, `check_kb`) route
through a single dispatch point (`euclid_mcp/engine.py:execute`), so no tool
changes are needed to swap the backend.

```bash
EUCLID_BACKEND=native euclid-mcp
# or, per invocation:
EUCLID_BACKEND=native python examples/04_loan_eligibility.py
```

## Architecture

```
server.py ──► engine.py (dispatcher) ──► prolog_bridge.py ──► SWI-Prolog
                                     └─► ir_engine.py ──► ir_parser.py (native)
```

* `euclid_mcp/ir_parser.py` — lexer + recursive-descent parser producing a small
  term tree (`Var` / `Atom` / `Number` / `Compound`).
* `euclid_mcp/ir_engine.py` — unification (with occurs check), a depth-limited
  SLD-style solver, negation as failure, arithmetic evaluation, and proof-tree
  construction. `rule_id` markers and string literals are preserved.
* Both backends emit the **same `ProofNode` structure**, so `explain`,
  `diagnose` and `what_if` work unchanged on native proofs.

## Supported

* Facts and rules (Horn clauses), including recursive rules
* Conjunctions (`AND`), multi-line rule bodies
* Negation as failure (`NOT`), same depth limit as the Prolog meta-interpreter
* Arithmetic: `> >= < <= == != is =` with `+ - * /` expressions
  (`$level >= $min_level + 1` works; expressions are evaluated recursively)
* `=` is **unification**, not arithmetic (matches Prolog: `$x = $y + 1`
  binds `$x` to the *term* `y+1`)
* `==` / `!=`: numeric when both sides are numeric, otherwise syntactic
  equality of ground terms (a native extension — Prolog's `=:=` errors there)
* Rule ids (`# RULE: <id>`) surfaced as `rule_id` in proofs and cited by
  `explain`
* String literals (`"..."`, `'...'`) preserved as UTF-8
* Wildcards (`_`), negative numbers (`-90`), hyphenated atoms (`security-ops`)
* Clause ordering matches the Prolog backend (sort by predicate name, then
  statement text), so solution order is identical for typical KBs

## Semantics parity

For the examples in this repo the native engine produces **identical results**
to the Prolog backend — verified per-question on example 07
(`it_security_compliance`, ~577 facts with arithmetic) and examples
01, 02, 04, 08 and 13.

## Limitations (by design)

* **ASCII-only lexer**: Unicode predicate/atom names (e.g. `父(张三)`) are not
  supported natively (SWI-Prolog handles them). The tool-level Unicode support
  tests are therefore `prolog_only`; the native matrix instead asserts the
  clear rejection error (`Query parsing error: Unexpected character …`), so the
  limit is documented rather than silently skipped.
* **No cut** (`!`), lists, `findall`/`bagof`, dynamic `assert`/`retract`,
  modules, or disjunction — same restriction as Euclid-IR itself.
* **Depth-limited recursion** (`max_depth`, default 30) and a wall-clock
  timeout; performance is tuned for small KBs (a few hundred facts), not large
  datasets.
* **One statement per line**: multiple `.`-terminated Prolog-style facts on a
  single line are not supported natively (the Cluedo example was converted to
  idiomatic Euclid-IR for this reason).
* A `-` immediately after a number is read as a negative number, not
  subtraction, so `p(1-2)` parses as two arguments `p(1, -2)` and `$x > 90-1`
  is a parse error. Write arithmetic with spaces (`$a - $b`, `90 - 1`);
  `$a-$b` is rejected with a parse error.
* Unbound variables in comparisons/`is` raise an arithmetic error (as Prolog's
  `=:=`/`is` do on uninstantiated operands).
* Solutions whose query variables are not fully bound are dropped (mirrors the
  Prolog backend's JSON serialization).
* Native Engine is slower than SWI-Prolog
  (see [`07-native-vs-prolog.md`](../benchmarks/docs/07-native-vs-prolog.md)).
  Of course it is not *slower by design* but making it faster is not in our roadmap.

## Test matrix

Run the full suite against the Prolog backend (default), then against the
native engine:

```bash
pytest                          # Prolog backend — full suite (all tests)
EUCLID_BACKEND=native pytest    # native engine
```

Native matrix (this release):

| Result | Tests |
|--------|-------|
| pass   | `tests/test_native_engine.py` (23) + the whole main suite |
| pass   | `test_reason_tool_unicode_rejected_native`, `test_what_if_unicode_rejected_native` (assert the ASCII-only rejection) |
| skip   | `test_reason_tool_unicode`, `test_what_if_unicode` (`prolog_only` — SWI-Prolog Unicode support) |

The CI matrix runs both backends explicitly: the Prolog legs on every supported
Python, plus a `EUCLID_BACKEND=native` leg, so native-specific behaviour is
always exercised on every push/PR.

New tool-level behaviour must keep the Prolog suite green; native-specific
behaviour belongs in `tests/test_native_engine.py`.
