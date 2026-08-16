# Euclid-MCP Didactic Guide

Teach logical reasoning with **Euclid-IR**: you state what is *true* (facts and
rules), the engine proves what *follows* — and hands you a **proof tree** that
shows exactly why. No LLM, no magic: just unification, backtracking and
recursion, the same three ideas that power Prolog since the 1970s.

This guide is written for someone who has never seen logic programming. It uses
the interactive `euclid-cli` REPL as a laboratory, so you learn by typing.

---

## 1. The one-sentence idea

> **LLMs describe. Euclid-MCP proves.**

In classical programming you tell the machine *how* to compute an answer. In
logic programming you declare *what is true*, and the engine searches for
answers that follow from your declarations — and can always explain the path it
took.

That path is the **proof tree**: a nested structure where every conclusion is
backed by the facts and rules that produced it. Because the engine is
deterministic, the same knowledge base and query always give the same answers
with the same proofs — which is what makes the results auditable.

---

## 2. Euclid-IR is Prolog without the notation

The inference engine underneath is Prolog, but you never write Prolog. You write
**Euclid-IR**, and the translator compiles it to Prolog for you. The mapping is
deliberately 1:1, so every intuition you build with Euclid-IR transfers to
Prolog unchanged:

| Euclid-IR       | Prolog         | Meaning                                  |
|-----------------|----------------|------------------------------------------|
| `parent(tom, bob)` | `parent(tom, bob).` | Fact (a ground clause)              |
| `$x`            | `X`            | Variable                                 |
| `head IF body`  | `head :- body` | Rule: head is true when body holds       |
| `a AND b`       | `a, b`         | Conjunction (both must hold)             |
| `NOT a`         | `\+ a`         | Negation as failure (a must not hold)    |
| `? query`       | `?- query`     | Query (goal to prove)                    |
| `# comment`     | `% comment`    | Comment                                  |

The differences are **not** arbitrary — every one exists to make Euclid-IR
easier to read and understand than Prolog:

- **Uppercase keywords (`IF`, `AND`, `NOT`)** — they stand out visually and read
  like an English sentence: `mortal($x) IF human($x)`. In Prolog the same idea
  uses punctuation: `mortal(X) :- human(X).` Punctuation is easy to miss and
  easy to misread; words are not.
- **`$` variables** — in Prolog, *any* identifier starting with an uppercase
  letter is a variable (`X`, `Alice`). That rule is subtle and a common source
  of beginner bugs. Euclid-IR makes variables explicit with a `$` prefix:
  `$x`, `$who`, `$days`.
- **`AND` instead of `,`** — Prolog overloads the comma: it separates
  arguments *and* joins sub-goals. Euclid-IR reserves `,` for arguments only,
  and spells conjunctions with `AND`, removing the ambiguity.
- **`#` and `//` comments** — these are the comment markers of Markdown and most
  programming languages. A `.euclid` knowledge base can carry explanatory
  comments that render nicely in any Markdown viewer, doubling as
  documentation:

  ```
  # Who is allowed to deploy to production?
  can_deploy($user, prod) IF
      user($user) AND
      has_role($user, deployer)
  ```

  Keywords are **case-insensitive** (`if`, `If`, `IF`, `AND`, `not` all work),
  so you are free to pick the style you find clearest — the uppercase form is
  simply the recommended one because it reads like English.

- **Multi-line rules** — a rule body that ends in `IF` or `AND` continues on
  the next line. Long rules can be formatted like code:

  ```
  can_deploy($user, $env) IF
      user($user) AND
      has_role($user, $role) AND
      deploy_requires_level($env, $min) AND
      deploy_role_level($role, $level) AND
      $level >= $min
  ```

---

## 3. Core concepts

We use one running example — a family tree:

```
# Facts — things that are true, with no conditions
parent(tom, bob)
parent(bob, ann)
parent(tom, liz)

# Rule — something that is true *when* its body holds
ancestor($x, $y) IF parent($x, $y)
ancestor($x, $y) IF parent($x, $z) AND ancestor($z, $y)
```

Three building blocks:

1. **Facts** are statements with no conditions: `parent(tom, bob)`.
2. **Rules** are conditional statements (Horn clauses): a *head* that holds
   when its *body* holds. The first rule says: "$x` is an ancestor of `$y` if
   `$x` is a parent of `$y`." The second rule is **recursive**: a parent of a
   parent is an ancestor, so the rule can apply to itself.
3. **Queries** are goals to prove. Prefix with `?` on its own line:

   ```
   ? ancestor(tom, $who)
   ```

The engine answers with every `$who` such that the query can be proven, each
with a proof tree. The full language reference is in
[`docs/EUCLID_IR.md`](EUCLID_IR.md).

---

## 4. How deduction actually works

The engine is **goal-driven**: it starts from the query and works *backwards*
towards the facts. It does so with three operations:

### Unification

Two terms **unify** when they can be made identical by assigning variables. For
example, `ancestor(tom, $who)` unifies with the rule head `ancestor($x, $y)`
by binding `$x = tom` and `$y = $who`. Unification is the engine's only way to
"match" a goal against a fact or a rule head.

### Depth-first search with backtracking

To prove a goal, the engine tries the clauses for that predicate **in order**.
If a clause leads to a dead end, it *backtracks*: it undoes the bindings and
tries the next clause. This is exactly the `for` loop + `yield` generator you
can see in the native engine's `_prove_predicate` (section 5).

### Recursion

Rules may call themselves, which is how the engine reaches an unbounded number
of proof steps from a finite knowledge base. Recursion always needs a **base
case** (the first `ancestor` rule) to terminate — the same rule as in functional
programming.

### A worked trace: `ancestor(tom, ann)`

The engine processes goals left-to-right and clauses top-to-bottom:

```
Goal: ancestor(tom, ann)                 # "ann" fixed — prove tom is an ancestor of ann
  try rule 2: ancestor($x, $y) IF parent($x, $z) AND ancestor($z, $y)
  unify head -> $x = tom, $y = ann
  prove body, left to right:
    parent(tom, $z)   → matches parent(tom, bob) → $z = bob
    ancestor(bob, ann)  → try rule 1: ancestor($x, $y) IF parent($x, $y)
                          unify -> $x = bob, $y = ann
                          prove parent(bob, ann) → matches the fact  ✓
  ✓ both sub-goals proven
```

The engine never "knows" that `bob` is the connecting person — it *finds* him
by unification and backtracking. And because the proof is built step by step,
it can be returned to you as a tree:

```
ancestor(tom, ann)  [rule]
  [and]
    parent(tom, bob)  [fact]
    ancestor(bob, ann)  [rule]
      parent(bob, ann)  [fact]
```

---

## 5. The heart of the engine: the meta-interpreter

The whole engine is small enough to read. It is a **meta-interpreter**: a
program that interprets logic programs, and — as a side effect of the search —
builds the proof tree you receive.

### The Prolog version

SWI-Prolog is the primary backend. When you load a knowledge base, the
translator appends this tiny interpreter and runs your query through it
(`euclid_mcp/translator.py`):

```prolog
% prove(+Goal, +MaxDepth, -ProofTree)
prove(true, _, true) :- !.                        % (1) an empty body is trivially true
prove((A, B), D, and(PA, PB)) :- !,               % (2) a conjunction (A AND B):
    prove(A, D, PA),                             %       prove A, capture its proof,
    prove(B, D, PB).                             %       prove B, capture its proof
prove(\+ Goal, D, neg(Goal, negated)) :- !,       % (3) negation as failure:
    \+ prove(Goal, D, _).                        %       holds iff Goal cannot be proven
prove(Goal, _, fact(Goal)) :-                    % (4) a fact:
    clause(Goal, true).                          %       Goal is a clause with no body
prove(Goal, D, rule(Goal, Rest, BodyProof, Id)) :-% (5) a rule:
    D > 0, D1 is D - 1,                          %       depth limit (guards recursion)
    clause(Goal, Body), Body \= true,            %       find a clause with a body
    decompose_rule_id(Body, Rest, Id),           %       extract the # RULE: <id>, if any
    prove(Rest, D1, BodyProof).                  %       prove the body, capture its proof
```

Line by line: facts are clauses whose body is `true` (4); rules are anything
else (5). Each `prove` call returns the *proof* of what it proved, so the tree
is assembled as the recursion unwinds. The `MaxDepth` counter exists only to
stop runaway recursion.

### The native Python mirror

Where SWI-Prolog is unavailable, a pure-Python engine interprets Euclid-IR
directly with the same semantics (`euclid_mcp/ir_engine.py`). The search loop is
a Python generator — the `yield` freezes the search state, and resuming the
iteration continues the backtracking:

```python
def _prove(self, goal, depth, subst):
    goal_t = _deref(goal, subst)                      # resolve bound variables
    ...
    if f == "not":                                    # negation as failure
        if not self._has_solution(inner, depth, subst):
            yield subst, ProofNode(type="neg", goal=render(inner, subst))
        return
    if f in _COMPARISON_OPS:                          # arithmetic
        if self._compare(f, args, subst):
            yield subst, ProofNode(type="true")
        return
    yield from self._prove_predicate(goal_t, f, depth, subst)

def _prove_predicate(self, goal_t, pred, depth, subst):
    for clause in self.program.clauses_for(pred):     # try clauses in order
        head = _fresh(clause.head, mapping, self.counter)
        s = _unify(goal_t, head, subst)               # unification
        if s is None:
            continue                                  # no match -> next clause
        if not clause.body:
            yield s, ProofNode(type="fact", goal=render(goal_t, s))
            continue
        for s2, body_proof in self._prove_goals(body, depth - 1, s):
            yield s2, ProofNode(                      # rule node wraps sub-proof
                type="rule", goal=render(goal_t, s2),
                subproof=body_proof, rule_id=clause.rule_id)
```

Both backends produce the **same proof-tree structure**, so `explain`,
`diagnose` and `what_if` work unchanged no matter which engine is running. See
[`docs/NATIVE_ENGINE.md`](NATIVE_ENGINE.md) for the details and limits of the
native engine.

---

## 6. Proof trees are the payoff

Every answer comes with its reasoning. A proof tree has four node kinds:

| Node    | Meaning                                            |
|---------|----------------------------------------------------|
| `fact`  | the goal was proven directly by a fact (leaf)      |
| `rule`  | the goal was proven by applying a rule (carries its `rule_id` when present) |
| `and`   | two sub-goals, both proven (`left` and `right`)    |
| `neg`   | the goal holds because the negated goal fails      |

The CLI renders them as an indented tree (section 7). The `explain` tool walks
the same tree and renders it as natural-language sentences:

```
Explanation 1:
  who: plato
  - mortal(plato) is derived by rule BIO-001 from: human(plato).
  - human(plato) is asserted as a fact in the knowledge base.
```

And because rules can carry an audit id (`# RULE: BIO-001`), a proof can be
*cited*: "this conclusion derives from rule BIO-001". That is the difference
between an answer and a justification.

---

## 7. The `euclid-cli` REPL as a laboratory

The best way to learn is to type. `euclid-cli` with **no subcommand** opens an
interactive Euclid-IR REPL, the equivalent of Prolog's `swipl` prompt:

```bash
$ euclid-cli
Euclid-MCP REPL — type facts and rules in Euclid-IR, then `? query`.
Commands: :help  :check  :kb  :load  :explain  :diagnose  :what-if  :reset  :quit

euclid > parent(tom, bob)
euclid > parent(bob, ann)
euclid > ancestor($x, $y) IF parent($x, $y)
euclid > ancestor($x, $y) IF parent($x, $z) AND ancestor($z, $y)
euclid > ? ancestor(tom, $who)
Query: ancestor(tom, $who)
Solution 1:
  who: bob
ancestor(tom,bob)  [rule]
  parent(tom,bob)  [fact]

Solution 2:
  who: ann
ancestor(tom,ann)  [rule]
  [and]
    parent(tom,bob)  [fact]
    ancestor(bob,ann)  [rule]
      parent(bob,ann)  [fact]
```

### How the session behaves

- **The session knowledge base accumulates.** Every fact and rule you type is
  added to the session and stays available for later queries. `:kb` prints the
  current session; `:reset` clears it.
- **Multi-line rules.** A line ending in `IF` or `AND` continues on the next
  line — the prompt becomes `... >`. A blank line finishes the statement.
- **Queries.** Any line starting with `?` runs a deduction (`? query`).
- **Backend.** Add `--backend native` to force the pure-Python engine, or
  `--backend prolog` to force SWI-Prolog (`auto` picks either, default).

### Meta-commands

| Command | What it does |
|---------|--------------|
| `:check` | validate the session KB (catches typos and undefined predicates) |
| `:kb` | print the accumulated session KB |
| `:load <file>` | append a `.euclid` file to the session |
| `:explain [query]` | natural-language explanation of a proof (uses the last query if omitted) |
| `:diagnose <query> [why\|why_not\|what_needs]` | explain why a query holds or fails |
| `:what-if <mods>` | test changes, e.g. `+ human(plato)` or `- parent(tom, bob)` |
| `:reset` | clear the session KB |
| `:quit` | exit |

For example, a complete teaching exchange:

```
euclid > human(socrates)
euclid > human(plato)
euclid > mortal($x) IF human($x)  # RULE: BIO-001
euclid > ? mortal($who)
Query: mortal($who)
Solution 1:
  who: plato
mortal(plato)  [rule (BIO-001)]
  human(plato)  [fact]

Solution 2:
  who: socrates
mortal(socrates)  [rule (BIO-001)]
  human(socrates)  [fact]

euclid > :explain
Explanation 1:
  who: plato
  - mortal(plato) is derived by rule BIO-001 from: human(plato).
  - human(plato) is asserted as a fact in the knowledge base.
...
euclid > :diagnose mortal(aristotle) why_not
Query: mortal(aristotle)
Mode:  why_not
Query does NOT hold.
Conclusion: The query fails. Check rule conditions.
  [satisfied] human — Facts exist for 'human' (2 facts)

euclid > :what-if + human(aristotle)
Query: mortal($who)
Modifications: + human(aristotle)
Solutions: 2 -> 3 (delta: more)
Conclusion: Solutions increased: 2 -> 3.
```

### Batch mode

Feed the same loop through stdin (no prompts) to run a script:

```bash
printf 'human(socrates)\nmortal($x) IF human($x)\n? mortal($who)\n' | euclid-cli
```

The five tools are also available as one-shot subcommands
(`euclid-cli reason|explain|diagnose|what-if|check`) with `--json` for
machine-readable output — full reference in [`docs/CLI.md`](CLI.md).

---

## 8. Progressive exercises

Try each one in the REPL. Notice *what* the engine prints, not just the answer.

**Level 1 — a fact and a boolean query.** A query with no variables is true or
false.

```
rainy
? rainy
```
Output: `Solution 1: rainy [fact]` — one solution with **no variable bindings**
(`{}` in the API/JSON view), proven directly by the fact. Try `? sunny` →
`No solutions.`

**Level 2 — one rule.** Deduction from a single implication.

```
human(socrates)
mortal($x) IF human($x)
? mortal($who)
```
`who: socrates`, proven `[rule]` over the fact `human(socrates) [fact]`.

**Level 3 — conjunction.** Two conditions must both hold.

```
parent(tom, bob)
parent(bob, ann)
grandparent($x, $y) IF parent($x, $z) AND parent($z, $y)
? grandparent(tom, $who)
```
`who: ann`. Look at the proof: an `[and]` node whose `left` and `right` are two
`parent` facts. The engine found `bob` (the middle `$z`) for you.

**Level 4 — recursion.** The rule calls itself; the base case stops it.

```
parent(tom, bob)
parent(bob, ann)
ancestor($x, $y) IF parent($x, $y)
ancestor($x, $y) IF parent($x, $z) AND ancestor($z, $y)
? ancestor(tom, $who)
```
Two solutions: `bob` (base case) and `ann` (recursive case — the nested
`ancestor` proof inside the `[and]` node). This is Prolog's classic transitive
closure.

**Level 5 — negation as failure.** Something holds because its opposite does
*not* hold.

```
active(alice)
blocked($user) IF NOT active($user)
? blocked(bob)
? blocked(alice)
```
`blocked(bob)` holds (there is no `active(bob)` fact); `blocked(alice)` fails.
Watch the `[neg]` node in the proof.

**Level 6 — arithmetic.** Numbers in rules.

```
user(alice)
last_login(alice, 120)
stale($user) IF user($user) AND last_login($user, $days) AND $days > 90
? stale($who)
```
`who: alice`. Change `120` to `30` → `No solutions.` Operators:
`> >= < <= == != is`.

**Level 7 — what-if.** Predict, then check: what if we add a fact?

```
human(socrates)
mortal($x) IF human($x)
? mortal($who)
:what-if + human(aristotle)
```
`Solutions: 1 -> 2`. Remove a fact with `-`.

**Level 8 — diagnose.** When a query fails, ask *why not*.

```
human(socrates)
mortal($x) IF human($x)
:diagnose mortal(aristotle) why_not
```
The finding shows `human` has facts but none for `aristotle` — the missing
piece is the fact, not a broken rule. `:diagnose ... what_needs` even suggests
what to add.

---

## 9. Where to go next

- [`docs/EUCLID_IR.md`](EUCLID_IR.md) — the full Euclid-IR language reference
  (syntax, operators, strings, versions).
- [`docs/CLI.md`](CLI.md) — every `euclid-cli` flag, subcommand and output mode.
- [`docs/NATIVE_ENGINE.md`](NATIVE_ENGINE.md) — how the pure-Python fallback
  engine works and its limits.
- [`docs/EXAMPLES.md`](EXAMPLES.md) — real knowledge bases (genealogy, RBAC,
  loan eligibility, IT security compliance, Cluedo).
- [`README.md`](../README.md) — architecture, MCP/HTTP/Python usage, and the
  "What is Prolog?" background.
