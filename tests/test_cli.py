"""Integration tests for the CLI wrapper (integrations/euclid_cli.py)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

import integrations.euclid_cli as cli

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLI = PROJECT_ROOT / "integrations" / "euclid_cli.py"

KB = "human(socrates)\nmortal($x) IF human($x)\n? mortal($who)"


class _FakeStdin:
    def __init__(self, text: str):
        self._text = text

    def read(self):
        return self._text


def _run(args: list[str], stdin: str | None = None) -> dict:
    cmd = [sys.executable, str(CLI), *args]
    proc = subprocess.run(
        cmd,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, f"CLI failed: {proc.stderr}"
    return json.loads(proc.stdout)


class TestCli:
    def test_inline_json(self):
        out = _run([json.dumps({"knowledge": KB})])
        assert len(out["solutions"]) == 1
        assert out["solutions"][0]["substitutions"]["who"] == "socrates"

    def test_stdin(self):
        out = _run([], stdin=json.dumps({"knowledge": KB}))
        assert len(out["solutions"]) == 1

    def test_flag_arguments(self):
        out = _run(["--knowledge", "red(apple)", "--query", "red($x)"])
        assert len(out["solutions"]) == 1
        assert out["solutions"][0]["substitutions"]["x"] == "apple"

    def test_reason_tool(self):
        out = _run(["--tool", "reason", "--knowledge", KB])
        assert out["solutions"][0]["substitutions"]["who"] == "socrates"

    def test_diagnose_tool(self):
        out = _run(
            [
                "--tool", "diagnose",
                "--knowledge", "human(socrates)\nmortal($x) IF human($x)",
                "--query", "mortal(plato)",
                "--mode", "why_not",
            ]
        )
        assert out["holds"] is False
        assert out["conclusion"]

    def test_what_if_tool(self):
        base = "human(socrates)\nmortal($x) IF human($x)"
        out = _run(
            [
                "--tool", "what-if",
                "--knowledge", base,
                "--modifications", "+ human(plato)",
                "--query", "mortal($who)",
            ]
        )
        assert out["after_count"] == 2
        assert out["before_count"] == 1
        assert out["delta"] == "more"

    def test_check_kb_tool(self):
        out = _run(["--tool", "check-kb", "--knowledge", KB])
        assert out["valid"] is True
        assert out["facts_count"] == 1
        assert out["rules_count"] == 1

    def test_unknown_tool(self):
        proc = subprocess.run(
            [sys.executable, str(CLI), "--tool", "bogus", "--knowledge", KB],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert proc.returncode == 0
        out = json.loads(proc.stdout)
        assert "Unknown tool" in out["error"]


class TestCliInProcess:
    """Coverage-focused in-process tests.

    The subprocess tests above exercise the real wrapper end-to-end but do not
    count toward pytest-cov (coverage does not follow into child processes).
    Calling main()/_parse_args() in-process is what lifts the CLI module's
    own lines into the measured set.
    """

    def _invoke(self, monkeypatch, capsys, argv, stdin_text=None) -> dict:
        monkeypatch.setattr(sys, "argv", argv)
        # cli.main() writes EUCLID_BACKEND to the process env; isolate it so
        # in-process runs cannot leak a backend selection into later tests.
        monkeypatch.delenv("EUCLID_BACKEND", raising=False)
        if stdin_text is not None:
            monkeypatch.setattr(sys, "stdin", _FakeStdin(stdin_text))
        cli.main()
        return json.loads(capsys.readouterr().out)

    def test_inline_json(self, monkeypatch, capsys):
        out = self._invoke(monkeypatch, capsys, ["cli", json.dumps({"knowledge": KB})])
        assert out["solutions"][0]["substitutions"]["who"] == "socrates"

    def test_stdin(self, monkeypatch, capsys):
        out = self._invoke(
            monkeypatch, capsys, ["cli"], stdin_text=json.dumps({"knowledge": KB})
        )
        assert len(out["solutions"]) == 1

    def test_flag_arguments(self, monkeypatch, capsys):
        out = self._invoke(
            monkeypatch, capsys, ["cli", "--knowledge", "red(apple)", "--query", "red($x)"]
        )
        assert out["solutions"][0]["substitutions"]["x"] == "apple"

    def test_flag_knowledge_without_query(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["cli", "--knowledge", KB])
        assert cli._parse_args() == {"knowledge": KB, "query": None}

    def test_tool_reason(self, monkeypatch, capsys):
        out = self._invoke(monkeypatch, capsys, ["cli", "--tool", "reason", "--knowledge", KB])
        assert out["solutions"][0]["substitutions"]["who"] == "socrates"
        assert "elapsed_ms" in out

    def test_tool_diagnose(self, monkeypatch, capsys):
        knowledge = "human(socrates)\nmortal($x) IF human($x)"
        out = self._invoke(
            monkeypatch,
            capsys,
            [
                "cli", "--tool", "diagnose",
                "--knowledge", knowledge,
                "--query", "mortal(plato)",
                "--mode", "why_not",
            ],
        )
        assert out["holds"] is False
        assert out["conclusion"]

    def test_tool_what_if(self, monkeypatch, capsys):
        base = "human(socrates)\nmortal($x) IF human($x)"
        out = self._invoke(
            monkeypatch,
            capsys,
            [
                "cli", "--tool", "what-if",
                "--knowledge", base,
                "--modifications", "+ human(plato)",
                "--query", "mortal($who)",
            ],
        )
        assert out["after_count"] == 2
        assert out["before_count"] == 1
        assert out["delta"] == "more"

    def test_tool_check_kb(self, monkeypatch, capsys):
        out = self._invoke(monkeypatch, capsys, ["cli", "--tool", "check-kb", "--knowledge", KB])
        assert out["valid"] is True
        assert out["facts_count"] == 1
        assert out["rules_count"] == 1

    def test_unknown_tool(self, monkeypatch, capsys):
        out = self._invoke(monkeypatch, capsys, ["cli", "--tool", "bogus", "--knowledge", KB])
        assert "Unknown tool" in out["error"]

    def test_parse_args_max_solutions_depth(self, monkeypatch):
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli", "--tool", "reason",
                "--knowledge", KB,
                "--max-solutions", "3",
                "--max-depth", "10",
            ],
        )
        data = cli._parse_args()
        assert data["max_solutions"] == 3
        assert data["max_depth"] == 10

    def test_parse_args_skips_unknown_flags(self, monkeypatch):
        monkeypatch.setattr(
            sys,
            "argv",
            ["cli", "--tool", "reason", "--bogus", "x", "--knowledge", KB],
        )
        data = cli._parse_args()
        assert data == {"_tool": "reason", "knowledge": KB}

    def test_parse_args_flag_without_value(self, monkeypatch):
        # a trailing --knowledge with no value must not raise
        monkeypatch.setattr(sys, "argv", ["cli", "--tool", "reason", "--knowledge"])
        data = cli._parse_args()
        assert data == {"_tool": "reason"}

    def test_invalid_json_raises(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["cli", "{not json"])
        with pytest.raises(json.JSONDecodeError):
            cli._parse_args()
