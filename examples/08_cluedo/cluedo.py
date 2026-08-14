#!/usr/bin/env python3
"""
Cluedo Detective - Example 08
A detective agent that uses Euclid-MCP to solve Cluedo mysteries.

Usage:
    python3 cluedo.py                          # Run both scenarios
    python3 cluedo.py --scenario early         # Early game only
    python3 cluedo.py --scenario late          # Late game only
    python3 cluedo.py --custom <file>          # Custom game state file
"""
import argparse
from pathlib import Path

from game_states import EARLY_GAME, LATE_GAME

from euclid_mcp.server import reason, what_if

RULES_FILE = Path(__file__).parent / "cluedo_rules.euclid"


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


MAGNIFIER = [
    "      .--.     ",
    "     |o_o|     ",
    "     |:_/|     ",
    "    //   \\\\   ",
    "   (|     | )  ",
    "  /'\\\\_   _/`\\\\ ",
    "  \\\\___)=(___/  ",
]


def print_banner():
    """Print the detective-themed opening banner."""
    for row in MAGNIFIER:
        print(f"{C.BOLD}{C.CYAN}{row}{C.RESET}")

    inner = 60
    text_width = inner - 4
    lines = [
        "╔" + "═" * inner + "╗",
        "║" + "CLUEDO DETECTIVE".center(inner) + "║",
        "║" + " " * inner + "║",
        "║  " + "Euclid-MCP Deduction Engine".ljust(text_width) + "  ║",
        "║  " + "Solve the case by elimination: who, with what, where.".ljust(text_width) + "  ║",
        "╚" + "═" * inner + "╝",
    ]
    print(f"{C.BOLD}{C.CYAN}" + "\n".join(lines) + f"{C.RESET}")
    print()


def load_rules() -> str:
    return RULES_FILE.read_text()


def detective(question: str, game_state: str):
    """Run deduction on a game state and return solutions."""
    knowledge = load_rules() + "\n" + game_state + f"\n? {question}"
    return reason(knowledge=knowledge, max_solutions=20, max_depth=30)


def colorize_triple(subs) -> str:
    """Render a suspect/weapon/room solution with per-category colors."""
    suspect = subs.get("s", "?")
    weapon = subs.get("w", "?")
    room = subs.get("r", "?")
    return (
        f"{C.MAGENTA}{suspect}{C.RESET} + "
        f"{C.RED}{weapon}{C.RESET} + "
        f"{C.CYAN}{room}{C.RESET}"
    )


def print_solutions(name: str, result):
    """Pretty-print deduction results."""
    print(f"\n{C.BOLD}{'=' * 55}{C.RESET}")
    print(f"  {C.BOLD}{C.YELLOW}{name}{C.RESET}")
    print(f"{C.BOLD}{'=' * 55}{C.RESET}")

    if result.error:
        print(f"  {C.RED}Error: {result.error}{C.RESET}")
        return

    if not result.solutions:
        print(f"  {C.YELLOW}No solution found — need more clues!{C.RESET}")
        return

    print(f"  {C.CYAN}Query:{C.RESET} {result.query}")
    print(f"  {C.GREEN}Solutions found:{C.RESET} {C.BOLD}{len(result.solutions)}{C.RESET}"
          f"  {C.DIM}({result.elapsed_ms:.1f}ms){C.RESET}\n")

    for i, sol in enumerate(result.solutions, 1):
        print(f"  {C.BOLD}{i}.{C.RESET} {colorize_triple(sol.substitutions)}")
        if sol.proof:
            print(f"     {C.DIM}Proof: {sol.proof.type}{C.RESET}")

    print(f"\n  {C.BOLD}{C.GREEN}CASE RESOLVED{C.RESET}")


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
            print(f"  {C.BOLD}{i}.{C.RESET} {colorize_triple(sol.substitutions)}")
    elif result.after_count == 0 and result.before_count > 0:
        print(f"  {C.BOLD}{C.RED}*** All solutions eliminated! ***{C.RESET}")
    else:
        print(f"  {result.conclusion}")


def main():
    parser = argparse.ArgumentParser(description="Cluedo Detective Agent")
    parser.add_argument(
        "--scenario", choices=["early", "late", "what-if", "both"], default="both"
    )
    parser.add_argument(
        "--custom", help="Path to custom game state .txt file"
    )
    args = parser.parse_args()

    rules = load_rules()
    print_banner()
    print(f"  Rules loaded: {C.BOLD}{len(rules.splitlines())}{C.RESET} lines\n")

    # Query for full envelope: 1 suspect + 1 weapon + 1 room
    query = "envelope_suspect($s) AND envelope_weapon($w) AND envelope_room($r)"

    if args.custom:
        state = Path(args.custom).read_text()
        result = detective(query, state)
        print_solutions(f"Custom Game ({args.custom})", result)
    elif args.scenario == "what-if":
        # What-if scenarios on early game
        print("\n--- What-if Analysis on Early Game ---")
        scenarios = [
            {
                "name": "What if we learn Peacock has candlestick (eliminates it from envelope)?",
                "modifications": "+ hand(peacock, candlestick)",
                "query": "envelope_weapon($w)",
            },
            {
                "name": "What if we learn the kitchen is NOT in the envelope (via suggestion)?",
                "modifications": "+ showed(peacock, candlestick, scarlett)",
                "query": "envelope_room($r)",
            },
        ]
        for sc in scenarios:
            result = what_if(
                base_knowledge=rules + "\n" + EARLY_GAME + f"\n? {sc['query']}",
                modifications=sc["modifications"],
                query=sc["query"],
                max_solutions=20,
                max_depth=30,
            )
            print_what_if(sc["name"], result)
    elif args.scenario == "early":
        result = detective(query, EARLY_GAME)
        print_solutions("Early Game (3 turns) - limited info", result)
    elif args.scenario == "late":
        result = detective(query, LATE_GAME)
        print_solutions("Late Game (12 turns) - more info", result)
    else:
        for name, state in [
            ("Early Game (3 turns) - limited info", EARLY_GAME),
            ("Late Game (12 turns) - more info", LATE_GAME),
        ]:
            result = detective(query, state)
            print_solutions(name, result)


if __name__ == "__main__":
    main()
