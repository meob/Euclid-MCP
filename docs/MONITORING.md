# Monitoring Euclid-MCP

Two lightweight ways to observe the MCP server without touching any code:

1. **MCP Inspector** (interactive browser UI): spawn the server, call the tools by
   hand, watch the raw JSON-RPC traffic and per-call timing.
2. **Structured logs**: every tool call already emits a
   `tool=... elapsed_ms=... solutions=...` line (or `error=...` on failure).

Both are read-only observers — the server needs no code changes.

## What you can observe

The server exposes eight tools: `check_kb`, `diagnose`, `explain`, `reason`,
`what_if`, `register_kb`, `unregister_kb`, `list_kbs`.
Each call is wrapped by `_log_call` (euclid_mcp/server.py) which logs the tool
name, elapsed time and outcome:

```
INFO  tool=reason  elapsed_ms=12.3  solutions=5
WARN  tool=diagnose elapsed_ms=400.1 error=Unknown predicate: foo
```

## Prerequisites

- Node.js >= 22.19 (`node --version`)
- Project venv with euclid-mcp installed
- Optional: `EUCLID_LOG_LEVEL` (DEBUG/INFO/WARNING/ERROR/CRITICAL) to tune log
  verbosity

---

## Mode A — MCP Inspector (interactive UI)

### Inspector version

The server uses the `mcp` SDK **2.x** (`mcp>=2.0` in pyproject.toml) and speaks
the **modern protocol** (2026-07-28 era), so the latest MCP Inspector (`>= 2.0`)
works out of the box — no version pin needed.

```bash
npx -y @modelcontextprotocol/inspector .venv/bin/python -m euclid_mcp
```

The Inspector starts `python -m euclid_mcp` as a child process and prints:

```
🔗 Open inspector with token pre-filled:
   http://localhost:6274/?MCP_PROXY_AUTH_TOKEN=<token>
```

and opens your browser automatically.

### Connect

- Use the **full printed URL** (with `MCP_PROXY_AUTH_TOKEN`). The token is
  one-time and changes on every Inspector restart.
- Open it in a **fresh browser tab**. Reusing an old tab or a URL without the
  token makes the connection fail with no visible error in the browser.

### Where to paste text and call a tool

1. Left sidebar → **Tools** section lists the eight tools.
2. Click a tool, e.g. `reason`: a **form-based panel** opens with one input
   field per parameter (generated from the tool's JSON schema).
   - `reason`: `knowledge` (optional when a KB is preloaded), `kb_id`, `delta_knowledge`, `query`, `max_solutions`, `max_depth`
   - `explain`: `knowledge`, `kb_id`, `delta_knowledge`, `query`, `max_solutions`, `max_depth`
   - `diagnose`: `knowledge`, `kb_id`, `delta_knowledge`, `query`, `mode` (`why` / `why_not` / `what_needs`), ...
   - `what_if`: `base_knowledge`, `kb_id`, `delta_knowledge`, `modifications` (`+ fact(...)` / `- fact(...)`), `query`, ...
   - `check_kb`: `knowledge`, `kb_id`, `delta_knowledge`
   - `register_kb`: `kb_id`, `knowledge`
   - `unregister_kb`: `kb_id`
   - `list_kbs`: (no parameters)
3. **Paste the knowledge base** into the `knowledge` (or `base_knowledge`)
   field, the query into `query`, then click **Call tool**.
4. The structured result appears below with the timing; the **request history /
   notifications** panel shows the raw JSON-RPC request/response pairs.

Minimal copy-paste KB to try in `reason`:

```
human(socrates)
mortal($x) IF human($x)
? mortal($who)
```

Then leave `query` empty (the `?` line is used) or set `query` to
`? mortal($who)`.

### CLI mode (no browser)

The same client, scriptable. Useful for quick checks and automation.

```bash
# List the server's tools
npx -y @modelcontextprotocol/inspector --cli .venv/bin/python -m euclid_mcp \
  --method tools/list

# Call reason (single-quote args to keep $ and line breaks intact)
npx -y @modelcontextprotocol/inspector --cli .venv/bin/python -m euclid_mcp \
  --method tools/call --tool-name reason \
  --tool-arg 'knowledge=human(socrates)
mortal($x) IF human($x)
? mortal($who)'

# Enable the server's structured logs in the spawned child
npx -y @modelcontextprotocol/inspector --cli \
  -e EUCLID_LOG_LEVEL=INFO \
  .venv/bin/python -m euclid_mcp --method tools/list
```

---

## Mode B — Structured logs (long-running, no UI)

```bash
EUCLID_LOG_LEVEL=INFO .venv/bin/python -m euclid_mcp
```

While an MCP client (opencode, Claude Desktop, ...) drives it, the server's
stderr carries one line per tool call (see the format above). Aggregate them:

```bash
# Calls per tool
rg "tool=" | rg -o "tool=\w+" | sort | uniq -c

# Slowest calls
rg "tool=" | sort -t= -k3 -rn | head

# Errors
rg "error="
```

For a plain-text log file, wrap the server:

```bash
EUCLID_LOG_LEVEL=INFO .venv/bin/python -m euclid_mcp 2>> mcp.log
```

> Note: the example-10 demo (`examples/10_llm_vs_euclid/demo.py`) calls the
> engine **in-process** via `euclid_mcp.server` — it does not go through the MCP
> protocol, so the Inspector cannot see it, and the demo never configures the
> logger, so `EUCLID_LOG_LEVEL` has no effect there. Its monitoring channel is
> the demo's own output with `--verbose` (proof trees + tool responses).

---

## HTTP API access log

`integrations/euclid_api.py` logs every request with a correlation id:

```
INFO request_id=<id> "POST /reason HTTP/1.1" 200 -
```

Send your own `X-Request-Id` header; it is echoed on the response and included
in the log line, so you can correlate client calls with server logs.

---

## Versioning and coordinating across projects

### The constraint

The incompatibility is between the **protocol era** of the server SDK and the
Inspector:

| Server SDK        | Protocol era            | Inspector         |
| ----------------- | ----------------------- | ----------------- |
| `mcp` 1.x         | legacy (max `2025-11-25`) | `0.22.0` (pin) |
| `mcp` 2.x (this project) | modern (`2026-07-28`)   | `>= 2.0`         |

This project is on `mcp` 2.x, so the latest Inspector works without a pin.

### Coordinating with your other MCP servers

If a different project still uses `mcp` 1.x, pin its Inspector command:
`npx -y @modelcontextprotocol/inspector@0.22.0`. Servers on SDK 2.x use the
latest Inspector; ones still on 1.x keep `0.22.0` — they do not interfere
(the Inspector is a client tool, not shared state).
