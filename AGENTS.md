# Euclid-MCP — Agent Guide

Euclid-MCP is a deterministic logical reasoning engine. Write facts and rules in **Euclid IR** (Intermediate Representation), the engine translates to Prolog, performs deduction, and returns solutions with **proof trees**.

Available tool: `euclid-mcp_reason`

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `knowledge` | `string` | — | Facts and rules in text or YAML format |
| `query` | `string?` | — | Separate query (optional, overrides the one in knowledge) |
| `max_solutions` | `int` | `5` | Max solutions to return |
| `max_depth` | `int` | `30` | Max proof tree depth |

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
- Does not support negation, cut, or Prolog side effects
- Supports only Horn-clause logic (no disjunctions)
