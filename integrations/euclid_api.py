"""
Euclid-MCP HTTP API — for n8n / Zapier / automation workflows

Run:  python3 integrations/euclid_api.py [--port 8080]

Endpoints:
  POST /reason  —  Body: {"knowledge": "...", "query": "...", "max_solutions": 5, "max_depth": 30}
  GET  /health  —  Returns {"status": "ok"}

n8n usage: HTTP Request node → POST http://localhost:8080/reason
"""

import json
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from euclid_mcp.server import reason


class ReasonHandler(BaseHTTPRequestHandler):

    def do_POST(self):
        if self.path != "/reason":
            self._send(404, {"error": "Not found. POST to /reason or GET /health"})
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._send(400, {"error": "invalid JSON"})
            return

        knowledge = data.get("knowledge", "")
        if not knowledge.strip():
            self._send(400, {"error": "'knowledge' field is required"})
            return

        try:
            result = reason(
                knowledge=knowledge,
                query=data.get("query"),
                max_solutions=data.get("max_solutions", 5),
                max_depth=data.get("max_depth", 30),
            )
            self._send(200, {
                "query": result.query,
                "solutions": [s.model_dump() for s in result.solutions],
                "elapsed_ms": result.elapsed_ms,
            })
        except Exception as e:
            self._send(500, {"error": str(e)})

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"status": "ok", "service": "euclid-mcp"})
        else:
            self._send(404, {"error": "Not found"})

    def _send(self, status: int, data: dict):
        body = json.dumps(data, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"[euclid-api] {args[0]} {args[1]} {args[2]}", file=sys.stderr)


def main():
    port = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--port" else 8080
    server = HTTPServer(("0.0.0.0", port), ReasonHandler)
    print(f"Euclid-MCP API running on http://0.0.0.0:{port}")
    print(f"  POST /reason  —  deduct from facts and rules")
    print(f"  GET  /health  —  health check")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
