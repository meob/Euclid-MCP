# Euclid-MCP — Agent Guide

Deterministic logical reasoning engine. Write facts/rules in **Euclid IR**, engine translates to Prolog, returns solutions with **proof trees**.

Tools: `euclid-mcp_reason`, `euclid-mcp_explain`, `euclid-mcp_diagnose`, `euclid-mcp_what_if`, `euclid-mcp_check_kb`

## Workflow

```
1. check_kb    → validate before reasoning (catch syntax errors, undefined predicates)
2. reason      → run deduction, get solutions + proof trees
3. explain     → turn solutions into readable, auditable reasoning steps
4. diagnose    → if result unexpected: mode="why_not" to find missing facts/rules
5. what_if     → test modifications before applying them
```

Always call `check_kb` first on new or modified knowledge bases.

`knowledge`/`base_knowledge` are optional on all tools: when a KB is preloaded
(`EUCLID_KB_PATH` / `--kb-path`), an empty value falls back to it. Pass
`knowledge` explicitly only for session-specific facts or a different KB.

## Tools

### `reason`
Main deduction. Returns solutions with variable bindings and proof trees.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `knowledge` | `string?` | — | Facts & rules (falls back to preloaded KB) |
| `query` | `string?` | — | Override query (optional) |
| `max_solutions` | `int` | `5` | Max solutions |
| `max_depth` | `int` | `30` | Max proof tree depth |

### `explain`
Deterministic proof-tree → natural-language reasoning steps. Cites `rule_id`
when a rule has one.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `knowledge` | `string?` | — | Facts & rules (falls back to preloaded KB) |
| `query` | `string?` | — | Override query (optional) |
| `max_solutions` | `int` | `5` | Max solutions |
| `max_depth` | `int` | `30` | Max proof tree depth |

### `diagnose`
Why a query succeeds or fails.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `knowledge` | `string` | — | Facts & rules |
| `query` | `string` | — | Query to diagnose |
| `mode` | `string` | `why` | `why` / `why_not` / `what_needs` |
| `max_solutions` | `int` | `5` | Max solutions |
| `max_depth` | `int` | `30` | Max proof depth |

### `what_if`
Test modifications before applying. `+` prefix to add, `-` to remove.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `base_knowledge` | `string` | — | Base facts & rules |
| `modifications` | `string` | — | `+ fact(...)` or `- fact(...)` |
| `query` | `string` | — | Query to evaluate |
| `max_solutions` | `int` | `5` | Max solutions |
| `max_depth` | `int` | `30` | Max proof depth |

### `check_kb`
Validate knowledge base for errors before reasoning.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `knowledge` | `string` | — | Facts & rules |

## Euclid IR Syntax

```
# Facts
parent(tom, bob)
active(user_42)
rainy

# Rules
mortal($x) IF human($x)  # rule: BIO-001
ancestor($x, $y) IF parent($x, $z) AND ancestor($z, $y)

# Negation
blocked($user) IF NOT active($user)

# Arithmetic
stale($user) IF user($user) AND last_login($user, $days) AND $days > 90

# Query (? prefix required)
? mortal($who)
? can_access_resource($user, $res) AND resource($res, _, _, _, _, secret)
```

### Rules
- Variables: `$name` (lowercase after `$`)
- Implication: `IF` (case-insensitive)
- Conjunction: `AND` (case-insensitive)
- Negation: `NOT` (case-insensitive)
- Query prefix: `?` on a separate line
- Predicates: lowercase with args in `()`
- Wildcards: `_` (anonymous variable)
- Comments: `#` or `//`
- Rule IDs: trailing `# rule: <id>` → surfaced as `rule_id` in proofs, cited by `explain`
- Multi-line rules: continuation implied after `IF` or `AND`

### Supported operators
`>`, `>=`, `<`, `<=`, `==`, `is`, `!=`

### String literals
UTF-8 strings for real-world data (emails, URLs, addresses):
```
user(alice, "alice@example.com")
address(bob, 'Via Roma, 15')
```

## Proof Tree Nodes

- `fact` — goal proved from a fact (leaf)
- `rule` — goal proved by rule application (has `goal`, `body`, `subproof`)
- `and` — conjunction of two sub-goals (has `left`, `right`)

## Common Patterns

**Boolean check** (no variables): `? grass_is_green` → `{}` if true

**Multi-hop reasoning**: chain rules with `AND`
```
can_deploy($user, $env) IF
    user($user) AND
    has_role($user, $role) AND
    deploy_requires_level($env, $min) AND
    deploy_role_level($role, $level) AND
    $level >= $min
```

**Diagnostic flow**:
1. `reason` returns unexpected → `diagnose(mode="why_not")` → find missing facts
2. `diagnose(mode="what_needs")` → suggest what to add

## Development

Standard verification commands (run before committing changes):

```bash
ruff check .                       # lint
mypy euclid_mcp integrations       # type check
pytest --cov=euclid_mcp --cov=integrations   # tests + coverage (fail_under 80)
```

The CI workflow (`.github/workflows/ci.yml`) runs these on every push/PR.
Optional local hooks are provided via `.pre-commit-config.yaml`
(`pre-commit install`).

## Limitations

- Predicate/fact names: **lowercase only** (case-insensitive: `Human(ALICE)` → `human(alice)`)
- Variables: `$` + lowercase (`$x`, `$who`)
- No disjunction, cut, list syntax, findall/bagof, dynamic assert/retract, modules
- Horn-clause logic only
