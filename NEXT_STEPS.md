# Next Steps

## Open point: closed-world `check_kb` vs. open-world (load-once) knowledge bases

**Status**: open — to investigate
**Discovered**: 2026-08-22, while building `samples/regulation/pci_dss/` (local, gitignored)

### Problem

`check_kb` validates a KB against a **closed-world contract**: every predicate
referenced in a rule body must be *defined* in the same payload, i.e. have at
least one fact or one rule head (`euclid_mcp/validation.py`, Check 2,
"undefined predicate"). The same applies to the query (Check 4).

This conflicts with the intended lifecycle for regulation-style KBs:

- the stable layer contains **rules only** and is loaded once, never edited;
- entity/session facts arrive at query time via `delta_knowledge`.

Under this design the stable layer can never validate green: every input
predicate (e.g. `merchant/1`, `annual_combined_txn_volume/2`) is flagged as
`undefined_predicate`. Symmetrically, a fact-only delta template fails Check 4
because it queries predicates defined by the base KB, not by itself. The only
payload that validates green is the full base+delta concatenation assembled at
query time — which defeats "validate once, load once".

### Related latent issue found while probing workarounds

The classic Prolog predeclaration idiom `pred(X) :- false.` breaks the SWI-Prolog
backend with a bare `engine_error`:

- the injected meta-interpreter resolves goals through `clause(Goal, Body)`;
- `false/0` is an alias of built-in `fail/0`, and SWI-Prolog 10 raises
  `permission_error(access, private_procedure, fail/0)` on `clause/2` over
  built-ins; the engine loop's catch-all turns any exception into
  `error:'engine_error'`, discarding the message.

The pure-Python native engine handles `IF false` bodies correctly, so the
failure is backend-specific and silent until hit.

### Workaround adopted (no code changes)

Vocabulary declarations with an **intentionally unsatisfiable arithmetic
guard**:

```
merchant($m) IF 1 > 2
annual_combined_txn_volume($m, $n) IF 1 > 2
```

Properties that make this safe:

- the head defines the predicate → Check 2 passes, standalone KB validates green;
- the guard is routed through the arithmetic branch of both engines and simply
  fails — `clause/2` is never called on a built-in, so no permission error;
- it can never contribute a solution, so inference results are untouched
  (verified on all sample cases, both backends).

Drawbacks: rule counts are inflated by one declaration per vocabulary
predicate, the idiom is unusual for auditors reading the KB, and bare
`IF false` remains a trap for anyone who tries the more natural spelling.

### Candidate solutions

1. **`@predicate` directive in Euclid IR** (preferred)
   - Syntax: `@predicate merchant/1, channel_ecommerce/1, ...` parsed like the
     existing `@version` directive.
   - Parser: collect declarations on the `KB` model.
   - Validator: declared predicates count as defined for Checks 2 and 4.
   - Translator / Prolog bridge: include declared signatures in the dynamic
     declaration list (mechanism already exists — `kb_to_decls_clauses`).
   - Native engine: unknown predicates already fail cleanly.
   - Pros: explicit, self-documenting, keeps validator strictness for typos.

2. **Soften Check 2/4 to warnings when a predicate is referenced only by bodies**
   - Configurable strictness on `check_kb`.
   - Pros: zero new syntax. Cons: weakens typo detection exactly where it
     matters most (long regulatory vocabularies); errors become advisory noise.

3. **Make the meta-interpreter robust to built-in body goals**
   - Guard `clause/2` branches with `\+ predicate_property(Goal, built_in)`
     so built-ins fail cleanly instead of raising, and/or add explicit
     `prove(false, _, _) :- !, fail.` handling of `true`/`false` literals.
   - Pros: fixes the latent `engine_error` regardless of solution 1/2; makes
     `IF false` a legitimate idiom. Cons: does not by itself let a rules-only
     KB validate green (still needed: 1 or 2).

Recommended path: implement **1 + 3** together; keep the unsatisfiable-guard
workaround documented in `samples/README.md` until 1 lands.
