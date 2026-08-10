"""
Euclid-MCP HTTP API — for n8n / Zapier / automation workflows

Run:  python3 integrations/euclid_api.py [--port 8080]

Endpoints:
  POST /reason    —  {"knowledge": "...", "query": "...", "max_solutions": 5, "max_depth": 30}
  POST /explain   —  {"knowledge": "...", "query": "...", "max_solutions": 5, "max_depth": 30}
  POST /diagnose  —  {"knowledge": "...", "query": "...", "mode": "why",
                      "max_solutions": 5, "max_depth": 30}
  POST /what-if   —  {"base_knowledge": "...", "modifications": "...", "query": "...",
                      "max_solutions": 5, "max_depth": 30}
  POST /check-kb  —  {"knowledge": "..."}
  GET  /health    —  Returns {"status": "ok"}

n8n usage: HTTP Request node → POST http://localhost:8080/reason
"""

import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _apply_kb_path_arg() -> None:
    """Funnel a `--kb-path` CLI flag into EUCLID_KB_PATH before import.

    KB preload happens at server-module import time, so the flag must be
    applied before `from euclid_mcp.server import ...` below.
    """
    if "--kb-path" in sys.argv:
        idx = sys.argv.index("--kb-path")
        if idx + 1 < len(sys.argv):
            os.environ["EUCLID_KB_PATH"] = sys.argv[idx + 1]


_apply_kb_path_arg()

from euclid_mcp.server import (  # noqa: E402
    _PRELOADED_KB,
    _setup_logging,
    check_kb,
    diagnose,
    explain,
    reason,
    what_if,
)

logger = logging.getLogger("euclid_api")


def _optional_knowledge(raw) -> str | None:
    """Normalize a raw knowledge field: whitespace-only → None (preload)."""
    value = (raw or "").strip()
    return value or None


class ReasonHandler(BaseHTTPRequestHandler):

    def _extract_request_id(self):
        self._request_id = self.headers.get("X-Request-Id") or None

    def do_POST(self):
        self._extract_request_id()
        if self.path == "/reason":
            self._handle_reason()
        elif self.path == "/explain":
            self._handle_explain()
        elif self.path == "/diagnose":
            self._handle_diagnose()
        elif self.path == "/what-if":
            self._handle_what_if()
        elif self.path == "/check-kb":
            self._handle_check_kb()
        else:
            self._send(
                404,
                {
                    "error": (
                        "Not found. POST to /reason, /explain, /diagnose, /what-if, "
                        "/check-kb or GET /health"
                    )
                },
            )

    def _handle_reason(self):
        data = self._read_body()
        if data is None:
            return

        knowledge = _optional_knowledge(data.get("knowledge"))
        if knowledge is None and _PRELOADED_KB is None:
            self._send(
                400,
                {"error": "'knowledge' field is required (or preload a KB "
                         "via EUCLID_KB_PATH / --kb-path)"},
            )
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

    def _handle_explain(self):
        data = self._read_body()
        if data is None:
            return

        knowledge = _optional_knowledge(data.get("knowledge"))
        if knowledge is None and _PRELOADED_KB is None:
            self._send(
                400,
                {"error": "'knowledge' field is required (or preload a KB "
                         "via EUCLID_KB_PATH / --kb-path)"},
            )
            return

        try:
            result = explain(
                knowledge=knowledge,
                query=data.get("query"),
                max_solutions=data.get("max_solutions", 5),
                max_depth=data.get("max_depth", 30),
            )
            self._send(200, {
                "query": result.query,
                "explanations": [
                    {
                        "substitutions": e.substitutions,
                        "steps": e.steps,
                    }
                    for e in result.explanations
                ],
                "elapsed_ms": result.elapsed_ms,
            })
        except Exception as e:
            self._send(500, {"error": str(e)})

    def _handle_diagnose(self):
        data = self._read_body()
        if data is None:
            return

        knowledge = _optional_knowledge(data.get("knowledge"))
        query = data.get("query", "")
        if knowledge is None and _PRELOADED_KB is None:
            self._send(
                400,
                {"error": "'knowledge' field is required (or preload a KB "
                         "via EUCLID_KB_PATH / --kb-path)"},
            )
            return
        if not query.strip():
            self._send(400, {"error": "'query' field is required"})
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

        base_knowledge = _optional_knowledge(data.get("base_knowledge"))
        modifications = data.get("modifications", "")
        query = data.get("query", "")
        if base_knowledge is None and _PRELOADED_KB is None:
            self._send(
                400,
                {"error": "'base_knowledge' field is required (or preload a KB "
                         "via EUCLID_KB_PATH / --kb-path)"},
            )
            return
        if not modifications.strip() or not query.strip():
            self._send(
                400,
                {"error": "'modifications', and 'query' fields are required"},
            )
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

        knowledge = _optional_knowledge(data.get("knowledge"))
        if knowledge is None and _PRELOADED_KB is None:
            self._send(
                400,
                {"error": "'knowledge' field is required (or preload a KB "
                         "via EUCLID_KB_PATH / --kb-path)"},
            )
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
            return dict(json.loads(body))
        except json.JSONDecodeError:
            self._send(400, {"error": "invalid JSON"})
            return None

    def do_GET(self):
        self._extract_request_id()
        if self.path == "/health":
            self._send(200, {"status": "ok", "service": "euclid-mcp"})
        else:
            self._send(404, {"error": "Not found"})

    def _send(self, status: int, data: dict):
        body = json.dumps(data, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        if getattr(self, "_request_id", None):
            self.send_header("X-Request-Id", self._request_id)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        request_id = getattr(self, "_request_id", None) or "-"
        logger.info("request_id=%s %s", request_id, fmt % args)


def main():
    _setup_logging()
    port = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--port" else 8080
    server = HTTPServer(("0.0.0.0", port), ReasonHandler)
    logger.info("Euclid-MCP API running on http://0.0.0.0:%d", port)
    print(f"Euclid-MCP API running on http://0.0.0.0:{port}")
    print("  POST /reason    —  deduct from facts and rules")
    print("  POST /explain   —  explain results in natural language")
    print("  POST /diagnose  —  diagnose why a query succeeds or fails")
    print("  POST /what-if   —  what-if analysis on knowledge base")
    print("  POST /check-kb  —  check KB for consistency")
    print("  GET  /health    —  health check")
    if _PRELOADED_KB is not None:
        kb_path = os.environ.get("EUCLID_KB_PATH")
        print(f"  Preloaded KB   —  {kb_path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
