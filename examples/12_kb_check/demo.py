#!/usr/bin/env python3
"""
KB Check — Example 12

Demonstrates check_kb() on valid and broken knowledge bases.

Usage:
    python3 demo.py              # Check both files
    python3 demo.py --file valid # Check specific file
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from euclid_mcp.server import check_kb

BASE_DIR = Path(__file__).parent


def check_file(filepath: Path) -> dict:
    """Run check_kb on a file and return the result."""
    knowledge = filepath.read_text()
    start = time.time()
    result = check_kb(knowledge=knowledge)
    elapsed = time.time() - start

    return {
        "file": filepath.name,
        "valid": result.valid,
        "errors": [{"type": e.type, "message": e.message} for e in result.errors],
        "warnings": [{"type": w.type, "message": w.message} for w in result.warnings],
        "facts_count": result.facts_count,
        "rules_count": result.rules_count,
        "predicates_count": result.predicates_count,
        "elapsed_ms": round(elapsed * 1000),
    }


def print_result(result: dict) -> None:
    """Pretty-print a check result."""
    status = "VALID" if result["valid"] else "INVALID"
    print(f"\n{'='*60}")
    print(f"  {result['file']} — {status}")
    print(f"{'='*60}")
    print(f"  Facts: {result['facts_count']} | Rules: {result['rules_count']} | Predicates: {result['predicates_count']}")
    print(f"  Time: {result['elapsed_ms']}ms")

    if result["errors"]:
        print(f"\n  Errors ({len(result['errors'])}):")
        for e in result["errors"]:
            print(f"    - [{e['type']}] {e['message']}")

    if result["warnings"]:
        print(f"\n  Warnings ({len(result['warnings'])}):")
        for w in result["warnings"]:
            print(f"    - [{w['type']}] {w['message']}")

    if not result["errors"] and not result["warnings"]:
        print("\n  No issues found.")


def main():
    parser = argparse.ArgumentParser(description="KB Check Demo")
    parser.add_argument("--file", choices=["valid", "broken", "both"], default="both")
    args = parser.parse_args()

    print("KB Check Demo — check_kb()")

    if args.file == "valid":
        result = check_file(BASE_DIR / "valid.knowledge")
        print_result(result)
    elif args.file == "broken":
        result = check_file(BASE_DIR / "broken.knowledge")
        print_result(result)
    else:
        for name in ["valid.knowledge", "broken.knowledge"]:
            result = check_file(BASE_DIR / name)
            print_result(result)

    # Summary
    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    print("  check_kb() detects: undefined predicates, circular rules,")
    print("  duplicate facts, syntax errors, undefined query predicates.")


if __name__ == "__main__":
    main()
