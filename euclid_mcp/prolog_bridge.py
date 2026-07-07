import json
import os
import shutil
import subprocess
import tempfile
import time

from .models import ProofNode, Solution


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


def execute(prolog_code: str, timeout: int = 30) -> list[Solution]:
    swipl = _find_swipl()

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".pl", delete=False, encoding="utf-8"
    )
    try:
        tmp.write(prolog_code)
        tmp.close()

        start = time.monotonic()
        proc = subprocess.run(
            [swipl, "-q", "-f", tmp.name, "-t", "halt"],
            capture_output=True, text=True, timeout=timeout,
        )
        _ = time.monotonic() - start

        if proc.returncode != 0 and not proc.stdout.strip():
            msg = proc.stderr.strip() or f"SWI-Prolog exit code {proc.returncode}"
            raise RuntimeError(msg)

        warnings = proc.stderr.strip()
        solutions: list[Solution] = []

        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict) or "solution" not in data or "proof" not in data:
                continue
            proof = _parse_proof(data["proof"])
            solutions.append(
                Solution(substitutions=data["solution"], proof=proof)
            )

        if warnings:
            pass

        return solutions

    except subprocess.TimeoutExpired:
        raise RuntimeError(f"SWI-Prolog timed out after {timeout}s")
    except FileNotFoundError:
        raise RuntimeError(
            "SWI-Prolog (swipl) non trovato. Installa con: brew install swi-prolog"
        )
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def _parse_proof(d: dict) -> ProofNode:
    t = d.get("type", "true")
    node = ProofNode(type=t)
    if t == "fact":
        node.goal = d.get("goal")
    elif t == "rule":
        node.goal = d.get("goal")
        node.body = d.get("body")
        if "subproof" in d and isinstance(d["subproof"], dict):
            node.subproof = _parse_proof(d["subproof"])
    elif t == "and":
        if "left" in d and isinstance(d["left"], dict):
            node.left = _parse_proof(d["left"])
        if "right" in d and isinstance(d["right"], dict):
            node.right = _parse_proof(d["right"])
    return node
