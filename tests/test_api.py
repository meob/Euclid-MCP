"""Integration tests for the HTTP API (integrations/euclid_api.py)."""

import http.client
import json
import threading
from http.server import HTTPServer

from integrations.euclid_api import ReasonHandler

KB = "human(socrates)\nmortal($x) IF human($x)\n? mortal($who)"


class _TestServer:
    def __init__(self):
        self.server = HTTPServer(("127.0.0.1", 0), ReasonHandler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def _request(
    port: int,
    method: str,
    path: str,
    body: dict | None = None,
    raw_body: bytes | None = None,
):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    if body is not None:
        payload = json.dumps(body).encode()
        headers = {"Content-Type": "application/json"}
    elif raw_body is not None:
        payload = raw_body
        headers = {"Content-Type": "application/json"}
    else:
        payload = None
        headers = {}
    conn.request(method, path, body=payload, headers=headers)
    resp = conn.getresponse()
    data = json.loads(resp.read().decode())
    conn.close()
    return resp.status, data


class TestApi:
    def test_health(self):
        with _TestServer() as s:
            status, data = _request(s.port, "GET", "/health")
            assert status == 200
            assert data["status"] == "ok"

    def test_reason(self):
        with _TestServer() as s:
            status, data = _request(s.port, "POST", "/reason", {"knowledge": KB})
            assert status == 200
            assert len(data["solutions"]) == 1
            assert data["solutions"][0]["substitutions"]["who"] == "socrates"
            assert "elapsed_ms" in data

    def test_reason_missing_knowledge(self):
        with _TestServer() as s:
            status, data = _request(s.port, "POST", "/reason", {"knowledge": "  "})
            assert status == 400
            assert "knowledge" in data["error"]

    def test_diagnose(self):
        with _TestServer() as s:
            body = {"knowledge": KB, "query": "mortal(plato)", "mode": "why_not"}
            status, data = _request(s.port, "POST", "/diagnose", body)
            assert status == 200
            assert data["holds"] is False
            assert data["conclusion"]

    def test_what_if(self):
        with _TestServer() as s:
            body = {
                "base_knowledge": KB,
                "modifications": "+ human(plato)",
                "query": "mortal($who)",
            }
            status, data = _request(s.port, "POST", "/what-if", body)
            assert status == 200
            assert data["after_count"] > data["before_count"]
            assert data["delta"] == "more"

    def test_what_if_missing_fields(self):
        with _TestServer() as s:
            status, data = _request(s.port, "POST", "/what-if", {})
            assert status == 400

    def test_check_kb(self):
        with _TestServer() as s:
            status, data = _request(s.port, "POST", "/check-kb", {"knowledge": KB})
            assert status == 200
            assert data["valid"] is True
            assert data["facts_count"] == 1
            assert data["rules_count"] == 1

    def test_check_kb_invalid(self):
        with _TestServer() as s:
            body = {"knowledge": "mortal($x) IF ghost($x)"}
            status, data = _request(s.port, "POST", "/check-kb", body)
            assert status == 200
            assert data["valid"] is False

    def test_invalid_json(self):
        with _TestServer() as s:
            status, data = _request(s.port, "POST", "/reason", raw_body=b"{not json")
            assert status == 400
            assert "JSON" in data["error"]

    def test_unknown_post_path(self):
        with _TestServer() as s:
            status, data = _request(s.port, "POST", "/nope")
            assert status == 404
            assert "Not found" in data["error"]

    def test_unknown_get_path(self):
        with _TestServer() as s:
            status, data = _request(s.port, "GET", "/nope")
            assert status == 404
