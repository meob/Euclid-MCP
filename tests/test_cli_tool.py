"""Tests for the euclid-cli command-line interface (euclid_mcp/cli.py)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

import euclid_mcp.cli as cli

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KB = "human(socrates)\nmortal($x) IF human($x)\n? mortal($who)"
BASE = "human(socrates)\nmortal($x) IF human($x)"
RULE_ID_KB = "human(socrates)\nmortal($x) IF human($x)  # RULE: BIO-001\n? mortal($who)"


def _write_kb(tmp_path: Path, text: str = KB) -> Path:
    path = tmp_path / "kb.euclid"
    path.write_text(text, encoding="utf-8")
    return path


class TestCliInProcess:
    """In-process tests for coverage (same pattern as test_cli.py)."""

    def _invoke(self, monkeypatch, capsys, args, expect_code=0):
        monkeypatch.setattr(sys, "argv", ["euclid-cli", *args])
        code = cli.main()
        out, err = capsys.readouterr()
        assert code == expect_code, f"exit={code} stderr={err}"
        return out, err

    def test_check_valid(self, monkeypatch, capsys):
        out, _ = self._invoke(monkeypatch, capsys, ["check", "--knowledge", KB])
        assert "KB valid: True" in out
        assert "Facts: 1" in out

    def test_check_invalid_exit_code(self, monkeypatch, capsys):
        out, _ = self._invoke(
            monkeypatch,
            capsys,
            ["check", "--knowledge", "human(a) IF human(a)"],
            expect_code=1,
        )
        assert "KB valid: False" in out

    def test_reason_substitutions_and_proof(self, monkeypatch, capsys):
        out, _ = self._invoke(monkeypatch, capsys, ["reason", "--knowledge", RULE_ID_KB])
        assert "who: socrates" in out
        assert "mortal(socrates)  [rule (BIO-001)]" in out
        assert "human(socrates)  [fact]" in out

    def test_reason_explicit_query(self, monkeypatch, capsys):
        out, _ = self._invoke(
            monkeypatch,
            capsys,
            ["reason", "--knowledge", BASE, "--query", "mortal($who)"],
        )
        assert "who: socrates" in out

    def test_reason_json(self, monkeypatch, capsys):
        import json

        out, _ = self._invoke(monkeypatch, capsys, ["reason", "--knowledge", KB, "--json"])
        data = json.loads(out)
        assert data["solutions"][0]["substitutions"]["who"] == "socrates"

    def test_reason_no_knowledge(self, monkeypatch, capsys):
        monkeypatch.setenv("EUCLID_KB_PATH", "")
        _, err = self._invoke(monkeypatch, capsys, ["reason"], expect_code=1)
        assert "No knowledge provided" in err

    def test_explain_steps(self, monkeypatch, capsys):
        out, _ = self._invoke(monkeypatch, capsys, ["explain", "--knowledge", KB])
        assert "human(socrates) is asserted as a fact" in out

    def test_diagnose_why_not(self, monkeypatch, capsys):
        out, _ = self._invoke(
            monkeypatch,
            capsys,
            [
                "diagnose",
                "--knowledge", BASE,
                "--query", "mortal(plato)",
                "--mode", "why_not",
            ],
        )
        assert "does NOT hold" in out

    def test_what_if(self, monkeypatch, capsys):
        out, _ = self._invoke(
            monkeypatch,
            capsys,
            [
                "what-if",
                "--knowledge", BASE,
                "--modifications", "+ human(plato)",
                "--query", "mortal($who)",
            ],
        )
        assert "1 -> 2" in out
        assert "more" in out

    def test_what_if_missing_modifications_usage_error(self, monkeypatch, capsys):
        monkeypatch.setattr(
            sys, "argv", ["euclid-cli", "what-if", "--knowledge", BASE, "--query", "mortal($who)"]
        )
        with pytest.raises(SystemExit) as exc:
            cli.main()
        assert exc.value.code == 2

    def test_diagnose_missing_query_usage_error(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["euclid-cli", "diagnose", "--knowledge", KB])
        with pytest.raises(SystemExit) as exc:
            cli.main()
        assert exc.value.code == 2

    def test_backend_flag(self, monkeypatch, capsys, tmp_path):
        _write_kb(tmp_path)
        self._invoke(
            monkeypatch,
            capsys,
            ["--backend", "native", "reason", "-f", str(tmp_path / "kb.euclid")],
        )
        assert os.environ.get("EUCLID_BACKEND") == "native"

    def test_file_loading(self, monkeypatch, capsys, tmp_path):
        path = _write_kb(tmp_path)
        out, _ = self._invoke(monkeypatch, capsys, ["reason", "-f", str(path)])
        assert "who: socrates" in out

    def test_missing_file_usage_error(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            sys, "argv", ["euclid-cli", "reason", "-f", str(tmp_path / "nope.euclid")]
        )
        with pytest.raises(SystemExit) as exc:
            cli.main()
        assert exc.value.code == 2


class TestCliSubprocess:
    """End-to-end tests through the real entry point."""

    def _run(self, args, env_extra=None):
        env = dict(os.environ)
        if env_extra:
            env.update(env_extra)
        proc = subprocess.run(
            [sys.executable, "-m", "euclid_mcp.cli", *args],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            env=env,
        )
        return proc

    def test_reason_end_to_end(self, tmp_path):
        path = _write_kb(tmp_path)
        proc = self._run(["reason", "-f", str(path)])
        assert proc.returncode == 0, proc.stderr
        assert "who: socrates" in proc.stdout

    def test_reason_native_backend(self, tmp_path):
        path = _write_kb(tmp_path)
        proc = self._run(
            ["--backend", "native", "reason", "-f", str(path)],
            env_extra={"EUCLID_BACKEND": "native"},
        )
        assert proc.returncode == 0, proc.stderr
        assert "who: socrates" in proc.stdout

    def test_check_invalid_exit_code(self):
        proc = self._run(["check", "--knowledge", "human(a) IF human(a)"])
        assert proc.returncode == 1
        assert "KB valid: False" in proc.stdout

    def test_embedded_query_no_flag(self, tmp_path):
        path = _write_kb(tmp_path)
        proc = self._run(["reason", "-f", str(path)])
        assert proc.returncode == 0, proc.stderr
        assert "who: socrates" in proc.stdout

    def test_json_output(self, tmp_path):
        import json

        path = _write_kb(tmp_path)
        proc = self._run(["reason", "-f", str(path), "--json"])
        assert proc.returncode == 0, proc.stderr
        data = json.loads(proc.stdout)
        assert data["solutions"][0]["substitutions"]["who"] == "socrates"
