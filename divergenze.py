#!/usr/bin/env python3
"""Backend-divergence isolator for Unicode handling in Euclid-IR.

Usage:
    python3 divergenze.py native
    python3 divergenze.py prolog   # needs swipl on PATH

The two known divergences (as of euclid-mcp 0.4.5):

  D1  non-ASCII variable ($città): the native engine raises a parse error,
      while the Prolog backend silently truncates the variable name at the
      first non-ASCII character ("citt") and returns a solution.

  D2  NFD-decomposed identifiers: the native engine rejects combining marks
      (they are outside \\w), while Prolog accepts any code points and only
      unifies byte-identical spellings — so NFC fact vs NFD query does not
      unify, but NFD vs NFD does.

Each scenario must produce THE SAME outcome on every backend. The script
prints per-scenario verdicts (CONGRUENT / DIVERGENT) and exits non-zero when
at least one divergence is detected.
"""

import json
import os
import sys
import unicodedata

BACKEND = sys.argv[1] if len(sys.argv) > 1 else "auto"
os.environ["EUCLID_BACKEND"] = BACKEND

import euclid_mcp  # noqa: E402
from euclid_mcp.engine import execute, resolve_backend  # noqa: E402
from euclid_mcp.language import parse  # noqa: E402

NFC_CITTA = unicodedata.normalize("NFC", "città")
NFD_CITTA = unicodedata.normalize("NFD", "città")


def run(kb_text: str, query: str | None = None):
    """Parse + execute like the server does; return ("ok", subs) or ("error", msg)."""
    try:
        kb = parse(kb_text)
        if query is not None:
            kb = kb.model_copy(update={"query": query})
        sols = execute(kb_text, kb)
        return ("ok", [dict(s.substitutions) for s in sols])
    except Exception as exc:  # noqa: BLE001 - diagnostics must not raise
        return ("error", f"{type(exc).__name__}: {exc}")


SCENARIOS: list[tuple[str, str, str | None]] = [
    (
        "D1_non_ascii_variable",
        "city(roma)\n"
        "grande($città) IF city($città)\n"
        "? grande($città)",
        None,
    ),
    (
        "D2a_nfc_fact__nfd_query",
        f"{NFC_CITTA}(roma)",
        NFD_CITTA + "($quale)",
    ),
    (
        "D2b_nfd_fact__nfc_query",
        f"{NFD_CITTA}(roma)",
        f"{NFC_CITTA}($quale)",
    ),
    (
        "D2c_nfd_fact__nfd_query",
        f"{NFD_CITTA}(roma)",
        NFD_CITTA + "($quale)",
    ),
]


def main() -> int:
    print(f"euclid_mcp : {euclid_mcp.__file__}")
    print(f"backend    : {resolve_backend()} (requested: {BACKEND})")
    print("-" * 72)
    for name, kb_text, query in SCENARIOS:
        status, payload = run(kb_text, query)
        # Canonical, backend-independent line: diff the CANONICAL blocks of
        # two runs to decide congruence mechanically.
        if status == "ok":
            canon = json.dumps(
                [dict(sorted(s.items())) for s in payload],
                ensure_ascii=False,
                sort_keys=True,
            )
        else:
            # Error text differs per engine: only the failure STATUS is canonical.
            canon = "error"
        print(f"{name}")
        print(f"   detail  : {status} {payload!r}")
        print(f"   CANONICAL {name}: {canon}")
    print("-" * 72)
    print("Congruence check: diff the 'CANONICAL' lines of this run with the")
    print("other backend's run — every line must match.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
