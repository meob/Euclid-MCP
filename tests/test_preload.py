"""Tests for KB preload (EUCLID_KB_PATH / --kb-path).

Preload happens at server-module import time, so the file-level tests run the
module in a fresh subprocess with the env var set.
"""

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest
from mcp import Client

from euclid_mcp.server import (
    check_kb,
    diagnose,
    explain,
    mcp,
    reason,
    what_if,
)

ROOT = Path(__file__).resolve().parent.parent

PRELOAD_KB = (
    "human(socrates)\n"
    "human(plato)\n"
    "mortal($x) IF human($x)  # rule: MORTAL-1\n"
    "? mortal($who)\n"
)

QUERY_KB = PRELOAD_KB + "? mortal($who)"


def _run(env_path: str | None, code: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop("EUCLID_KB_PATH", None)
    env["PYTHONPATH"] = str(ROOT)
    if env_path is not None:
        env["EUCLID_KB_PATH"] = env_path
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
        timeout=60,
    )


@pytest.fixture
def preload_file(tmp_path: Path) -> Path:
    path = tmp_path / "kb.euclid"
    path.write_text(PRELOAD_KB, encoding="utf-8")
    return path


class TestPreloadFromFile:
    def test_preloads_kb_and_reasons_without_knowledge(self, preload_file: Path):
        code = (
            "import euclid_mcp.server as s\n"
            "print('KB_START')\n"
            "print(s._PRELOADED_KB)\n"
            "print('KB_END')\n"
            "r = s.reason(query='mortal($who)')\n"
            "print(sorted(x.substitutions['who'] for x in r.solutions))\n"
        )
        proc = _run(str(preload_file), code)
        assert proc.returncode == 0, proc.stderr
        out = proc.stdout
        body = out.split("KB_START")[1].split("KB_END")[0]
        assert body.strip() == PRELOAD_KB.strip()
        assert "['plato', 'socrates']" in out

    def test_explicit_knowledge_overrides_preload(self, preload_file: Path):
        code = (
            "import euclid_mcp.server as s\n"
            "r = s.reason('human(aristotle)', query='human($who)')\n"
            "print(sorted(x.substitutions['who'] for x in r.solutions))\n"
        )
        proc = _run(str(preload_file), code)
        assert proc.returncode == 0, proc.stderr
        assert "['aristotle']" in proc.stdout

    def test_digest_appended_to_instructions(self, preload_file: Path):
        code = (
            "import euclid_mcp.server as s\n"
            "print('Preloaded Knowledge Base' in s.mcp.instructions)\n"
            "print('mortal/1' in s.mcp.instructions)\n"
            "print('rule: MORTAL-1' in s.mcp.instructions)\n"
        )
        proc = _run(str(preload_file), code)
        assert proc.returncode == 0, proc.stderr
        assert "True\nTrue\nTrue" in proc.stdout

    def test_missing_file_fails_fast(self):
        proc = _run("/tmp/euclid-does-not-exist.euclid", "import euclid_mcp.server")
        assert proc.returncode != 0
        assert "EUCLID_KB_PATH" in proc.stderr
        assert "missing file" in proc.stderr

    def test_invalid_kb_fails_fast(self, tmp_path: Path):
        bad = tmp_path / "bad.euclid"
        bad.write_text("mortal($x) IF ghost($x)\n", encoding="utf-8")
        proc = _run(str(bad), "import euclid_mcp.server")
        assert proc.returncode != 0
        assert "not a valid knowledge base" in proc.stderr
        assert "ghost/1" in proc.stderr

    def test_no_preload_env_is_none(self):
        proc = _run(None, "import euclid_mcp.server as s\nprint(s._PRELOADED_KB)")
        assert proc.returncode == 0, proc.stderr
        assert "None" in proc.stdout

    def test_api_reason_without_knowledge_uses_preload(self, preload_file: Path):
        code = (
            "import json, sys, threading\n"
            "from http.client import HTTPConnection\n"
            "from http.server import HTTPServer\n"
            "sys.path.insert(0, '.')\n"
            "from integrations.euclid_api import ReasonHandler\n"
            "server = HTTPServer(('127.0.0.1', 0), ReasonHandler)\n"
            "port = server.server_address[1]\n"
            "t = threading.Thread(target=server.serve_forever, daemon=True)\n"
            "t.start()\n"
            "conn = HTTPConnection('127.0.0.1', port, timeout=10)\n"
            "conn.request('POST', '/reason', body=b'{}', "
            "headers={'Content-Type': 'application/json'})\n"
            "resp = conn.getresponse()\n"
            "data = json.loads(resp.read().decode())\n"
            "print(resp.status)\n"
            "print(sorted(s['substitutions']['who'] for s in data['solutions']))\n"
            "server.shutdown()\n"
        )
        proc = _run(str(preload_file), code)
        assert proc.returncode == 0, proc.stderr
        assert "200" in proc.stdout
        assert "['plato', 'socrates']" in proc.stdout

    def test_all_tools_fall_back_to_preload(self, preload_file: Path):
        code = (
            "import euclid_mcp.server as s\n"
            "r = s.reason()\n"
            "print('reason', len(r.solutions), r.error)\n"
            "d = s.diagnose(query='mortal(plato)')\n"
            "print('diagnose', d.holds)\n"
            "w = s.what_if(modifications='+ human(aristotle)', query='mortal($who)')\n"
            "print('what_if', w.after_count, w.before_count)\n"
            "c = s.check_kb()\n"
            "print('check_kb', c.valid, c.facts_count)\n"
            "e = s.explain()\n"
            "print('explain', len(e.explanations), e.error)\n"
        )
        proc = _run(str(preload_file), code)
        assert proc.returncode == 0, proc.stderr
        assert "reason 2 None" in proc.stdout
        assert "diagnose True" in proc.stdout
        assert "what_if 3 2" in proc.stdout
        assert "check_kb True 2" in proc.stdout
        assert "explain 2 None" in proc.stdout

    def test_reason_content_hash_matches_preload_file(self, preload_file: Path):
        expected = hashlib.sha256(PRELOAD_KB.encode("utf-8")).hexdigest()
        code = (
            "import euclid_mcp.server as s\n"
            "r = s.reason()\n"
            f"print(r.content_hash == '{expected}')\n"
            "c = s.check_kb()\n"
            f"print(c.content_hash == '{expected}')\n"
            "print(s.reason().version is None)\n"
        )
        proc = _run(str(preload_file), code)
        assert proc.returncode == 0, proc.stderr
        assert "True\nTrue\nTrue" in proc.stdout


class TestNoKnowledgeProvided:
    def test_reason(self):
        r = reason()
        assert r.error is not None
        assert "No knowledge provided" in r.error
        assert "EUCLID_KB_PATH" in r.error

    def test_explain(self):
        r = explain()
        assert r.error is not None
        assert "No knowledge provided" in r.error

    def test_diagnose(self):
        r = diagnose(query="human(socrates)")
        assert r.error is not None
        assert "No knowledge provided" in r.error

    def test_what_if(self):
        r = what_if(modifications="+ human(plato)", query="human($who)")
        assert r.error is not None
        assert "No base knowledge provided" in r.error

    def test_check_kb(self):
        r = check_kb()
        assert r.valid is False
        assert r.error is not None
        assert "No knowledge provided" in r.error
        assert any(e.type == "no_knowledge" for e in r.errors)

    def test_explicit_empty_string_falls_back_to_no_kb(self):
        r = reason(knowledge="")
        assert r.error is not None
        assert "No knowledge provided" in r.error


class TestSchemaOptional:
    def test_reason_knowledge_not_required(self):
        async def run():
            async with Client(mcp) as client:
                tools = await client.list_tools()
                return {t.name: t.input_schema for t in tools.tools}

        import asyncio
        schemas = asyncio.run(run())
        assert "knowledge" not in schemas["reason"].get("required", [])
        assert "knowledge" not in schemas["explain"].get("required", [])
        assert "knowledge" not in schemas["diagnose"].get("required", [])
        assert "knowledge" not in schemas["check_kb"].get("required", [])
        assert "base_knowledge" not in schemas["what_if"].get("required", [])
        for name in ("reason", "explain", "diagnose", "check_kb"):
            assert "null" in [
                t.get("type") for t in schemas[name]["properties"]["knowledge"]["anyOf"]
            ]
