"""Tests for the euclid-cli command-line interface (euclid_mcp/cli.py)."""

import io
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


class _FakeStdin:
    """Non-interactive stdin for in-process REPL tests."""

    def __init__(self, text: str) -> None:
        self._io = io.StringIO(text)

    def isatty(self) -> bool:
        return False

    def readline(self) -> str:
        return self._io.readline()


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

    def test_check_prints_predicate_inventory(self, monkeypatch, capsys):
        out, _ = self._invoke(
            monkeypatch,
            capsys,
            ["check", "--knowledge",
             "can_access(a)\nuser(u1)\nallowed($x) IF can_access($x)"],
        )
        assert "- can_access/1: 1 facts, 0 rules" in out
        assert "- user/1: 1 facts, 0 rules" in out
        assert "- allowed/1: 0 facts, 1 rules" in out

    def test_check_json_includes_predicates(self, monkeypatch, capsys):
        import json

        out, _ = self._invoke(monkeypatch, capsys, ["check", "--knowledge", KB, "--json"])
        data = json.loads(out)
        assert "predicates" in data
        by_name = {p["name"]: p for p in data["predicates"]}
        assert by_name["human"]["facts"] == 1
        assert by_name["mortal"]["rules"] == 1
        assert by_name["mortal"]["arities"] == [1]

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


class TestCliRepl:
    """In-process tests for the interactive (no-subcommand) REPL mode."""

    def _run(self, monkeypatch, capsys, script, seed_args=(), expect_code=0):
        monkeypatch.setattr(sys, "stdin", _FakeStdin(script))
        monkeypatch.setattr(sys, "argv", ["euclid-cli", *seed_args])
        code = cli.main()
        out, err = capsys.readouterr()
        assert code == expect_code, f"exit={code} stderr={err}"
        return out, err

    def test_query_without_subcommand(self, monkeypatch, capsys):
        script = "human(socrates)\nmortal($x) IF human($x)\n? mortal($who)\n"
        out, _ = self._run(monkeypatch, capsys, script)
        assert "Query: mortal($who)" in out
        assert "who: socrates" in out
        assert "human(socrates)  [fact]" in out

    def test_multiline_rule(self, monkeypatch, capsys):
        script = (
            "human(socrates)\nhuman(plato)\n"
            "mortal($x) IF human($x) AND\n  greek($x)\n"
            "greek(socrates)\n? mortal($who)\n"
        )
        out, _ = self._run(monkeypatch, capsys, script)
        assert "who: socrates" in out
        assert "who: plato" not in out

    def test_query_no_solutions(self, monkeypatch, capsys):
        out, _ = self._run(monkeypatch, capsys, "human(socrates)\n? mortal($who)\n")
        assert "No solutions." in out

    def test_check_and_kb(self, monkeypatch, capsys):
        out, _ = self._run(monkeypatch, capsys, "human(socrates)\n:check\n:kb\n")
        assert "KB valid: True" in out
        assert "human(socrates)" in out

    def test_check_empty_session(self, monkeypatch, capsys):
        out, _ = self._run(monkeypatch, capsys, ":check\n")
        assert "(session KB is empty)" in out

    def test_what_if(self, monkeypatch, capsys):
        script = (
            "human(socrates)\nmortal($x) IF human($x)\n? mortal($who)\n"
            ":what-if + human(plato)\n"
        )
        out, _ = self._run(monkeypatch, capsys, script)
        assert "1 -> 2" in out

    def test_diagnose(self, monkeypatch, capsys):
        script = "human(socrates)\nmortal($x) IF human($x)\n:diagnose mortal(plato) why_not\n"
        out, _ = self._run(monkeypatch, capsys, script)
        assert "does NOT hold" in out

    def test_explain(self, monkeypatch, capsys):
        script = "human(socrates)\nmortal($x) IF human($x)\n:explain mortal($who)\n"
        out, _ = self._run(monkeypatch, capsys, script)
        assert "asserted as a fact" in out

    def test_load_file(self, monkeypatch, capsys, tmp_path):
        path = tmp_path / "seed.euclid"
        path.write_text("red(apple)\n", encoding="utf-8")
        out, _ = self._run(monkeypatch, capsys, f":load {path}\n? red($x)\n")
        assert "Loaded" in out
        assert "x: apple" in out

    def test_reset(self, monkeypatch, capsys):
        out, _ = self._run(monkeypatch, capsys, "human(socrates)\n:reset\n:kb\n")
        assert "Session KB cleared." in out
        assert "(session KB is empty)" in out

    def test_quit_stops_loop(self, monkeypatch, capsys):
        self._run(monkeypatch, capsys, "human(socrates)\n:q\nhuman(plato)\n")

    def test_syntax_error_rolled_back(self, monkeypatch, capsys):
        monkeypatch.setenv("EUCLID_KB_PATH", "")
        out, err = self._run(monkeypatch, capsys, "human(socrates\n? red($x)\n")
        assert "Error:" in err

    def test_unknown_command(self, monkeypatch, capsys):
        out, err = self._run(monkeypatch, capsys, ":bogus\n")
        assert "Unknown command" in err

    def test_seeded_from_file(self, monkeypatch, capsys, tmp_path):
        path = _write_kb(tmp_path)
        out, _ = self._run(monkeypatch, capsys, "? mortal($who)\n", seed_args=["-f", str(path)])
        assert "who: socrates" in out

    def test_seeded_from_inline_knowledge(self, monkeypatch, capsys):
        out, _ = self._run(
            monkeypatch, capsys, "? mortal($who)\n",
            seed_args=["--knowledge", BASE],
        )
        assert "who: socrates" in out


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

    def test_repl_piped_end_to_end(self):
        proc = subprocess.run(
            [sys.executable, "-m", "euclid_mcp.cli"],
            input=(
                "human(socrates)\n"
                "mortal($x) IF human($x)\n"
                "? mortal($who)\n"
                ":check\n"
                ":quit\n"
            ),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        assert "who: socrates" in proc.stdout
        assert "KB valid: True" in proc.stdout
