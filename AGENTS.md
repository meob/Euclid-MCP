# Euclid-MCP — Agent Guide

Deterministic logical reasoning engine. Write facts/rules in **Euclid IR**, engine translates to Prolog, returns solutions with **proof trees**.

Tools: `euclid-mcp_reason`, `euclid-mcp_diagnose`, `euclid-mcp_what_if`, `euclid-mcp_check_kb`

## Workflow

```
1. check_kb    → validate before reasoning (catch syntax errors, undefined predicates)
2. reason      → run deduction, get solutions + proof trees
3. diagnose    → if result unexpected: mode="why_not" to find missing facts/rules
4. what_if     → test modifications before applying them
```

Always call `check_kb` first on new or modified knowledge bases.

## Tools

### `reason`
Main deduction. Returns solutions with variable bindings and proof trees.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `knowledge` | `string` | — | Facts & rules (text or YAML) |
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
mortal($x) IF human($x)
ancestor($x, $y) IF parent($x, $z) AND ancestor($z, $y)

# Negation
blocked($user) IF NOT active($user)

# Arithmetic
stale($user) IF user($user) AND last_login($user, $days) AND $days > 90

# Query (? prefix required)
? mortal($who)
? can_access($user, $res) AND resource($res, _, _, _, _, secret)
```

### Rules
- Variables: `$name` (lowercase after `$`)
- Implication: `IF` (uppercase)
- Conjunction: `AND` (uppercase)
- Negation: `NOT` (uppercase)
- Query prefix: `?` on a separate line
- Predicates: lowercase with args in `()`
- Wildcards: `_` (anonymous variable)
- Comments: `#` or `//`
- Multi-line rules: continuation implied after `IF` or `AND`

### Supported operators
`>`, `>=`, `<`, `=<`, `=:=`, `=\=`, `is`

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

## Limitations

- Predicate/fact names: **lowercase only**
- Variables: `$` + lowercase (`$x`, `$who`)
- Case-sensitive: `Mortal` ≠ `mortal`
- No disjunction, cut, list syntax, findall/bagof, dynamic assert/retract, modules
- Horn-clause logic only
