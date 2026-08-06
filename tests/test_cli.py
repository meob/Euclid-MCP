"""Integration tests for the CLI wrapper (integrations/euclid_cli.py)."""

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLI = PROJECT_ROOT / "integrations" / "euclid_cli.py"

KB = "human(socrates)\nmortal($x) IF human($x)\n? mortal($who)"


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
