# Euclid-MCP Integrations

Tools to integrate Euclid-MCP into automation platforms and agent frameworks.

## HTTP API (n8n / Zapier / Make)

```bash
python3 integrations/euclid_api.py --port 8080
# Preload a knowledge base so requests can omit the "knowledge" field:
python3 integrations/euclid_api.py --kb-path /path/to/policies.euclid --port 8080
# Require an API key on every POST and serve HTTPS:
python3 integrations/euclid_api.py --api-key "$(openssl rand -hex 32)" \
    --certfile /etc/euclid/cert.pem --keyfile /etc/euclid/key.pem --port 8080
```

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/reason` | POST | Send facts + rules, get proof-backed solutions |
| `/explain` | POST | Natural-language reasoning steps with rule ID citations |
| `/diagnose` | POST | Diagnose why a query succeeds or fails |
| `/what-if` | POST | What-if analysis with fact additions/removals |
| `/check-kb` | POST | Validate a knowledge base for consistency |
| `/health` | GET | Health check |

### Authentication & TLS

The API is **open by default** (no auth, plain HTTP) — intended for a trusted
loopback. Before exposing it beyond a trusted network, protect it:

- **API key** — set `EUCLID_API_KEY` (or `--api-key`). Every POST then requires
  the header `Authorization: Bearer <key>`; requests without a valid key get
  `401`. Comparison is constant-time. `GET /health` stays open so load
  balancers can probe it. Generate a strong key with
  `openssl rand -hex 32`.
- **TLS** — set `EUCLID_TLS_CERT` / `EUCLID_TLS_KEY` (or
  `--certfile` / `--keyfile`) to serve HTTPS directly, or terminate TLS at the
  load balancer and keep the API on plain HTTP inside the trusted network.

An API key sent over plain HTTP is **not** sufficient — always pair it with
HTTPS so the credential cannot be read in transit. See
`docs/PRODUCTION.md` → "Authentication & TLS" for the full setup.

**n8n setup:**
1. Add an **HTTP Request** node
2. Method: `POST`, URL: `https://host:8080/reason`
3. Headers: `Content-Type: application/json`, `Authorization: Bearer <api-key>`
4. Body (JSON): `{{ $json }}` with `knowledge`, `query`, etc.

**POST /explain** — Request body:

```json
{
  "knowledge": "human(socrates)\nmortal($x) IF human($x)  # RULE: BIO-001",
  "query": "mortal($who)",
  "max_solutions": 5,
  "max_depth": 30
}
```

Returns `explanations[]`, each with `substitutions` and an ordered list of
natural-language `steps` that cite rule IDs when present.

**POST /diagnose** — Request body:

```json
{
  "knowledge": "human(socrates)\nmortal($x) IF human($x)",
  "query": "mortal(plato)",
  "mode": "what_needs"
}
```

**POST /what-if** — Request body:

```json
{
  "base_knowledge": "human(socrates)\nmortal($x) IF human($x)",
  "modifications": "+ human(plato)",
  "query": "mortal($who)"
}
```

**POST /check-kb** — Request body:

```json
{
  "knowledge": "human(socrates)\nmortal($x) IF human($x)\n? mortal($who)"
}
```

## CLI (shell pipelines)

```bash
echo '{"knowledge": "red(apple)\\n? red($x)"}' | python3 integrations/euclid_cli.py

# Or with inline arguments
python3 integrations/euclid_cli.py '{"knowledge": "red(apple)\\n? red($x)", "max_solutions": 3}'
```

**n8n (executeCommand node):**
- Command: `python3`
- Parameters: `integrations/euclid_cli.py`, `'{"knowledge": "{{ $json.knowledge }}", "max_solutions": 5}'`

## OpenCode / Claude Desktop

Add to your `opencode.json` or `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "euclid-mcp": {
      "command": "python3",
      "args": ["-m", "euclid_mcp"],
      "cwd": "/path/to/euclid-mcp"
    }
  }
}
```

This project's `.opencode.json` includes a pre-configured `reasoning-engine` agent.
