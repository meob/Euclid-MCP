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
