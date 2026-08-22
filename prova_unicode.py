#!/usr/bin/env python3
"""Unicode conformance suite for Euclid-IR, one inference backend at a time.

Usage:
    EUCLID_BACKEND=native python3 prova_unicode.py native
    EUCLID_BACKEND=prolog python3 prova_unicode.py prolog   # needs swipl on PATH

Every case states the outcome that BOTH backends must produce. A case passes
when the engine returns the expected solutions (variable bindings); it fails
on a parse/engine error or on any binding mismatch. Run it against both
backends: the union of outputs must show all PASS for Unicode support to be
considered congruent.
"""

import os
import sys
import unicodedata

BACKEND = sys.argv[1] if len(sys.argv) > 1 else "auto"
os.environ["EUCLID_BACKEND"] = BACKEND

import euclid_mcp  # noqa: E402
from euclid_mcp.engine import execute, resolve_backend  # noqa: E402
from euclid_mcp.language import parse  # noqa: E402

NFD = unicodedata.normalize("NFD", "città")  # c i t t a + combining grave
NFC = unicodedata.normalize("NFC", "città")  # c i t t \u00e0


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


CASES: list[tuple[str, str, str | None, object]] = [
    # name, kb text, query override, expected ("ok", subs) or ("error", None)
    (
        "ascii_baseline",
        "parent(tom, bob)\n? parent(tom, $child)",
        None,
        ("ok", [{"child": "bob"}]),
    ),
    (
        "accented_predicate_nfc",
        "città(roma)\n? città($quale)",
        None,
        ("ok", [{"quale": "roma"}]),
    ),
    (
        "cyrillic_predicate",
        "родитель(толстой)\n? родитель($кто)",
        None,
        ("ok", [{"кто": "толстой"}]),
    ),
    (
        "cjk_predicate",
        "父(太郎, 次郎)\n? 父($x, 次郎)",
        None,
        ("ok", [{"x": "太郎"}]),
    ),
    (
        "non_ascii_variable",
        "city(roma)\n"
        "grande($città) IF city($città)\n"
        "? grande($città)",
        None,
        ("ok", [{"città": "roma"}]),
    ),
    (
        "nfc_fact_nfd_query",
        "città(roma)",  # fact spelled NFC
        NFD + "($quale)",  # query spelled NFD
        ("ok", [{"quale": "roma"}]),
    ),
    (
        "nfd_fact_nfc_query",
        f"{NFD}(roma)",  # fact spelled NFD
        "città($quale)",  # query spelled NFC
        ("ok", [{"quale": "roma"}]),
    ),
    (
        "nfd_fact_nfd_query",
        f"{NFD}(roma)",
        NFD + "($quale)",
        ("ok", [{"quale": "roma"}]),
    ),
    (
        "unicode_string_literals",
        'user("müller", "münchen")\n? user($name, $city)',
        None,
        # Quotes are IR syntax: both backends bind the bare value.
        ("ok", [{"name": "müller", "city": "münchen"}]),
    ),
]


def main() -> int:
    print(f"euclid_mcp : {euclid_mcp.__file__}")
    print(f"backend    : {resolve_backend()} (requested: {BACKEND})")
    print("-" * 72)
    failures = 0
    for name, kb_text, query, expected in CASES:
        got = run(kb_text, query)
        if expected[1] is None:  # expected error: only the status must match
            passed = got[0] == expected[0]
        else:
            passed = got == expected
        mark = "PASS" if passed else "FAIL"
        if not passed:
            failures += 1
        print(f"[{mark}] {name}")
        if not passed:
            print(f"       expected: {expected}")
            print(f"       got     : {got}")
    print("-" * 72)
    total = len(CASES)
    print(f"{total - failures}/{total} cases passed on backend '{BACKEND}'")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
