"""Persistent SWI-Prolog engine process manager.

Launches ``euclid_mcp/prolog_engine.pl`` once and talks to it over a
JSON-lines protocol on stdin/stdout: one request line in, one response
line out. Thread-safe (requests are serialized with a lock) and
self-healing (a crashed engine is relaunched on the next request).

The engine never builds knowledge itself: every ``load`` clears the
workspace and re-asserts the clauses the caller provides, so repeated
loads are idempotent. A ``load`` carrying a ``kb_hash`` that matches the
currently-loaded workspace is skipped by the engine (``skipped:true``) —
the KB persists and only the query runs.
"""

import collections
import json
import logging
import os
import select
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_ENGINE_FILE = Path(__file__).resolve().parent / "prolog_engine.pl"


def _find_swipl() -> str:
    path = shutil.which("swipl")
    if path:
        return path
    for candidate in [
        "/opt/homebrew/bin/swipl",
        "/usr/local/bin/swipl",
        "/usr/bin/swipl",
    ]:
        if os.path.isfile(candidate):
            return candidate
    return "swipl"


class PrologServer:
    """A persistent SWI-Prolog inference engine over a JSON-lines pipe."""

    def __init__(
        self,
        engine_file: str | Path | None = None,
        swipl: str | None = None,
        restart_every: int = 1000,
    ):
        self._engine_file = Path(engine_file) if engine_file else _ENGINE_FILE
        self._swipl = swipl or _find_swipl()
        self._proc: subprocess.Popen[str] | None = None
        self._err_thread: threading.Thread | None = None
        self._stderr_tail: collections.deque[str] = collections.deque(maxlen=50)
        self._lock = threading.RLock()
        # Bounded-resource policy: restart the long-lived engine after N
        # requests (and after any timeout recovery) to cap atom-table and
        # stack growth. The restart is deferred until the next `load`, so a
        # freshly-launched engine always receives its workspace (including
        # the per-load meta-interpreter, prove/3) before any query runs on
        # it. 0 disables the periodic restart.
        self._restart_every = max(0, restart_every)
        self._requests_since_restart = 0

    # ── lifecycle ────────────────────────────────────────────────────────

    def _launch(self) -> None:
        self._requests_since_restart = 0
        self._proc = subprocess.Popen(
            [
                self._swipl,
                "-q",
                "-s",
                str(self._engine_file),
                "-g",
                "main",
                "-t",
                "halt",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self._err_thread = threading.Thread(
            target=self._drain_stderr, daemon=True, name="euclid-swipl-stderr"
        )
        self._err_thread.start()

    def _drain_stderr(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        for line in proc.stderr:
            text = line.rstrip()
            self._stderr_tail.append(text)
            if text:
                logger.debug("SWI-Prolog: %s", text)

    def _alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _terminate(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                proc.kill()

    def close(self) -> None:
        with self._lock:
            self._terminate()

    def __del__(self) -> None:  # pragma: no cover - interpreter shutdown
        try:
            self.close()
        except Exception:
            pass

    # ── protocol ─────────────────────────────────────────────────────────

    def _request(self, payload: dict[str, Any], timeout: float = 30) -> dict[str, Any]:
        with self._lock:
            if (
                self._restart_every
                and self._requests_since_restart >= self._restart_every
                and payload.get("command") == "load"
            ):
                # Periodic restart to bound memory growth. Fire it only right
                # before a `load`, never after one: a freshly-launched engine
                # must receive its workspace (incl. the per-load meta-
                # interpreter, prove/3) before any query runs on it, otherwise
                # the query paired with a restarting load fails with an
                # existence error on a bare engine.
                self._terminate()
            if not self._alive():
                self._launch()
            self._requests_since_restart += 1
            line = json.dumps(payload) + "\n"
            try:
                self._write(line)
            except (BrokenPipeError, OSError):
                # Engine died between the liveness check and the write:
                # relaunch once and retry before giving up.
                self._terminate()
                self._launch()
                self._write(line)
            data = self._read_response(timeout)
            if not isinstance(data, dict):
                raise RuntimeError("Invalid response from Euclid engine")
            status = data.get("status")
            if status == "error":
                raise RuntimeError(data.get("error") or "Euclid engine error")
            if status == "timeout":
                # Drop the engine so the next request starts from a clean
                # state: the time limit fired, so state may be inconsistent.
                self._terminate()
                raise RuntimeError(f"Euclid engine timed out after {timeout}s")
            return data

    def _write(self, line: str) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise RuntimeError("Euclid engine is not running")
        proc.stdin.write(line)
        proc.stdin.flush()

    def _read_response(self, timeout: float) -> Any:
        proc = self._proc
        if proc is None or proc.stdout is None:
            raise RuntimeError("Euclid engine is not running")
        fd = proc.stdout.fileno()
        wait = timeout + 5  # backstop beyond the engine's own time limit
        try:
            ready, _, _ = select.select([fd], [], [], wait)
        except (OSError, ValueError):
            raise RuntimeError("Euclid engine terminated unexpectedly")
        if not ready:
            # The engine's time limit failed to fire; drop the engine so the
            # next request starts from a clean state.
            self._terminate()
            raise RuntimeError(f"Euclid engine timed out after {timeout}s")
        line = proc.stdout.readline()
        if line == "":
            raise RuntimeError("Euclid engine terminated unexpectedly")
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            raise RuntimeError("Invalid response from Euclid engine")

    # ── commands ─────────────────────────────────────────────────────────

    def ping(self, timeout: float = 5) -> dict[str, Any]:
        return self._request({"command": "ping"}, timeout)

    def load(
        self,
        decls: list[str],
        clauses: list[str],
        timeout: float = 30,
        kb_hash: str | None = None,
    ) -> dict[str, Any]:
        """Load a knowledge base into the engine workspace.

        When ``kb_hash`` matches the engine's currently-loaded workspace the
        load is skipped (response ``skipped: true``) and the stored facts/rules
        counts are returned, so repeated loads of the same KB only pay for the
        query. Without a hash, every load rebuilds the workspace.
        """
        payload: dict[str, Any] = {
            "command": "load",
            "decls": decls,
            "clauses": "\n".join(clauses),
        }
        if kb_hash is not None:
            payload["kb_hash"] = kb_hash
        resp = self._request(payload, timeout)
        if isinstance(resp.get("skipped"), int):
            resp["skipped"] = bool(resp["skipped"])
        return resp

    def query(self, snippet: str, timeout: float = 30) -> dict[str, Any]:
        resp = self._request(
            {"command": "query", "snippet": snippet, "timeout": timeout}, timeout
        )
        solutions = resp.get("solutions")
        if isinstance(solutions, str):
            # The engine streams the result set as a JSON array string.
            resp["solutions"] = json.loads(solutions) if solutions.strip() else []
        return resp

    def assert_clause(self, clause: str, timeout: float = 30) -> dict[str, Any]:
        return self._request({"command": "assert", "clause": clause}, timeout)

    def retract(self, clause: str, timeout: float = 30) -> dict[str, Any]:
        return self._request({"command": "retract", "clause": clause}, timeout)

    def stats(self, timeout: float = 30) -> dict[str, Any]:
        return self._request({"command": "stats"}, timeout)

    def halt(self, timeout: float = 5) -> None:
        with self._lock:
            if not self._alive():
                return
            try:
                self._write(json.dumps({"command": "halt"}) + "\n")
                self._read_response(timeout)
            except (RuntimeError, OSError):
                pass
            self._terminate()
