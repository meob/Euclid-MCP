"""High-level Python API for the persistent SWI-Prolog engine.

Translates a knowledge base into a ``load`` + ``query`` exchange with a
single persistent engine process (see :mod:`euclid_mcp.prolog_server`),
instead of spawning a fresh ``swipl`` subprocess per call.
"""

import logging
import re
import threading
from typing import Any

from .models import ProofNode, Solution
from .prolog_server import PrologServer
from .translator import build_query_snippet

logger = logging.getLogger(__name__)

# Pattern to remove temp file paths from error messages
_TEMP_PATH_PATTERN = re.compile(r"/[^\s:]+\.pl:\d+:?\s*")

_default_server: PrologServer | None = None
_server_lock = threading.Lock()


def _sanitize_error(msg: str) -> str:
    """Remove internal file paths from Prolog error messages."""
    return _TEMP_PATH_PATTERN.sub("<input>: ", msg).strip()


def _get_server() -> PrologServer:
    """Return the process-wide engine, launching it on first use."""
    global _default_server
    with _server_lock:
        if _default_server is None:
            _default_server = PrologServer()
        return _default_server


def close() -> None:
    """Terminate the persistent engine, if one was launched.

    Used by the HTTP API's graceful-shutdown path so no ``swipl`` process is
    orphaned when the container/process receives SIGTERM or SIGINT.
    """
    global _default_server
    with _server_lock:
        server, _default_server = _default_server, None
    if server is not None:
        server.close()


def health_info() -> dict | None:
    """Live engine snapshot for deep health checks.

    The engine is launched lazily on first use, so a cold process has no
    engine to probe yet — that is healthy, not degraded: the next request
    starts one. Returns a dict with ``reachable: False`` only when an engine
    process exists but does not answer a ping (wedged/dropped; ``PrologServer``
    then discards it and the next request relaunches from a clean state). The
    native backend has no ``swipl`` process at all and is handled by the
    caller without consulting this function.

    The dict carries the workspace ``facts``/``rules`` counts and the
    Python-side ``requests_since_restart`` for the current engine process.
    """
    with _server_lock:
        server = _default_server
    if server is None:
        return {
            "backend": "prolog",
            "reachable": True,
            "facts": None,
            "rules": None,
            "requests_since_restart": 0,
        }
    try:
        server.ping(timeout=5)
    except (RuntimeError, OSError):
        return {"backend": "prolog", "reachable": False}
    info: dict[str, Any] = {
        "backend": "prolog",
        "reachable": True,
        "requests_since_restart": server.requests_since_restart,
    }
    try:
        stats = server.stats(timeout=5)
        info["facts"] = stats.get("facts")
        info["rules"] = stats.get("rules")
    except (RuntimeError, OSError):
        pass
    return info


def execute(
    decls: list[str],
    clauses: list[str],
    query: str | None,
    max_depth: int = 30,
    max_solutions: int = 1000,
    timeout: int = 30,
    kb_hash: str | None = None,
) -> list[Solution]:
    """Load a knowledge base into the persistent engine and run a query.

    Args:
        decls: Predicate signatures to declare dynamic (user + engine helpers).
        clauses: Fact/rule clause texts plus the meta-interpreter and the
            proof-tree serializer (see ``translator.kb_to_decls_clauses``).
        query: Euclid-IR query body (``$vars``) to evaluate.
        max_depth: Maximum proof tree depth for the meta-interpreter.
        max_solutions: Upper bound on returned solutions.
        timeout: Seconds allowed for load and query.
        kb_hash: Fingerprint of the KB source. When it matches the engine's
            currently-loaded workspace the load is skipped and only the query
            runs (see ``prolog_server.PrologServer.load``).

    Returns:
        Solutions (variable substitutions + proof trees). Empty when the
        query has no answers.
    """
    if not query:
        return []

    server = _get_server()
    snippet = build_query_snippet(
        query, max_depth=max_depth, max_solutions=max_solutions
    )
    response = server.load_and_query(
        decls, clauses, snippet, timeout=timeout, kb_hash=kb_hash
    )

    solutions: list[Solution] = []
    for item in response.get("solutions") or []:
        if not isinstance(item, dict):
            continue
        try:
            proof = _parse_proof(item.get("proof") or {})
            subs: dict[str, Any] = item.get("solution") or {}
            solutions.append(Solution(substitutions=subs, proof=proof))
        except Exception:
            continue
    return solutions[:max_solutions]


def _parse_proof(d: dict[str, Any]) -> ProofNode:
    t = d.get("type", "true")
    node = ProofNode(type=t)
    if t == "fact":
        node.goal = d.get("goal")
    elif t == "rule":
        node.goal = d.get("goal")
        node.body = d.get("body")
        node.rule_id = d.get("rule_id")
        if "subproof" in d and isinstance(d["subproof"], dict):
            node.subproof = _parse_proof(d["subproof"])
    elif t == "and":
        if "left" in d and isinstance(d["left"], dict):
            node.left = _parse_proof(d["left"])
        if "right" in d and isinstance(d["right"], dict):
            node.right = _parse_proof(d["right"])
    elif t == "neg":
        node.goal = d.get("goal")
    return node
