# Euclid-MCP — Agent Guide

Euclid-MCP is a deterministic logical reasoning engine. Write facts and rules in **Euclid IR** (Intermediate Representation), the engine translates to Prolog, performs deduction, and returns solutions with **proof trees**.

Available tools: `euclid-mcp_reason`, `euclid-mcp_diagnose`, `euclid-mcp_what_if`, `euclid-mcp_check_kb`

## `reason` — Main deduction tool

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `knowledge` | `string` | — | Facts and rules in text or YAML format |
| `query` | `string?` | — | Separate query (optional, overrides the one in knowledge) |
| `max_solutions` | `int` | `5` | Max solutions to return |
| `max_depth` | `int` | `30` | Max proof tree depth |

## `diagnose` — Query analysis

Diagnose why a query succeeds or fails. Modes:
- `why` — explain why a query holds (or that it doesn't)
- `why_not` — explain why a query fails (missing facts/rules)
- `what_needs` — suggest what would make a false query true

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `knowledge` | `string` | — | Facts and rules in text or YAML format |
| `query` | `string` | — | Query to diagnose |
| `mode` | `string` | `why` | One of: `why`, `why_not`, `what_needs` |
| `max_solutions` | `int` | `5` | Max solutions to return |
| `max_depth` | `int` | `30` | Max proof tree depth |

## `what_if` — Scenario analysis

Apply modifications to a knowledge base and see how they affect query results. Use `+` prefix to add facts, `-` prefix to remove facts.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `base_knowledge` | `string` | — | Base facts and rules |
| `modifications` | `string` | — | Modifications: `+ fact(...)` to add, `- fact(...)` to remove |
| `query` | `string` | — | Query to evaluate |
| `max_solutions` | `int` | `5` | Max solutions to return |
| `max_depth` | `int` | `30` | Max proof tree depth |

## `check_kb` — Knowledge base validator

Check a knowledge base for consistency: syntax errors, undefined predicates, circular rules, duplicates.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `knowledge` | `string` | — | Facts and rules in text or YAML format |

## Euclid IR Syntax (text format)

```
# Comments with # or //
fact(arg1, arg2)
rule($x) IF premise($x)
? query($x)              # ? is required for the query

# AND for conjunctions:
rule($x) IF premise1($x) AND premise2($x)
```

### Rules
- **Variables**: prefix `$` + lowercase name (`$x`, `$who`, `$person`)
- **Implication**: `IF` (uppercase)
- **Conjunction**: `AND` (uppercase)
- **Query**: prefix `?` on a separate line
- **Predicates**: lowercase, with arguments in parentheses
- **Comments**: `#` or `//` at line start or inline
- **Trailing dot**: optional, ignored

## Alternative YAML format

```yaml
facts:
  - parent(tom, bob)
  - parent(bob, ann)
rules:
  - ancestor($x, $y) IF parent($x, $y)
  - ancestor($x, $y) IF parent($x, $z) AND ancestor($z, $y)
query: ancestor(tom, $who)
```

**Prefer the text format** — it is more concise and less error-prone.

## Usage examples

### 1. Simple fact
```
red(apple)
? red($x)
```

### 2. Rule with variable
```
human(socrates)
mortal($x) IF human($x)
? mortal($who)
```
→ `$who = socrates` (deduced from rule)

### 3. Rule chain (ancestry)
```
parent(tom, bob)
parent(bob, ann)
parent(tom, liz)
ancestor($x, $y) IF parent($x, $y)
ancestor($x, $y) IF parent($x, $z) AND ancestor($z, $y)
? ancestor(tom, $who)
```
→ `$who = bob`, `$who = ann`, `$who = liz`

### 4. Multiple rules for the same predicate
```
mortal($x) IF human($x)
mortal($x) IF robot($x)
human(socrates)
robot(t-800)
? mortal($who)
```
→ `$who = socrates`, `$who = t-800`

### 5. Boolean query (no variables)
```
grass_is_green
sky_is_blue
? grass_is_green
```
→ empty solution `{}` if true

### 6. Multiple variables
```
parent(tom, bob)
parent(bob, ann)
grandparent($x, $y) IF parent($x, $z) AND parent($z, $y)
? grandparent($x, $y)
```

### 7. Diagnose a failing query

Knowledge base:
```
human(socrates)
mortal($x) IF human($x)
```

Call `diagnose` with `query="mortal(plato)"` and `mode="why_not"`:

**Result:**
```json
{
  "holds": false,
  "findings": [
    "Fact 'mortal(plato)' not found in knowledge base",
    "No rule with head 'mortal(plato)' found"
  ],
  "conclusion": "Query fails: no derivation path for mortal(plato)"
}
```

### 8. What-if scenario

Knowledge base:
```
human(socrates)
mortal($x) IF human($x)
```

Call `what_if` with `modifications="+ human(plato)"` and `query="mortal($who)"`:

**Result:**
```json
{
  "before_count": 1,
  "after_count": 2,
  "delta": 1,
  "solutions_before": [{"substitutions": {"who": "socrates"}}],
  "solutions_after": [
    {"substitutions": {"who": "socrates"}},
    {"substitutions": {"who": "plato"}}
  ],
  "conclusion": "Adding 'human(plato)' adds 1 new solution"
}
```

### 9. Validate a knowledge base

Call `check_kb` with:
```
human(socrates)
mortal($x) IF unknown_predicate($x)
? mortal($who)
```

**Result:**
```json
{
  "valid": false,
  "errors": ["Undefined predicate: unknown_predicate/1"],
  "warnings": [],
  "facts_count": 1,
  "rules_count": 1,
  "predicates_count": 3
}
```

## Proof tree interpretation

Each solution contains `substitutions` (variable bindings) and `proof` (the proof tree):

- **`fact`**: goal proved directly from a fact — leaf node
- **`rule`**: goal proved by applying a rule — contains `goal`, `body` (premises), `subproof` (subtree)
- **`and`**: conjunction of two sub-goals — contains `left` and `right`

## Best practices

- Place the **query at the end** of the knowledge, prefixed by `?`
- Use the **query as the last line** in the `knowledge` parameter, or pass a separate `query`
- For variable-less (boolean) queries, `substitutions` will be `{}`
- If no query is provided, the tool returns an error
- Use `max_solutions` to limit results (default 5)
- Use `max_depth` to control recursion depth (default 30)

## Known limitations

- Predicate and fact names must be **lowercase**
- Variables in text must start with `$` + **lowercase letter** (`$x`, `$y`, `$who`)
- `$` variables are translated to Prolog with an uppercase first letter
- The engine is **case-sensitive**: `Mortal` ≠ `mortal`
- Does not support cut or Prolog side effects
- Supports only Horn-clause logic (no disjunctions)
