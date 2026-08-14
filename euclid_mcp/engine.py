"""Inference-backend dispatcher.

Selects the engine used by ``reason`` (and therefore ``explain``, ``diagnose``
and ``what_if``) via the ``EUCLID_BACKEND`` environment variable or the
``--backend`` CLI flag:

* ``auto``   - SWI-Prolog when available on PATH, otherwise the native engine.
* ``prolog`` - always the persistent SWI-Prolog engine.
* ``native`` - always the pure-Python Euclid-IR engine (small KBs only).

The dispatch point is a single function, ``execute``, so swapping or adding a
backend never touches the tool layer.
"""

from __future__ import annotations

import functools
import hashlib
import logging
import os
import shutil

from .language import parse
from .models import KB, Solution
from .prolog_bridge import execute as _prolog_execute
from .translator import kb_to_decls_clauses

logger = logging.getLogger(__name__)

BACKEND_AUTO = "auto"
BACKEND_PROLOG = "prolog"
BACKEND_NATIVE = "native"

_BACKENDS = frozenset({BACKEND_AUTO, BACKEND_PROLOG, BACKEND_NATIVE})

# Seconds allowed for a single load+query (matches the historical hardcode).
_EXECUTION_TIMEOUT = 30

_announced: set[str] = set()


def resolve_backend() -> str:
    """Return the active backend name, resolving ``auto`` against PATH."""
    setting = os.environ.get("EUCLID_BACKEND", BACKEND_AUTO).strip().lower()
    if setting not in _BACKENDS:
        raise ValueError(
            f"EUCLID_BACKEND must be one of: {', '.join(sorted(_BACKENDS))}"
        )
    if setting == BACKEND_NATIVE:
        return BACKEND_NATIVE
    if setting == BACKEND_PROLOG:
        return BACKEND_PROLOG
    return BACKEND_NATIVE if shutil.which("swipl") is None else BACKEND_PROLOG


def kb_fingerprint(kb_source: str) -> str:
    """Fingerprint of a KB source; the engine skips unchanged workspaces."""
    return hashlib.sha256(kb_source.encode("utf-8")).hexdigest()


@functools.lru_cache(maxsize=8)
def _translate_cached(
    kb_source: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Parse and translate a KB source for the Prolog backend, cached by text."""
    decls, clauses = kb_to_decls_clauses(parse(kb_source))
    return tuple(decls), tuple(clauses)


def execute(
    kb_source: str,
    kb: KB,
    max_depth: int = 30,
    max_solutions: int = 5,
    timeout: int = _EXECUTION_TIMEOUT,
) -> list[Solution]:
    """Run ``kb.query`` on the active backend; return solutions with proofs."""
    backend = resolve_backend()
    if backend == BACKEND_NATIVE:
        if "native" not in _announced:
            _announced.add("native")
            logger.warning(
                "SWI-Prolog not available; using the native Euclid-IR engine "
                "(small knowledge bases only)"
            )
        from .ir_engine import solve_kb

        return solve_kb(
            kb,
            max_depth=max_depth,
            max_solutions=max_solutions,
            timeout=timeout,
        )

    if "prolog" not in _announced:
        _announced.add("prolog")
        logger.info("using SWI-Prolog inference engine")
    decls, clauses = (list(x) for x in _translate_cached(kb_source))
    return _prolog_execute(
        decls,
        clauses,
        kb.query,
        max_depth=max_depth,
        max_solutions=max_solutions,
        timeout=timeout,
        kb_hash=kb_fingerprint(kb_source),
    )
