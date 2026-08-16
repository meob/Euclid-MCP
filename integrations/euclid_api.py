"""
Euclid-MCP HTTP API — for n8n / Zapier / automation workflows

Run:  python3 integrations/euclid_api.py [--port 8080]

Endpoints:
  POST /reason       —  {"knowledge": "...", "query": "...", "max_solutions": 5, "max_depth": 30}
  POST /explain      —  {"knowledge": "...", "query": "...", "max_solutions": 5, "max_depth": 30}
  POST /diagnose     —  {"knowledge": "...", "query": "...", "mode": "why",
                         "max_solutions": 5, "max_depth": 30}
  POST /what-if      —  {"base_knowledge": "...", "modifications": "...", "query": "...",
                         "max_solutions": 5, "max_depth": 30}
  POST /check-kb     —  {"knowledge": "..."}
  POST /register-kb  —  {"kb_id": "...", "knowledge": "..."}
  POST /unregister-kb—  {"kb_id": "..."}
  POST /list-kbs     —  {}
  GET  /health       —  Deep health: 200 + engine stats (backend, facts/rules,
                         requests_since_restart) when the service can serve;
                         503 when an engine process exists but does not answer
  GET  /metrics      —  Prometheus text exposition of the process metrics
                         (open, read-only, never carries KB data)

Named KBs (kb_id): register a KB once with /register-kb, then pass `kb_id`
(and optionally `delta_knowledge` for a session-specific overlay) on any of
the five reasoning endpoints instead of resending the full KB text.

Authentication (optional but recommended for production):
  Set EUCLID_API_KEY (or pass --api-key) to require `Authorization: Bearer <key>`
  on every POST. Unauthenticated POSTs get 401. GET /health and GET /metrics
  stay open so load balancers and Prometheus can probe them. Without a key the
  API runs open — fine on a trusted loopback, not when exposed.

TLS (optional):
  Set EUCLID_TLS_CERT (and EUCLID_TLS_KEY, or --certfile/--keyfile) to serve
  HTTPS. Alternatively terminate TLS at the load balancer and keep the API on
  plain HTTP inside the trusted network.

n8n usage: HTTP Request node → POST https://host:8080/reason
           with header `Authorization: Bearer <api-key>`
"""

import argparse
import hmac
import json
import logging
import os
import signal
import ssl
import sys
import threading
import time
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

from euclid_mcp import prolog_bridge  # noqa: E402
from euclid_mcp.engine import resolve_backend  # noqa: E402
from euclid_mcp.metrics import (  # noqa: E402
    Counter,
    Gauge,
    Histogram,
    register,
)
from euclid_mcp.metrics import (  # noqa: E402
    render as render_metrics,
)
from euclid_mcp.server import (  # noqa: E402
    _PRELOADED_KB,
    _setup_logging,
    check_kb,
    diagnose,
    explain,
    list_kbs,
    reason,
    register_kb,
    unregister_kb,
    what_if,
)

logger = logging.getLogger("euclid_api")

# Process start wall clock; /metrics exposes uptime so a scraper (or the
# benchmark) can tell how long the API has been running.
_PROCESS_START = time.monotonic()

# Observability: Prometheus-compatible HTTP metrics (see docs/MONITORING.md
# Mode C). Scraped from GET /metrics; none of these carry KB content.
http_requests_total = register(Counter(
    "euclid_http_requests_total",
    "HTTP requests by method, path and response status.",
    labels=("method", "path", "status"),
))
http_request_duration_seconds = register(Histogram(
    "euclid_http_request_duration_seconds",
    "HTTP request latency in seconds, by path.",
    labels=("path",),
))
solutions_total = register(Counter(
    "euclid_solutions_total",
    "Solutions/answers returned by reasoning endpoints, by path.",
    labels=("path",),
))
auth_failures_total = register(Counter(
    "euclid_auth_failures_total",
    "Rejected requests (401) due to a missing or invalid API key.",
))
process_uptime_seconds = register(Gauge(
    "euclid_process_uptime_seconds",
    "Seconds since the API process started.",
))


def _optional_knowledge(raw) -> str | None:
    """Normalize a raw knowledge field: whitespace-only → None (preload)."""
    value = (raw or "").strip()
    return value or None


def _tls_server_context(certfile: str, keyfile: str | None) -> ssl.SSLContext:
    """Build a server-side TLS context for the API socket."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile, keyfile)
    return ctx


class ReasonHandler(BaseHTTPRequestHandler):

    def _extract_request_id(self):
        self._request_id = self.headers.get("X-Request-Id") or None

    def _authenticated(self) -> bool:
        """True when the request carries a valid API key (or auth is off).

        The comparison is constant-time so a remote client cannot measure the
        key length-wise or byte-wise via response timing.
        """
        expected = os.environ.get("EUCLID_API_KEY") or ""
        if not expected:
            return True
        scheme, _, token = self.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            return False
        return hmac.compare_digest(token, expected)

    def do_POST(self):
        self._start_request()
        if not self._authenticated():
            auth_failures_total.inc()
            self._send(401, {"error": "unauthorized: send Authorization: Bearer <api-key>"})
            return
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
        elif self.path == "/register-kb":
            self._handle_register_kb()
        elif self.path == "/unregister-kb":
            self._handle_unregister_kb()
        elif self.path == "/list-kbs":
            self._handle_list_kbs()
        else:
            self._send(
                404,
                {
                    "error": (
                        "Not found. POST to /reason, /explain, /diagnose, /what-if, "
                        "/check-kb, /register-kb, /unregister-kb, /list-kbs "
                        "or GET /health, /metrics"
                    )
                },
            )

    def _handle_reason(self):
        data = self._read_body()
        if data is None:
            return

        knowledge = _optional_knowledge(data.get("knowledge"))
        if knowledge is None and not data.get("kb_id") and _PRELOADED_KB is None:
            self._send(
                400,
                {"error": "'knowledge' field is required (or pass 'kb_id', or "
                         "preload a KB via EUCLID_KB_PATH / --kb-path)"},
            )
            return

        try:
            result = reason(
                knowledge=knowledge,
                kb_id=data.get("kb_id"),
                delta_knowledge=data.get("delta_knowledge"),
                query=data.get("query"),
                max_solutions=data.get("max_solutions", 5),
                max_depth=data.get("max_depth", 30),
            )
            self._record_solutions(len(result.solutions))
            self._send(200, {
                "query": result.query,
                "solutions": [s.model_dump() for s in result.solutions],
                "elapsed_ms": result.elapsed_ms,
                "content_hash": result.content_hash,
                "version": result.version,
            })
        except Exception as e:
            self._send(500, {"error": str(e)})

    def _handle_explain(self):
        data = self._read_body()
        if data is None:
            return

        knowledge = _optional_knowledge(data.get("knowledge"))
        if knowledge is None and not data.get("kb_id") and _PRELOADED_KB is None:
            self._send(
                400,
                {"error": "'knowledge' field is required (or pass 'kb_id', or "
                         "preload a KB via EUCLID_KB_PATH / --kb-path)"},
            )
            return

        try:
            result = explain(
                knowledge=knowledge,
                kb_id=data.get("kb_id"),
                delta_knowledge=data.get("delta_knowledge"),
                query=data.get("query"),
                max_solutions=data.get("max_solutions", 5),
                max_depth=data.get("max_depth", 30),
            )
            self._record_solutions(len(result.explanations))
            self._send(200, {
                "query": result.query,
                "explanations": [
                    {
                        "substitutions": e.substitutions,
                        "steps": e.steps,
                        "structured_steps": [s.model_dump() for s in e.structured_steps],
                    }
                    for e in result.explanations
                ],
                "elapsed_ms": result.elapsed_ms,
                "content_hash": result.content_hash,
                "version": result.version,
            })
        except Exception as e:
            self._send(500, {"error": str(e)})

    def _handle_diagnose(self):
        data = self._read_body()
        if data is None:
            return

        knowledge = _optional_knowledge(data.get("knowledge"))
        query = data.get("query", "")
        if knowledge is None and not data.get("kb_id") and _PRELOADED_KB is None:
            self._send(
                400,
                {"error": "'knowledge' field is required (or pass 'kb_id', or "
                         "preload a KB via EUCLID_KB_PATH / --kb-path)"},
            )
            return
        if not query.strip():
            self._send(400, {"error": "'query' field is required"})
            return

        try:
            result = diagnose(
                knowledge=knowledge,
                kb_id=data.get("kb_id"),
                delta_knowledge=data.get("delta_knowledge"),
                query=query,
                mode=data.get("mode", "why"),
                max_solutions=data.get("max_solutions", 5),
                max_depth=data.get("max_depth", 30),
            )
            self._record_solutions(len(result.solutions))
            self._send(200, {
                "query": result.query,
                "mode": result.mode,
                "holds": result.holds,
                "findings": [f.model_dump() for f in result.findings],
                "conclusion": result.conclusion,
                "solutions": [s.model_dump() for s in result.solutions],
                "elapsed_ms": result.elapsed_ms,
                "content_hash": result.content_hash,
                "version": result.version,
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
        if base_knowledge is None and not data.get("kb_id") and _PRELOADED_KB is None:
            self._send(
                400,
                {"error": "'base_knowledge' field is required (or pass 'kb_id', "
                         "or preload a KB via EUCLID_KB_PATH / --kb-path)"},
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
                kb_id=data.get("kb_id"),
                delta_knowledge=data.get("delta_knowledge"),
                modifications=modifications,
                query=query,
                max_solutions=data.get("max_solutions", 5),
                max_depth=data.get("max_depth", 30),
            )
            self._record_solutions(len(result.solutions_before) + len(result.solutions_after))
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
                "content_hash": result.content_hash,
                "version": result.version,
            })
        except Exception as e:
            self._send(500, {"error": str(e)})

    def _handle_check_kb(self):
        data = self._read_body()
        if data is None:
            return

        knowledge = _optional_knowledge(data.get("knowledge"))
        if knowledge is None and not data.get("kb_id") and _PRELOADED_KB is None:
            self._send(
                400,
                {"error": "'knowledge' field is required (or pass 'kb_id', or "
                         "preload a KB via EUCLID_KB_PATH / --kb-path)"},
            )
            return

        try:
            result = check_kb(
                knowledge=knowledge,
                kb_id=data.get("kb_id"),
                delta_knowledge=data.get("delta_knowledge"),
            )
            self._send(200, {
                "valid": result.valid,
                "errors": [e.model_dump() for e in result.errors],
                "warnings": [w.model_dump() for w in result.warnings],
                "facts_count": result.facts_count,
                "rules_count": result.rules_count,
                "predicates_count": result.predicates_count,
                "predicates": [p.model_dump() for p in result.predicates],
                "elapsed_ms": result.elapsed_ms,
                "content_hash": result.content_hash,
                "version": result.version,
            })
        except Exception as e:
            self._send(500, {"error": str(e)})

    def _handle_register_kb(self):
        data = self._read_body()
        if data is None:
            return
        try:
            result = register_kb(
                kb_id=data.get("kb_id"),
                knowledge=data.get("knowledge"),
            )
            self._send(200, result)
        except Exception as e:
            self._send(500, {"error": str(e)})

    def _handle_unregister_kb(self):
        data = self._read_body()
        if data is None:
            return
        try:
            result = unregister_kb(kb_id=data.get("kb_id"))
            self._send(200, result)
        except Exception as e:
            self._send(500, {"error": str(e)})

    def _handle_list_kbs(self):
        data = self._read_body()
        if data is None:
            return
        try:
            result = list_kbs()
            self._send(200, result)
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
        self._start_request()
        if self.path == "/health":
            self._handle_health()
        elif self.path == "/metrics":
            self._handle_metrics()
        else:
            self._send(404, {"error": "Not found. GET /health or GET /metrics"})

    def _start_request(self):
        """Mark the request start for per-request latency and the request id."""
        self._extract_request_id()
        self._request_started = time.monotonic()

    def _record_http(self, status: int):
        path = self.path.split("?", 1)[0]
        http_requests_total.inc(method=self.command, path=path, status=status)
        http_request_duration_seconds.observe(
            time.monotonic() - self._request_started, path=path
        )

    def _record_solutions(self, count: int):
        """Track solutions returned on a reasoning endpoint (0 → nothing)."""
        if count:
            solutions_total.inc(count, path=self.path.split("?", 1)[0])

    def _handle_health(self):
        """Deep health check: probe the engine process itself.

        200 with an `engine` section when the service can serve requests (a
        cold process with no engine yet is healthy — the engine starts lazily
        on the first request). 503 only when an engine process exists but does
        not answer a ping (wedged). The native backend has no engine process
        and is healthy by default.
        """
        backend = resolve_backend()
        if backend == "prolog":
            info = prolog_bridge.health_info()
            if info is not None and not info.get("reachable", True):
                self._send(503, {
                    "status": "degraded",
                    "service": "euclid-mcp",
                    "engine": info,
                })
                return
            engine = info if info is not None else {
                "backend": "prolog",
                "reachable": True,
            }
        else:
            engine = {"backend": backend}
        self._send(200, {"status": "ok", "service": "euclid-mcp", "engine": engine})

    def _handle_metrics(self):
        """Prometheus text exposition; open and read-only, never KB content."""
        process_uptime_seconds.set(time.monotonic() - _PROCESS_START)
        self._record_http(200)
        body = render_metrics().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, OSError):
            # A client (e.g. Prometheus) disconnecting mid-scrape is normal.
            logger.debug(
                "client disconnected mid-scrape (request_id=%s)",
                getattr(self, "_request_id", None),
            )

    def _send(self, status: int, data: dict):
        self._record_http(status)
        body = json.dumps(data, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.send_header("Access-Control-Allow-Origin", "*")
        if status == 401:
            self.send_header("WWW-Authenticate", "Bearer")
        if getattr(self, "_request_id", None):
            self.send_header("X-Request-Id", self._request_id)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, OSError):
            # A client disconnecting mid-response is normal on real TCP
            # (e.g. it timed out or moved on); not a server error.
            logger.debug(
                "client disconnected mid-response (request_id=%s)",
                getattr(self, "_request_id", None),
            )

    def log_message(self, fmt, *args):
        request_id = getattr(self, "_request_id", None) or "-"
        logger.info("request_id=%s %s", request_id, fmt % args)


def main():
    _setup_logging()
    parser = argparse.ArgumentParser(
        description="Euclid-MCP HTTP API — for n8n / Zapier / automation workflows"
    )
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument(
        "--kb-path",
        help="preload a KB file (also via EUCLID_KB_PATH); read at startup",
    )
    parser.add_argument(
        "--api-key",
        help="require `Authorization: Bearer <key>` on every POST "
        "(also via EUCLID_API_KEY)",
    )
    parser.add_argument(
        "--certfile",
        help="PEM TLS certificate to serve HTTPS (also via EUCLID_TLS_CERT)",
    )
    parser.add_argument(
        "--keyfile",
        help="PEM TLS private key (also via EUCLID_TLS_KEY); "
        "defaults to reading it from --certfile",
    )
    args = parser.parse_args()

    if args.api_key:
        os.environ["EUCLID_API_KEY"] = args.api_key
    if not os.environ.get("EUCLID_API_KEY"):
        logger.warning(
            "No EUCLID_API_KEY set: the API accepts every POST. Set a key "
            "(and terminate TLS) before exposing it beyond a trusted network."
        )

    certfile = args.certfile or os.environ.get("EUCLID_TLS_CERT")
    keyfile = args.keyfile or os.environ.get("EUCLID_TLS_KEY")

    server = HTTPServer(("0.0.0.0", args.port), ReasonHandler)
    scheme = "http"
    if certfile:
        server.socket = _tls_server_context(certfile, keyfile).wrap_socket(
            server.socket, server_side=True
        )
        scheme = "https"
    logger.info("Euclid-MCP API running on %s://0.0.0.0:%d", scheme, args.port)
    print(f"Euclid-MCP API running on {scheme}://0.0.0.0:{args.port}")
    print("  POST /reason       —  deduct from facts and rules")
    print("  POST /explain      —  explain results in natural language")
    print("  POST /diagnose     —  diagnose why a query succeeds or fails")
    print("  POST /what-if      —  what-if analysis on knowledge base")
    print("  POST /check-kb     —  check KB for consistency")
    print("  POST /register-kb  —  register a named KB (kb_id)")
    print("  POST /unregister-kb—  remove a named KB")
    print("  POST /list-kbs     —  list registered named KBs")
    print("  GET  /health       —  health check (deep: pings the engine)")
    print("  GET  /metrics      —  Prometheus metrics (open, read-only)")
    if os.environ.get("EUCLID_API_KEY"):
        print("  Auth            —  API key required (Authorization: Bearer)")
    if _PRELOADED_KB is not None:
        kb_path = os.environ.get("EUCLID_KB_PATH")
        print(f"  Preloaded KB   —  {kb_path}")

    # Graceful shutdown: on SIGTERM/SIGINT stop accepting requests, finish the
    # in-flight one, then close the socket and the engine. shutdown() must run
    # off the main thread (the main thread is inside serve_forever()).
    def _request_shutdown(_signum, _frame):
        logger.info("received termination signal; shutting down gracefully")
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _request_shutdown)
    signal.signal(signal.SIGINT, _request_shutdown)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        # Only reached when signals are not installable (e.g. non-main thread).
        server.shutdown()
    finally:
        server.server_close()
        prolog_bridge.close()
        logger.info("API shut down cleanly")


if __name__ == "__main__":
    main()
