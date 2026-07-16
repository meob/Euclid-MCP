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
from euclid_mcp.server import reason, what_if
from game_states import EARLY_GAME, LATE_GAME
from pathlib import Path
import argparse

RULES_FILE = Path(__file__).parent / "cluedo_rules.euclid"


def load_rules() -> str:
    return RULES_FILE.read_text()


def detective(question: str, game_state: str):
    """Run deduction on a game state and return solutions."""
    knowledge = load_rules() + "\n" + game_state + f"\n? {question}"
    return reason(knowledge=knowledge, max_solutions=20, max_depth=30)


def print_solutions(name: str, result):
    """Pretty-print deduction results."""
    print(f"\n{'='*55}")
    print(f"  {name}")
    print(f"{'='*55}")

    if result.error:
        print(f"  Error: {result.error}")
        return

    if not result.solutions:
        print("  No solution found - need more clues!")
        return

    print(f"  Query: {result.query}")
    print(f"  Solutions found: {len(result.solutions)}")
    print(f"  Time: {result.elapsed_ms:.1f}ms\n")

    for i, sol in enumerate(result.solutions, 1):
        subs = sol.substitutions
        suspect = subs.get("s", "?")
        weapon = subs.get("w", "?")
        room = subs.get("r", "?")
        print(f"  {i}. {suspect:12s} + {weapon:12s} + {room}")
        if sol.proof:
            print(f"     Proof: {sol.proof.type}")


def print_what_if(name: str, result):
    """Pretty-print what-if results."""
    print(f"\n{'='*55}")
    print(f"  {name}")
    print(f"{'='*55}")

    if result.error:
        print(f"  Error: {result.error}")
        return

    print(f"  Modification: {result.modifications}")
    print(f"  Before: {result.before_count} solution(s)")
    print(f"  After:  {result.after_count} solution(s)")
    print(f"  Time: {result.elapsed_ms:.1f}ms\n")

    if result.after_count > 0 and result.before_count == 0:
        print("  *** New solution(s) appeared! ***")
        for i, sol in enumerate(result.solutions_after[:5], 1):
            subs = sol.substitutions
            suspect = subs.get("s", "?")
            weapon = subs.get("w", "?")
            room = subs.get("r", "?")
            print(f"  {i}. {suspect:12s} + {weapon:12s} + {room}")
    elif result.after_count == 0 and result.before_count > 0:
        print("  *** All solutions eliminated! ***")
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
    print("Cluedo Detective - Euclid-MCP Deduction Engine")
    print(f"Rules loaded: {len(rules.splitlines())} lines")

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
