"""
Euclid-MCP HTTP API — for n8n / Zapier / automation workflows

Run:  python3 integrations/euclid_api.py [--port 8080]

Endpoints:
  POST /reason    —  {"knowledge": "...", "query": "...", "max_solutions": 5, "max_depth": 30}
  POST /diagnose  —  {"knowledge": "...", "query": "...", "mode": "why", "max_solutions": 5, "max_depth": 30}
  POST /what-if   —  {"base_knowledge": "...", "modifications": "...", "query": "...", "max_solutions": 5, "max_depth": 30}
  POST /check-kb  —  {"knowledge": "..."}
  GET  /health    —  Returns {"status": "ok"}

n8n usage: HTTP Request node → POST http://localhost:8080/reason
"""

import json
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from euclid_mcp.server import check_kb, diagnose, reason, what_if


class ReasonHandler(BaseHTTPRequestHandler):

    def do_POST(self):
        if self.path == "/reason":
            self._handle_reason()
        elif self.path == "/diagnose":
            self._handle_diagnose()
        elif self.path == "/what-if":
            self._handle_what_if()
        elif self.path == "/check-kb":
            self._handle_check_kb()
        else:
            self._send(404, {"error": "Not found. POST to /reason, /diagnose, /what-if, /check-kb or GET /health"})

    def _handle_reason(self):
        data = self._read_body()
        if data is None:
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

    def _handle_diagnose(self):
        data = self._read_body()
        if data is None:
            return

        knowledge = data.get("knowledge", "")
        query = data.get("query", "")
        if not knowledge.strip() or not query.strip():
            self._send(400, {"error": "'knowledge' and 'query' fields are required"})
            return

        try:
            result = diagnose(
                knowledge=knowledge,
                query=query,
                mode=data.get("mode", "why"),
                max_solutions=data.get("max_solutions", 5),
                max_depth=data.get("max_depth", 30),
            )
            self._send(200, {
                "query": result.query,
                "mode": result.mode,
                "holds": result.holds,
                "findings": [f.model_dump() for f in result.findings],
                "conclusion": result.conclusion,
                "solutions": [s.model_dump() for s in result.solutions],
                "elapsed_ms": result.elapsed_ms,
            })
        except Exception as e:
            self._send(500, {"error": str(e)})

    def _handle_what_if(self):
        data = self._read_body()
        if data is None:
            return

        base_knowledge = data.get("base_knowledge", "")
        modifications = data.get("modifications", "")
        query = data.get("query", "")
        if not base_knowledge.strip() or not modifications.strip() or not query.strip():
            self._send(400, {"error": "'base_knowledge', 'modifications', and 'query' fields are required"})
            return

        try:
            result = what_if(
                base_knowledge=base_knowledge,
                modifications=modifications,
                query=query,
                max_solutions=data.get("max_solutions", 5),
                max_depth=data.get("max_depth", 30),
            )
            self._send(200, {
                "query": result.query,
                "modifications": result.modifications,
                "before_count": result.before_count,
                "after_count": result.after_count,
                "delta": result.delta,
                "conclusion": result.conclusion,
                "solutions_before": [s.model_dump() for s in result.solutions_before],
                "solutions_after": [s.model_dump() for s in result.solutions_after],
                "elapsed_ms": result.elapsed_ms,
            })
        except Exception as e:
            self._send(500, {"error": str(e)})

    def _handle_check_kb(self):
        data = self._read_body()
        if data is None:
            return

        knowledge = data.get("knowledge", "")
        if not knowledge.strip():
            self._send(400, {"error": "'knowledge' field is required"})
            return

        try:
            result = check_kb(knowledge=knowledge)
            self._send(200, {
                "valid": result.valid,
                "errors": [e.model_dump() for e in result.errors],
                "warnings": [w.model_dump() for w in result.warnings],
                "facts_count": result.facts_count,
                "rules_count": result.rules_count,
                "predicates_count": result.predicates_count,
                "elapsed_ms": result.elapsed_ms,
            })
        except Exception as e:
            self._send(500, {"error": str(e)})

    def _read_body(self) -> dict | None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            self._send(400, {"error": "invalid JSON"})
            return None

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
    print(f"  POST /reason    —  deduct from facts and rules")
    print(f"  POST /diagnose  —  diagnose why a query succeeds or fails")
    print(f"  POST /what-if   —  what-if analysis on knowledge base")
    print(f"  POST /check-kb  —  check KB for consistency")
    print(f"  GET  /health    —  health check")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
