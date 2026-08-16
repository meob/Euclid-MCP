#!/usr/bin/env python3
"""
Cluedo Detective - Example 08
A detective agent that uses Euclid-MCP to solve Cluedo mysteries
by elimination: who (suspect), with what (weapon), where (room).

Usage:
    python3 cluedo.py                          # Run early → late → resolved
    python3 cluedo.py --scenario early         # Early game only
    python3 cluedo.py --scenario late          # Late game only
    python3 cluedo.py --scenario resolved      # Resolved game only
    python3 cluedo.py --scenario what-if       # What-if scenarios
    python3 cluedo.py --custom <file>          # Custom game state file
"""
import argparse
import logging
import re
import unicodedata
from functools import reduce
from operator import mul
from pathlib import Path

from game_states import EARLY_GAME, LATE_GAME, RESOLVED_GAME

from euclid_mcp.server import explain, reason, what_if

RULES_FILE = Path(__file__).parent / "cluedo_rules.euclid"

# The engine logs every tool call at INFO on stderr; the demo prints its own
# output, so silence the engine while it runs.
logging.getLogger("euclid_mcp").setLevel(logging.CRITICAL)

CATEGORIES = ("suspect", "weapon", "room")


class C:
    """ANSI color codes — same palette as example 10."""

    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"
    CYAN = "\033[36m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    MAGENTA = "\033[95m"


def _center_wide(text: str, width: int) -> str:
    """Center text in `width` columns, counting wide (CJK/emoji) chars as 2."""
    visible = sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)
    pad = max(0, width - visible)
    left = pad // 2
    return " " * left + text + " " * (pad - left)


def print_banner():
    """Print the detective-themed opening banner."""
    inner = 60
    text_width = inner - 4
    lines = [
        "╔" + "═" * inner + "╗",
        "║" + _center_wide("CLUEDO 🦉 DETECTIVE", inner) + "║",
        "║" + " " * inner + "║",
        "║  " + "Euclid-MCP Deduction Engine".ljust(text_width) + "  ║",
        "║  " + "Solve the case by elimination: who, with what, where.".ljust(text_width) + "  ║",
        "╚" + "═" * inner + "╝",
    ]
    print(f"{C.BOLD}{C.CYAN}" + "\n".join(lines) + f"{C.RESET}")
    print()


def print_how_to_read():
    """Explain the output format once, before the first scenario."""
    print(f"  {C.BOLD}How to read this:{C.RESET}")
    print("    The envelope hides 1 suspect + 1 weapon + 1 room.")
    print("    A card is ruled out when it is in a player's hand or was shown")
    print("    during a suggestion. The case is solved only when exactly one")
    print("    combination of suspect/weapon/room remains.")
    print()


def load_rules() -> str:
    return RULES_FILE.read_text()


def _kb(game_state: str, query: str) -> str:
    return load_rules() + "\n" + game_state + f"\n? {query}"


def _solutions(query: str, game_state: str, max_solutions: int = 50):
    return reason(
        knowledge=_kb(game_state, query),
        max_solutions=max_solutions,
        max_depth=30,
    )


def _card_facts(game_state: str) -> dict[str, dict[str, str | None]]:
    """Map every card to its elimination reason (or None if still possible).

    Returns {category: {card: reason}} where reason is e.g. "in scarlett's
    hand" / "shown by plum", derived by querying the engine (not hardcoded).
    """
    hands = {
        sol.substitutions["c"]: f"in {sol.substitutions['p']}'s hand"
        for sol in _solutions("hand($p, $c)", game_state).solutions
    }
    shown = {
        sol.substitutions["c"]: f"shown by {sol.substitutions['p']}"
        for sol in _solutions("showed($p, $c, $to)", game_state).solutions
    }

    facts: dict[str, dict[str, str | None]] = {}
    for cat in CATEGORIES:
        cards: dict[str, str | None] = {
            sol.substitutions["c"]: None
            for sol in _solutions(f"{cat}($c)", game_state).solutions
        }
        for card in cards:
            if card in hands:
                cards[card] = hands[card]
            elif card in shown:
                cards[card] = shown[card]
        facts[cat] = cards
    return facts


def _color_card(cat: str, card: str) -> str:
    color = {"suspect": C.MAGENTA, "weapon": C.RED, "room": C.CYAN}[cat]
    return f"{color}{card}{C.RESET}"


def _colorize_triple(subs) -> str:
    """Render a suspect/weapon/room triple with per-category colors."""
    suspect = subs.get("s", "?")
    weapon = subs.get("w", "?")
    room = subs.get("r", "?")
    return (
        f"{C.MAGENTA}{suspect}{C.RESET} + "
        f"{C.RED}{weapon}{C.RESET} + "
        f"{C.CYAN}{room}{C.RESET}"
    )


def print_case(name: str, game_state: str) -> None:
    """Deduce and print the case state: what is ruled out and why."""
    print(f"\n{C.BOLD}{'=' * 55}{C.RESET}")
    print(f"  {C.BOLD}{C.YELLOW}{name}{C.RESET}")
    print(f"{C.BOLD}{'=' * 55}{C.RESET}\n")

    facts = _card_facts(game_state)
    remaining = {
        cat: [card for card, reason in facts[cat].items() if reason is None]
        for cat in CATEGORIES
    }

    for cat in CATEGORIES:
        label = cat.upper() + "S"
        print(f"  {C.BOLD}{label} ({len(facts[cat])}){C.RESET}")
        if remaining[cat]:
            cards = ", ".join(_color_card(cat, c) for c in remaining[cat])
            print(f"    {C.GREEN}still possible:{C.RESET}  {cards}")
        else:
            print(f"    {C.RED}none left{C.RESET}")
        eliminated = [
            (card, reason)
            for card, reason in facts[cat].items()
            if reason is not None
        ]
        if eliminated:
            parts = ", ".join(
                f"{_color_card(cat, card)} ({reason})" for card, reason in eliminated
            )
            print(f"    {C.DIM}eliminated:{C.RESET}     {parts}")
        print()

    counts = [len(remaining[cat]) for cat in CATEGORIES]
    total = reduce(mul, counts, 1)
    breakdown = " × ".join(str(n) for n in counts)
    print(f"  {C.BOLD}{breakdown} = {total} combination(s) still possible.{C.RESET}")

    if total == 1:
        _print_resolution(game_state)
    else:
        print(f"  {C.YELLOW}Case NOT resolved yet — need more clues.{C.RESET}\n")


def _print_resolution(game_state: str) -> None:
    """Narrate the single remaining combination with its proof trace."""
    query = "envelope_suspect($s) AND envelope_weapon($w) AND envelope_room($r)"
    r = explain(knowledge=_kb(game_state, query), max_solutions=5, max_depth=30)
    if r.error or not r.explanations:
        print(f"  {C.RED}Could not resolve: {r.error}{C.RESET}\n")
        return
    subs = r.explanations[0].substitutions
    print(f"\n  {C.BOLD}{C.GREEN}*** CASE RESOLVED ***{C.RESET}")
    print(f"  The envelope contains: {_colorize_triple(subs)}\n")
    print(f"  {C.DIM}Deduction trace:{C.RESET}")
    for step in r.explanations[0].steps:
        # the engine shows generated ids for anonymous variables; collapse
        # them to _ so the trace reads like the rules themselves
        cleaned = re.sub(r"_\d+", "_", step)
        print(f"    {C.DIM}•{C.RESET} {cleaned}")
    print()


def print_what_if(name: str, result):
    """Pretty-print what-if results."""
    print(f"\n{C.BOLD}{'=' * 55}{C.RESET}")
    print(f"  {C.BOLD}{C.YELLOW}{name}{C.RESET}")
    print(f"{C.BOLD}{'=' * 55}{C.RESET}")

    if result.error:
        print(f"  {C.RED}Error: {result.error}{C.RESET}")
        return

    print(f"  {C.DIM}Modification:{C.RESET} {result.modifications}")
    print(f"  Before: {C.BOLD}{result.before_count}{C.RESET} solution(s)  "
          f"After: {C.BOLD}{result.after_count}{C.RESET} solution(s)  "
          f"{C.DIM}({result.elapsed_ms:.1f}ms){C.RESET}\n")

    if result.after_count > 0 and result.before_count == 0:
        print(f"  {C.BOLD}{C.GREEN}*** New solution(s) appeared! ***{C.RESET}")
        for i, sol in enumerate(result.solutions_after[:5], 1):
            print(f"  {C.BOLD}{i}.{C.RESET} {_colorize_triple(sol.substitutions)}")
    elif result.after_count == 0 and result.before_count > 0:
        print(f"  {C.BOLD}{C.RED}*** All solutions eliminated! ***{C.RESET}")
    else:
        print(f"  {result.conclusion}")


def main():
    parser = argparse.ArgumentParser(description="Cluedo Detective Agent")
    parser.add_argument(
        "--scenario",
        choices=["early", "late", "resolved", "what-if", "both"],
        default="both",
        help="'both' runs early → late → resolved",
    )
    parser.add_argument(
        "--custom", help="Path to custom game state .txt file"
    )
    args = parser.parse_args()

    scenarios = [
        ("Early Game (3 turns) - limited info", EARLY_GAME),
        ("Late Game (12 turns) - more info", LATE_GAME),
        ("Resolved Game (all cards accounted for)", RESOLVED_GAME),
    ]

    print_banner()
    rules = load_rules()
    print(f"  Rules loaded: {C.BOLD}{len(rules.splitlines())}{C.RESET} lines\n")
    print_how_to_read()

    if args.custom:
        state = Path(args.custom).read_text()
        print_case(f"Custom Game ({args.custom})", state)
    elif args.scenario == "what-if":
        what_if_scenarios(EARLY_GAME)
    elif args.scenario == "both":
        for name, state in scenarios:
            print_case(name, state)
    else:
        name, state = next(
            (n, s) for n, s in scenarios if n.lower().startswith(args.scenario)
        )
        print_case(name, state)


def what_if_scenarios(game_state: str) -> None:
    """Demonstrate what-if analysis on a game state."""
    print("\n--- What-if Analysis on Early Game ---")
    scenarios = [
        {
            "name": "What if we learn Peacock has candlestick (eliminates it from envelope)?",
            "modifications": "+ hand(peacock, candlestick)",
            "query": "envelope_weapon($w)",
        },
        {
            "name": "What if we learn the kitchen is NOT in the envelope (via suggestion)?",
            "modifications": "+ showed(peacock, kitchen, scarlett)",
            "query": "envelope_room($r)",
        },
    ]
    for sc in scenarios:
        result = what_if(
            base_knowledge=load_rules() + "\n" + game_state + f"\n? {sc['query']}",
            modifications=sc["modifications"],
            query=sc["query"],
            max_solutions=20,
            max_depth=30,
        )
        print_what_if(sc["name"], result)


if __name__ == "__main__":
    main()
