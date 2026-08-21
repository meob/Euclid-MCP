#!/usr/bin/env python3
"""
Certainty Factors — Example 11
A miniature MYCIN-style diagnostic engine in pure Euclid-IR.

Each finding carries a certainty factor; a diagnosis scores
rule_CF x min(CF of its findings). The engine derives every score by
pure deduction with exact arithmetic — no sampling, no drift.

Usage:
    python3 certainty_factors.py            # full ranking
    python3 certainty_factors.py --disease flu
"""
import argparse
import logging
from pathlib import Path

from euclid_mcp.server import reason

KB_FILE = Path(__file__).parent / "certainty_factors.euclid"

# Expected scores: rule_CF x min(findings), all dyadic-exact.
EXPECTED = {
    "flu": 0.25,       # 0.5   * min(0.75, 0.5)
    "covid": 0.0625,   # 0.5   * min(0.75, 0.5, 0.125)
    "cold": 0.03125,   # 0.125 * min(0.5, 0.25)
}


class C:
    """ANSI color codes."""

    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"
    CYAN = "\033[36m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"


def print_banner():
    print(f"{C.BOLD}{C.CYAN}╔══════════════════════════════════════╗{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}║   CERTAINTY FACTORS IN EUCLID-IR     ║{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}╚══════════════════════════════════════╝{C.RESET}")
    print()
    print("  MYCIN-style scoring: diagnosis = rule_CF x min(findings).")
    print("  Uncertainty lives in the data; the engine stays exact.")


def _as_float(value) -> float:
    return float(str(value))


def run(all_diseases: bool) -> bool:
    query = "? score($disease, $cf)"
    res = reason(knowledge=KB_FILE.read_text() + "\n" + query,
                 max_solutions=10)

    if res.error:
        print(f"  {C.YELLOW}engine error: {res.error}{C.RESET}")
        return False

    rows = []
    for s in res.solutions:
        subs = s.substitutions
        disease = str(subs["disease"])
        cf = _as_float(subs["cf"])
        if all_diseases or disease in EXPECTED:
            rows.append((disease, cf))

    rows.sort(key=lambda r: r[1], reverse=True)

    print(f"\n{C.BOLD}Diagnosis ranking (score = rule_CF x min CF):{C.RESET}")
    ok = True
    for rank, (disease, cf) in enumerate(rows, 1):
        expected = EXPECTED.get(disease)
        match = expected is not None and abs(cf - expected) < 1e-12
        ok = ok and (match or expected is None)
        mark = f"{C.GREEN}OK{C.RESET}" if match else f"{C.YELLOW}?? {C.RESET}"
        exp = f"(expected {expected})" if expected is not None else "(not modeled)"
        print(f"  {rank}. {disease:<8} cf={cf:<9g} {mark} {exp}")

    modeled = [d for d, _ in rows if d in EXPECTED]
    passed = sum(
        1 for d, cf in rows if d in EXPECTED and abs(cf - EXPECTED[d]) < 1e-12
    )
    print(f"\n{C.BOLD}{passed}/{len(modeled)} modeled diseases scored exactly."
          f"{C.RESET}")
    return ok and passed == len(modeled)


def main():
    parser = argparse.ArgumentParser(description="Certainty factors demo")
    parser.add_argument("--disease", help="show a single disease's score")
    args = parser.parse_args()

    logging.getLogger("euclid_mcp").setLevel(logging.CRITICAL)
    print_banner()
    raise SystemExit(0 if run(args.disease is None) else 1)


if __name__ == "__main__":
    main()
