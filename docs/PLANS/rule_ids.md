# Rule IDs — Design (temporary plan; delete after implementation)

**Status**: planned · **Release**: v0.2.0 · **Supersedes**: IDEAS.md "Rule IDs — design"

## Motivation
Audit trail: an auditor must be able to cite the rule that produced a decision.
Suggested by the external reviews (staff/Eu4ChatGPT.md, ChatGPT P1).

## Syntax (approved: inline comment with reserved prefix)

```
can_access($u, $r) IF has_role($u, $role) AND role_perm($role, $r)  # rule: RBAC-0043
```

- Trailing comment `# rule: <id>` on the rule; for multi-line rules, on the last
  body line. Text format only (YAML v1: comments consumed by YAML).
- `# rule:` is reserved; a plain trailing comment (e.g. `# important rule`) stays a
  comment. A standalone line `# rule: X` is an ordinary comment (ignored).
- `# rule:` on a fact/query → parse error. ID case is preserved (extracted before
  lowercasing), like string literals.

## Semantics
- Optional & backward compatible: rules without an ID behave exactly as today;
  proof output stays byte-identical when no IDs are present.
- `ProofNode` gains `rule_id: Optional[str]`, set only on `rule` nodes.
- `check_kb` warns on duplicate rule IDs.

## Implementation (attribution: Prolog-native via body-marker)

| File | Change |
|---|---|
| models.py | `KB.rule_ids: dict[int, str]` (index-aligned to `rules`); `ProofNode.rule_id: Optional[str] = None` |
| language.py | capture `# rule: <id>` from the raw line (after `_extract_strings`, before lowercase); attach to the rule being built (incl. last multi-line body line); error if on fact/query; populate `KB.rule_ids` |
| translator.py | `_translate_rule`: prepend `euclid_rule_id('ID')` to the body when an ID exists. Meta-interpreter: decompose `(euclid_rule_id(Id), Rest)` → `rule(Goal, Rest, BodyProof, Id)` (or `null`). `proof_to_json`: emit `rule_id` only when `Id \= null` |
| sanitizer.py | reject `euclid_rule_id` in user input (reserved internal predicate, prevents ID spoofing); ID re-emitted as escaped Prolog string (`'` and `\` escaped) |
| server.py | `check_kb`: warning on duplicate IDs |
| prolog_bridge.py | `_parse_proof`: propagate `rule_id` from JSON |

## Security
- `# rule: '); halt.` cannot break out: ID is re-emitted as a quoted Prolog string
  with escaping.
- `euclid_rule_id/1` added to the sanitizer blocklist.

## Tests
- Parser: single-line, multi-line, case preserved, error on fact, standalone
  `# rule:` ignored, output unchanged without IDs.
- Security: escaping of hostile IDs; rejection of `euclid_rule_id` in input.
- check_kb: duplicate-ID warning.
- End-to-end: `reason()` proof tree carries `rule_id`.

## Docs
- docs/EUCLID_IR.md (syntax reference + example with `rule_id` in the proof),
  AGENTS.md, README.md (example output), CHANGELOG.md.

## Versioning
Backward-compatible language extension → minor bump **v0.2.0**
(current tagged: v0.1.5; accumulated main: v0.1.6).

## Out of scope
YAML rule IDs, IDs on facts, deterministic `explain_proof`, KB identity/hash.

## Cleanup
Delete this file after the feature is implemented and documented.
