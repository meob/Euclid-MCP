# Euclid-MCP CLI

`euclid-cli` is a thin, human-friendly command-line wrapper around the same
five reasoning tools exposed by the MCP server (`check_kb`, `reason`,
`explain`, `diagnose`, `what_if`). It is installed as a console script when
you install Euclid-MCP:

```bash
pip install euclid-mcp
euclid-cli --help
```

## Overview

```
euclid-cli [--backend auto|prolog|native] <subcommand> [options]
```

Subcommands:

| Subcommand | MCP tool     | Purpose                                |
|------------|--------------|----------------------------------------|
| `check`    | `check_kb`   | Validate a knowledge base              |
| `reason`   | `reason`     | Run a deduction                        |
| `explain`  | `explain`    | Explain solutions in natural language  |
| `diagnose` | `diagnose`   | Diagnose why a query holds or fails    |
| `what-if`  | `what_if`    | Evaluate knowledge modifications       |

The knowledge base comes from one of three sources, in order of precedence:

1. `--knowledge "KB TEXT"` — inline facts and rules
2. `-f kb.euclid` — a `.euclid` file
3. `EUCLID_KB_PATH` (or the server preload) — as a fallback

The query comes from `--query`, or from the `?` lines embedded in the KB
(any tool except `check`).

## Check output

`euclid-cli check` prints the KB statistics followed by the **predicate
inventory** — one line per predicate with its arities and fact/rule counts,
the derived contract for LLM extraction:

```
KB valid: True
Facts: 3  Rules: 1  Predicates: 3
  - allowed/1: 0 facts, 1 rules
  - can_access/1: 2 facts, 0 rules
  - user/1: 1 facts, 0 rules
```

A predicate used with multiple arities (e.g. `can_access(a)` and
`can_access(a, b)`) is flagged with an `inconsistent_arity` warning.

## Examples

```bash
# Validate a knowledge base
euclid-cli check -f policies.euclid

# Deduce using the ? line embedded in the file
euclid-cli reason -f policies.euclid

# Explicit query with limits
euclid-cli reason -f policies.euclid \
    --query "can_deploy($user, prod)" --max-solutions 10 --max-depth 40

# Inline knowledge, no file needed
euclid-cli reason --knowledge "human(socrates)
mortal(\$x) IF human(\$x)
? mortal(\$who)"

# Natural-language explanation (cites rule IDs when present)
euclid-cli explain -f policies.euclid

# Why does a query fail?
euclid-cli diagnose -f policies.euclid \
    --query "can_deploy(bob, prod)" --mode why_not

# What-if: add a fact and see how the answer changes
euclid-cli what-if -f policies.euclid \
    --modifications "+ has_role(bob, deployer)" --query "can_deploy(bob, prod)"

# Machine-readable output for scripting
euclid-cli reason -f policies.euclid --json
```

## Interactive REPL

Run `euclid-cli` with **no subcommand** to open an interactive Euclid-IR
REPL. You type facts, rules and `? query` lines directly — like `swipl` or
`psql` — and the session knowledge base accumulates across queries:

```
$ euclid-cli
Euclid-MCP REPL — type facts and rules in Euclid-IR, then `? query`.
Commands: :help  :check  :kb  :load  :explain  :diagnose  :what-if  :reset  :quit

euclid > human(socrates)
euclid > mortal($x) IF human($x)
euclid > ? mortal($who)
Query: mortal($who)
Solution 1:
  who: socrates
mortal(socrates)  [rule]
  human(socrates)  [fact]

euclid > :quit
```

- **Session KB** — facts and rules persist across `? query` lines. `:reset`
  clears it; `:kb` prints it. Seed it at startup with `-f kb.euclid` or
  `--knowledge "..."` (otherwise `EUCLID_KB_PATH`/preload is the fallback
  while the session is empty).
- **Multi-line rules** — a rule that ends in `IF` or `AND` continues on the
  next line (the prompt becomes `... >`). A blank line finishes the pending
  statement.
- **Meta-commands** — `:help`, `:check`, `:kb`, `:load <file>`,
  `:explain [query]`, `:diagnose <query> [why|why_not|what_needs]`
  (or `--mode <mode>`), `:what-if <mods>` (e.g. `+ human(plato)`), `:reset`,
  `:quit`.
- **Piped input** — feeding the script through stdin runs the same loop
  without prompts, so it doubles as a batch runner:

  ```bash
  printf 'human(socrates)\nmortal($x) IF human($x)\n? mortal($who)\n' | euclid-cli
  ```


## Backend selection

`--backend` selects the inference engine (it sets `EUCLID_BACKEND` for the
call), matching `docs/NATIVE_ENGINE.md`:

| Value    | Behavior                                                       |
|----------|----------------------------------------------------------------|
| `auto`   | SWI-Prolog if `swipl` is on `PATH`, otherwise the native engine (default) |
| `prolog` | Always the persistent SWI-Prolog engine                        |
| `native` | Always the native engine                                       |

```bash
euclid-cli --backend native reason -f policies.euclid
```

## Exit codes

| Code | Meaning                                                 |
|------|---------------------------------------------------------|
| `0`  | Success                                                 |
| `1`  | The tool reported an error (incl. an invalid KB via `check`) |
| `2`  | Usage error (unknown arguments, missing file, missing `--query`) |

## JSON output

`--json` prints the result as a JSON object instead of the human-readable
rendering: `query`, the solutions/explanations/findings with their full proof
trees, and `elapsed_ms`. Combined with the exit codes it is suitable for shell
pipelines and CI checks.
