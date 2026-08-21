#!/usr/bin/env python3
"""
Turing Machine — Example 09
A binary-increment Turing machine written entirely in Euclid-IR
(no cut, no lists): proof that the language is Turing-complete.

The runner feeds initial tapes to the engine, which executes the machine
by pure deduction (`final/2` reachability) and returns the halting config.

Usage:
    python3 tm_machine.py                # run all demos
    python3 tm_machine.py --bits 1011    # run one input
"""
import argparse
import logging
from pathlib import Path

from euclid_mcp.server import reason

MACHINE_FILE = Path(__file__).parent / "turing_machine.euclid"

# Depth headroom: each TM step costs ~3 proof levels; default 30 is enough
# for these demos but we pass an explicit limit to stay honest about it.
MAX_DEPTH = 60


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
    print(f"{C.BOLD}{C.CYAN}║   TURING MACHINE IN EUCLID-IR        ║{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}╚══════════════════════════════════════╝{C.RESET}")
    print()
    print("  A binary incrementer with no cut and no lists:")
    print("  the tape is two stacks of nested compound terms")
    print("  and execution is pure deduction (reachability).")


# ── initial config construction ──────────────────────────────────────────────


def _stack(symbols: list[str]) -> str:
    """Build 'cell(s1, cell(s2, ... blank))' — s1 is nearest the head."""
    out = "blank"
    for sym in reversed(symbols):
        out = f"cell({sym}, {out})"
    return out


def initial_config(bits: str) -> str:
    """Initial tape(...) for a binary string with the head on the LSB."""
    left = [bits[i] for i in range(len(bits) - 2, -1, -1)]  # nearest-first
    return (
        "tape("
        f"{_stack(left + ['blank'])}, "     # left neighbours + blank padding
        f"{_stack([bits[-1], 'blank'])})"   # LSB under the head + spare blank
    )


# ── result rendering ─────────────────────────────────────────────────────────


def _parse_term(text: str):
    """Tiny parser for rendered Prolog terms: atom | number | compound."""
    text = text.strip()

    def parse(i: int):
        if text[i] in "\"'":
            j = text.index(text[i], i + 1)
            return text[i : j + 1], j + 1
        if text[i] == "-":
            val, j = _parse_number(i)
            return val, j
        m_end = i
        while m_end < len(text) and (text[m_end].isalnum() or text[m_end] == "_"):
            m_end += 1
        name = text[i:m_end]
        if m_end < len(text) and text[m_end] == "(":
            args, j = [], m_end + 1
            while True:
                arg, j = parse(j)
                args.append(arg)
                if text[j] == ",":
                    j += 1
                    while j < len(text) and text[j] == " ":
                        j += 1
                    continue
                return (name, tuple(args)), j + 1  # skip ")"
        try:
            return int(name), m_end
        except ValueError:
            return name, m_end

    def _parse_number(i: int):
        j = i + 1
        while j < len(text) and text[j].isdigit():
            j += 1
        return int(text[i:j]), j

    term, _ = parse(0)
    return term


def decode_config(term) -> tuple[str, list[str]]:
    """Decode cfg(state, tape(left, right)) into (state, tape_symbols).

    Returns the flat tape as [left..., HEAD, right...] with '_' for blanks;
    the head position always sits at index len(left).
    """
    (_, (state, (_, (lft, rgt)))) = term
    def unwind(stack):
        cells = []
        # parser representation: ("cell", (symbol, rest)); blank terminates
        while isinstance(stack, tuple) and stack[0] == "cell":
            (_name, (head, rest)) = stack
            cells.append("_" if head == "blank" else str(head))
            stack = rest
        if stack != "blank":
            raise ValueError(f"unexpected stack terminator: {stack!r}")
        return cells
    left, right = unwind(lft), unwind(rgt)
    # left is nearest-first: far ... near | head-side right is head-first
    tape = list(reversed(left)) + ["|"] + right
    return str(state), tape


def render(state: str, tape: list[str]) -> str:
    body = " ".join(tape)
    return f"[{body}]  state={state}"


# ── demo ─────────────────────────────────────────────────────────────────────


def run_input(bits: str) -> bool:
    expected = bin(int(bits, 2) + 1)[2:]
    query = f"? final(cfg(run, {initial_config(bits)}), $end)"
    res = reason(knowledge=MACHINE_FILE.read_text() + "\n" + query,
                 max_solutions=5, max_depth=MAX_DEPTH)

    print(f"\n{C.BOLD}Input: {bits} ({int(bits, 2)})   expected: "
          f"{expected} ({int(expected, 2)}){C.RESET}")

    if res.error:
        print(f"  {C.YELLOW}engine error: {res.error}{C.RESET}")
        return False
    if not res.solutions:
        print(f"  {C.YELLOW}no derivation found (machine did not halt){C.RESET}")
        return False

    end_term = _parse_term(str(res.solutions[0].substitutions["end"]))
    state, tape = decode_config(end_term)
    got = "".join(c for c in tape if c not in "_|").lstrip("0") or "0"
    ok = got == expected
    color = C.GREEN if ok else C.YELLOW
    print(f"  halted config: {color}{render(state, tape)}{C.RESET}")
    print(f"  result: {'OK' if ok else 'MISMATCH'} "
          f"(proof depth budget {MAX_DEPTH})")
    return ok


def main():
    parser = argparse.ArgumentParser(description="Turing machine demo")
    parser.add_argument("--bits", help="single binary input to increment")
    args = parser.parse_args()

    logging.getLogger("euclid_mcp").setLevel(logging.CRITICAL)
    print_banner()
    inputs = [args.bits] if args.bits else ["1011", "111", "100", "0"]
    results = [run_input(b) for b in inputs]
    passed = sum(results)
    print(f"\n{C.BOLD}{passed}/{len(results)} inputs incremented correctly."
          f"{C.RESET}")
    raise SystemExit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
