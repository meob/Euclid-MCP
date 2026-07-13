# Euclid-MCP Integrations

Tools to integrate Euclid-MCP into automation platforms and agent frameworks.

## HTTP API (n8n / Zapier / Make)

```bash
python3 integrations/euclid_api.py --port 8080
```

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/reason` | POST | Send facts + rules, get proof-backed solutions |
| `/health` | GET | Health check |

**POST /reason** — Request body:

```json
{
  "knowledge": "human(socrates)\nmortal($x) IF human($x)\n? mortal($who)",
  "max_solutions": 5,
  "max_depth": 30
}
```

**n8n setup:**
1. Add an **HTTP Request** node
2. Method: `POST`, URL: `http://localhost:8080/reason`
3. Headers: `Content-Type: application/json`
4. Body (JSON): `{{ $json }}` with `knowledge`, `query`, etc.

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
