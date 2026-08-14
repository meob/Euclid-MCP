"""Integration tests for the HTTP API (integrations/euclid_api.py)."""

import hashlib
import http.client
import json
import shutil
import ssl
import subprocess
import threading
from http.server import HTTPServer

import pytest

from integrations.euclid_api import ReasonHandler, _tls_server_context

KB = "human(socrates)\nmortal($x) IF human($x)\n? mortal($who)"
KB_HASH = hashlib.sha256(KB.encode("utf-8")).hexdigest()


class _TestServer:
    def __init__(self, tls_context: ssl.SSLContext | None = None):
        self.server = HTTPServer(("127.0.0.1", 0), ReasonHandler)
        if tls_context is not None:
            self.server.socket = tls_context.wrap_socket(
                self.server.socket, server_side=True
            )
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
    headers: dict | None = None,
    tls: bool = False,
):
    conn_cls = http.client.HTTPSConnection if tls else http.client.HTTPConnection
    kwargs = {"timeout": 10}
    if tls:
        kwargs["context"] = ssl._create_unverified_context()
    conn = conn_cls("127.0.0.1", port, **kwargs)
    hdrs = dict(headers or {})
    if body is not None:
        payload = json.dumps(body).encode()
        hdrs.setdefault("Content-Type", "application/json")
    elif raw_body is not None:
        payload = raw_body
        hdrs.setdefault("Content-Type", "application/json")
    else:
        payload = None
    conn.request(method, path, body=payload, headers=hdrs)
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

    def test_request_id_echo(self):
        with _TestServer() as s:
            conn = http.client.HTTPConnection("127.0.0.1", s.port, timeout=10)
            headers = {
                "Content-Type": "application/json",
                "X-Request-Id": "req-123",
            }
            conn.request(
                "POST",
                "/reason",
                body=json.dumps({"knowledge": KB}).encode(),
                headers=headers,
            )
            resp = conn.getresponse()
            resp.read()
            assert resp.getheader("X-Request-Id") == "req-123"
            conn.close()

    def test_reason(self):
        with _TestServer() as s:
            status, data = _request(s.port, "POST", "/reason", {"knowledge": KB})
            assert status == 200
            assert len(data["solutions"]) == 1
            assert data["solutions"][0]["substitutions"]["who"] == "socrates"
            assert "elapsed_ms" in data
            assert data["content_hash"] == KB_HASH
            assert "version" in data

    def test_reason_missing_knowledge(self):
        with _TestServer() as s:
            status, data = _request(s.port, "POST", "/reason", {"knowledge": "  "})
            assert status == 400
            assert "knowledge" in data["error"]

    def test_explain(self):
        with _TestServer() as s:
            status, data = _request(s.port, "POST", "/explain", {"knowledge": KB})
            assert status == 200
            assert len(data["explanations"]) == 1
            exp = data["explanations"][0]
            assert exp["substitutions"]["who"] == "socrates"
            assert any("mortal(socrates)" in s for s in exp["steps"])
            assert "elapsed_ms" in data

    def test_explain_structured_steps(self):
        with _TestServer() as s:
            status, data = _request(s.port, "POST", "/explain", {"knowledge": KB})
            assert status == 200
            exp = data["explanations"][0]
            assert len(exp["structured_steps"]) == len(exp["steps"])
            kinds = [step["kind"] for step in exp["structured_steps"]]
            assert kinds == ["rule", "fact"]
            rule_step = exp["structured_steps"][0]
            assert rule_step["goal"] == "mortal(socrates)"
            assert rule_step["body"] == ["human(socrates)"]
            assert exp["structured_steps"][1]["goal"] == "human(socrates)"

    def test_explain_missing_knowledge(self):
        with _TestServer() as s:
            status, data = _request(s.port, "POST", "/explain", {"knowledge": "  "})
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
            assert data["content_hash"] == KB_HASH
            assert "version" in data

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


class TestApiIdentity:
    """KB identity (C4): content_hash/version exposed on every endpoint."""

    def test_explain_exposes_identity(self):
        with _TestServer() as s:
            status, data = _request(s.port, "POST", "/explain", {"knowledge": KB})
            assert status == 200
            assert data["content_hash"] == KB_HASH
            assert "version" in data

    def test_diagnose_exposes_identity(self):
        with _TestServer() as s:
            body = {"knowledge": KB, "query": "mortal(plato)"}
            status, data = _request(s.port, "POST", "/diagnose", body)
            assert status == 200
            assert data["content_hash"] == KB_HASH
            assert "version" in data

    def test_what_if_exposes_identity(self):
        with _TestServer() as s:
            body = {
                "base_knowledge": KB,
                "modifications": "+ human(plato)",
                "query": "mortal($who)",
            }
            status, data = _request(s.port, "POST", "/what-if", body)
            assert status == 200
            assert data["content_hash"] == KB_HASH
            assert "version" in data

    def test_identity_present_on_error_branch(self):
        with _TestServer() as s:
            # KB without a query -> tool-level error (no solutions), the
            # response still carries the content hash of the payload
            body = {"knowledge": "human(socrates)"}
            status, data = _request(s.port, "POST", "/reason", body)
            assert status == 200
            assert data["solutions"] == []
            expected = hashlib.sha256("human(socrates)".encode("utf-8")).hexdigest()
            assert data["content_hash"] == expected


class TestApiAuth:
    """EUCLID_API_KEY gates every POST; /health stays open for the LB."""

    def test_open_without_key(self, monkeypatch):
        monkeypatch.delenv("EUCLID_API_KEY", raising=False)
        with _TestServer() as s:
            status, _ = _request(s.port, "POST", "/reason", {"knowledge": KB})
            assert status == 200

    def test_reject_missing_key(self, monkeypatch):
        monkeypatch.setenv("EUCLID_API_KEY", "secret-123")
        with _TestServer() as s:
            status, data = _request(s.port, "POST", "/reason", {"knowledge": KB})
            assert status == 401
            assert "Authorization" in data["error"]

    def test_reject_wrong_key(self, monkeypatch):
        monkeypatch.setenv("EUCLID_API_KEY", "secret-123")
        with _TestServer() as s:
            status, _ = _request(
                s.port,
                "POST",
                "/reason",
                {"knowledge": KB},
                headers={"Authorization": "Bearer wrong-key"},
            )
            assert status == 401

    def test_reject_wrong_scheme(self, monkeypatch):
        monkeypatch.setenv("EUCLID_API_KEY", "secret-123")
        with _TestServer() as s:
            status, _ = _request(
                s.port,
                "POST",
                "/reason",
                {"knowledge": KB},
                headers={"Authorization": "Basic c2VjcmV0"},
            )
            assert status == 401

    def test_accept_valid_key(self, monkeypatch):
        monkeypatch.setenv("EUCLID_API_KEY", "secret-123")
        with _TestServer() as s:
            status, data = _request(
                s.port,
                "POST",
                "/reason",
                {"knowledge": KB},
                headers={"Authorization": "Bearer secret-123"},
            )
            assert status == 200
            assert data["solutions"][0]["substitutions"]["who"] == "socrates"

    def test_health_stays_open(self, monkeypatch):
        monkeypatch.setenv("EUCLID_API_KEY", "secret-123")
        with _TestServer() as s:
            status, data = _request(s.port, "GET", "/health")
            assert status == 200
            assert data["status"] == "ok"


class TestApiTls:
    def test_https_serves(self, tmp_path):
        openssl = shutil.which("openssl")
        if not openssl:
            pytest.skip("openssl not installed")
        cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
        subprocess.run(
            [
                openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                "-keyout", str(key), "-out", str(cert), "-days", "1",
                "-subj", "/CN=localhost",
            ],
            check=True,
            capture_output=True,
        )
        ctx = _tls_server_context(str(cert), str(key))
        with _TestServer(tls_context=ctx) as s:
            status, data = _request(
                s.port, "GET", "/health", tls=True
            )
            assert status == 200
            assert data["status"] == "ok"
