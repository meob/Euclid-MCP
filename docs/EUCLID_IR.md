# Euclid-IR Language Reference

**Version 1.0**

Euclid-IR (Intermediate Representation) is a declarative language for logical inference. It provides a clean, human-readable syntax for expressing facts, rules, and queries — without requiring knowledge of Prolog.

Euclid-MCP translates Euclid-IR into Prolog, executes the deduction, and returns structured results with proof trees.

## Design Principles

1. **Readability** — Syntax optimized for both humans and LLMs
2. **Minimalism** — Only the essential constructs of Horn-clause logic
3. **Determinism** — Every query has a finite, traceable proof
4. **Backend-agnostic** — Euclid-IR is an intermediate layer; today it targets Prolog, tomorrow it could target other engines

## Quick Start

```
# Facts
parent(tom, bob)
parent(bob, ann)

# Rules
ancestor($x, $y) IF parent($x, $y)
ancestor($x, $y) IF parent($x, $z) AND ancestor($z, $y)

# Query
? ancestor(tom, $who)
```

Output: `$who = bob`, `$who = ann` (with full proof trees).

---

## Version Directive

The first line of a knowledge base can declare a version:

```
@version 1.0

parent(tom, bob)
? parent($x, $y)
```

- **Optional** — if omitted, version `1.0` is assumed
- **Retrocompatible** — future versions will maintain backward compatibility
- **Parsed as a directive** — not treated as a fact or comment

---

## Lexical Rules

| Rule | Detail |
|------|--------|
| **Case sensitivity** | Keywords are uppercase (`IF`, `AND`, `NOT`). Predicate and atom names are lowercase. |
| **Variables** | Start with `$` followed by a lowercase letter: `$x`, `$who`, `$user_name` |
| **Atoms** | Lowercase identifiers: `tom`, `admin_role`, `us_east_1` |
| **Integers** | Digits only: `42`, `0`, `999` |
| **Comments** | `#` or `//` at line start or inline |
| **Trailing dots** | Optional, ignored (for Prolog familiarity) |
| **Whitespace** | Newlines separate statements; spaces separate tokens |

---

## Syntax Reference

### Facts

Ground assertions about the world.

```
parent(tom, bob)
color(apple, red)
active(user_42)
rainy
```

**Rules:**
- Predicate name: lowercase, no spaces
- Arguments: comma-separated (atoms, integers, or variables)
- No arguments → zero-arity fact: `rainy`
- Zero-arity facts can also be written as bare atoms: `rainy` (equivalent to `rainy.`)

### Variables

Variables represent unknown or generic values. They start with `$`:

```
$person
$x
$resource_name
$level
```

**Naming rules:**
- Must start with `$` + lowercase letter
- Can contain letters, digits, underscores
- Case-sensitive: `$x` ≠ `$X` (only `$x` is valid)
- Convention: use descriptive names for LLM readability (`$user`, `$count`)

**Translation to Prolog:** `$varname` → `Varname` (capitalized)

### Rules (Implication)

Rules define logical relationships. The head is implied by the body.

```
mortal($x) IF human($x)
```

**Syntax:** `<head> IF <body>`

- `IF` is uppercase and separates head from body
- Head: a predicate (possibly with variables)
- Body: one or more conditions connected by `AND`

**Multiple conditions:**

```
grandparent($x, $y) IF parent($x, $z) AND parent($z, $y)
```

### Conjunction (AND)

Connects multiple conditions in a rule body or query:

```
rule($x) IF condition1($x) AND condition2($x) AND condition3($x)
```

**In queries:**

```
? can_access($who, $res) AND resource($res, _, _, _, _, secret)
```

Both conditions must be satisfied simultaneously.

### Negation (NOT)

Closed-world negation — "it is not the case that":

```
blocked($user) IF NOT active($user)
eligible($user) IF registered($user) AND NOT blocked($user)
```

**Semantics:** `NOT predicate` succeeds when `predicate` cannot be proven (Prolog's `\+`).

**Warning:** Negation as failure is not logical negation. `NOT mortal(socrates)` succeeds if `mortal(socrates)` cannot be derived — not if it is "false."

### Query

The `?` prefix marks a query — what you want to prove:

```
? mortal(socrates)
? ancestor(tom, $who)
? can_access($user, $resource) AND resource($resource, _, _, _, _, secret)
```

**Rules:**
- One query per knowledge base (or override via `query` parameter)
- Can include variables (to find bindings) or be ground (boolean check)
- Can use `AND` for conjunctions
- Ground queries return empty substitution `{}` if true

### Arithmetic Comparisons

Compare numeric values in rule bodies:

```
stale($user) IF last_login($user, $days) AND $days > 90
adult($person) IF age($person, $age) AND $age >= 18
```

**Supported operators:**

| Operator | Meaning | Example |
|----------|---------|---------|
| `>` | Greater than | `$x > 0` |
| `>=` | Greater or equal | `$x >= 18` |
| `<` | Less than | `$x < 100` |
| `=<` | Less or equal (Prolog style) | `$x =< 50` |
| `=:=` | Arithmetic equal | `$x =:= 42` |
| `=\=` | Arithmetic not equal | `$x =\= 0` |
| `is` | Assignment/evaluation | `$x is $y + 1` |

**Note:** These are Prolog arithmetic operators, passed through verbatim. They are evaluated at deduction time.

### Multi-line Rules

Rules can span multiple lines for readability:

```
can_deploy($user, $env) IF
    user($user) AND
    has_role($user, $role) AND
    deploy_requires_level($env, $min) AND
    deploy_role_level($role, $level) AND
    $level >= $min AND
    user_has_permission($user, deploy_code)
```

**Parsing rules:**
- If a line ends with `IF` or `AND`, the parser continues to the next line
- All parts are joined into a single rule statement
- Indentation is ignored (cosmetic only)

### Wildcard Arguments

Use `_` for arguments you want to ignore:

```
# "What is the color of apple?" — ignore category and season
resource(apple, $color, _, _, _, _)
```

Wildcards are translated to Prolog anonymous variables (`_`).

### Comments

Two styles, both supported:

```
# This is a comment
// This is also a comment

parent(tom, bob)  # inline comment
active(user_42)   // inline comment
```

Comments are stripped during parsing.

### YAML Format

Euclid-IR also supports YAML input:

```yaml
facts:
  - parent(tom, bob)
  - parent(bob, ann)
rules:
  - ancestor($x, $y) IF parent($x, $y)
  - ancestor($x, $y) IF parent($x, $z) AND ancestor($z, $y)
query: ancestor(tom, $who)
```

**Recommendation:** Use the text format — it is more concise and less error-prone.

---

## Examples

### 1. Simple fact query

```
red(apple)
blue(sky)
? red($x)
```

**Result:** `$x = apple`

### 2. Rule with variable

```
human(socrates)
mortal($x) IF human($x)
? mortal($who)
```

**Result:** `$who = socrates` (deduced from rule)

### 3. Recursive rules (ancestry)

```
parent(tom, bob)
parent(bob, ann)
parent(tom, liz)

ancestor($x, $y) IF parent($x, $y)
ancestor($x, $y) IF parent($x, $z) AND ancestor($z, $y)

? ancestor(tom, $who)
```

**Result:** `$who = bob`, `$who = ann`, `$who = liz`

### 4. Negation

```
active(alice)
active(bob)
blocked(charlie)

eligible($user) IF active($user) AND NOT blocked($user)
? eligible($who)
```

**Result:** `$who = alice`, `$who = bob`

### 5. Arithmetic

```
user(alice)
user(bob)
user(charlie)
last_login(alice, 5)
last_login(bob, 45)
last_login(charlie, 120)

stale($user) IF user($user) AND last_login($user, $days) AND $days > 90
? stale($who)
```

**Result:** `$who = charlie`

### 6. Multi-line rule with conjunction query

```
user(alice)
role(alice, admin)
role_level(admin, 5)
env_requires_level(prod, 3)
permission(alice, deploy_code)

can_deploy($user, $env) IF
    user($user) AND
    role($user, $role) AND
    role_level($role, $level) AND
    env_requires_level($env, $min) AND
    $level >= $min AND
    permission($user, deploy_code)

? can_deploy(alice, prod)
```

**Result:** `{}` (empty substitution = true)

### 7. Boolean query (no variables)

```
grass_is_green
sky_is_blue
? grass_is_green
```

**Result:** `{}` if true (no variable bindings)

---

## Comparison with Prolog

| Euclid-IR | Prolog equivalent |
|-----------|-------------------|
| `parent(tom, bob).` | `parent(tom, bob).` |
| `$x` | `X` (capitalized) |
| `mortal($x) IF human($x)` | `mortal(X) :- human(X).` |
| `a($x) AND b($x)` | `a(X), b(X)` |
| `NOT active($x)` | `\+ active(X)` |
| `? ancestor(tom, $who)` | `?- ancestor(tom, Who).` |
| `$days > 90` | `Days > 90` |

**Key differences:**
- `$` prefix for variables (vs. uppercase first letter in Prolog)
- `IF` instead of `:-`
- `AND` instead of `,`
- `NOT` instead of `\+`
- `?` prefix for queries
- No cut (`!`), no disjunction (`;`), no list syntax

---

## Known Limitations

Euclid-IR targets **Horn-clause logic** — the core of Prolog without advanced features:

| Feature | Status | Notes |
|---------|--------|-------|
| Horn clauses | ✅ Supported | Facts + rules with conjunction |
| Negation (NOT) | ✅ Supported | Closed-world assumption |
| Arithmetic | ✅ Supported | Via Prolog pass-through |
| Multi-line rules | ✅ Supported | Body spans multiple lines |
| Conjunction queries | ✅ Supported | `AND` in query |
| Disjunction (OR) | ❌ Not supported | Use multiple rules instead |
| Cut (!) | ❌ Not supported | No backtracking control |
| Lists `[H\|T]` | ❌ Not supported | No pattern matching on lists |
| findall/bagof | ❌ Not supported | No collection of solutions |
| Assert/retract | ❌ Not supported | No dynamic facts at runtime |
| Modules | ❌ Not supported | Single knowledge base |
| Strings | ❌ Not supported | Atoms only (lowercase identifiers) |

**Workarounds:**

- **OR:** Define separate rules:
  ```
  # Instead of: mortal($x) IF human($x) OR god($x)
  mortal($x) IF human($x)
  mortal($x) IF god($x)
  ```

- **Lists:** Represent as facts:
  ```
  item(list_1, apple)
  item(list_1, banana)
  item(list_2, carrot)
  ```

---

## Best Practices for LLMs

When writing Euclid-IR knowledge for LLM consumption:

1. **One concept per predicate** — Don't overload predicates with multiple meanings
2. **Descriptive variable names** — `$user` instead of `$u`; `$resource_name` instead of `$r`
3. **Separate data from rules** — Load facts from external sources, keep rules in `.euclid` files
4. **Use comments** — Document the intent of complex rules
5. **Place query at the end** — The `?` line should be the last statement
6. **Limit rule depth** — Keep `max_depth` reasonable (default 30) to prevent infinite loops
7. **Test incrementally** — Start with simple facts, add rules one by one

### Example: LLM-friendly format

```
# User directory
user(alice)
user(bob)
user(charlie)

# Role assignments
has_role(alice, admin)
has_role(bob, developer)
has_role(charlie, viewer)

# Role hierarchy
role_level(admin, 5)
role_level(developer, 3)
role_level(viewer, 1)

# Access policy: admin can do everything
can_access($user, $resource) IF
    user($user) AND
    has_role($user, $role) AND
    role_level($role, $level) AND
    $level >= 4

# Query: who can access anything?
? can_access($who, $resource)
```

---

## File Extension

Euclid-IR files use the `.euclid` extension:

```
my_policies.euclid
```

This is a convention, not enforced. The parser accepts any text input.

---

## Error Handling

Common parsing errors and fixes:

| Error | Cause | Fix |
|-------|-------|-----|
| "No query found" | Missing `?` line | Add `? predicate(...)` at the end |
| "Invalid variable" | `$X` or `$123` | Use `$x` or `$name` (lowercase after `$`) |
| "Unterminated rule" | Missing body after `IF` | Add at least one condition |
| "Unknown keyword" | `IF`/`AND`/`NOT` in wrong case | Use uppercase: `IF`, `AND`, `NOT` |

---

## Glossary

| Term | Definition |
|------|------------|
| **Atom** | A lowercase identifier representing a constant: `tom`, `admin_role` |
| **Variable** | A `$`-prefixed identifier representing an unknown: `$x`, `$who` |
| **Fact** | A ground assertion: `parent(tom, bob)` |
| **Rule** | A logical implication: `mortal($x) IF human($x)` |
| **Query** | A goal to prove: `? mortal($who)` |
| **Proof tree** | The logical derivation path for a solution |
| **Substitution** | Variable bindings that make the query true |
| **Knowledge base** | The complete set of facts, rules, and query |
| **Backtracking** | Prolog's search mechanism for finding all solutions |
| **Closed-world assumption** | What cannot be proven is assumed false (basis of NOT) |
