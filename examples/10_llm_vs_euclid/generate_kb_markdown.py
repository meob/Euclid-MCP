#!/usr/bin/env python3
"""
Generate the condensed markdown digest of the IT Security KB.

The same digest that example 10 (LLM vs Euclid-MCP) builds in memory at
startup for Bot A, persisted to a file so it can be reviewed and versioned.

Usage:
    python generate_kb_markdown.py                  # writes kb_markdown.md
    python generate_kb_markdown.py --output out.md  # custom path
"""

import argparse
from pathlib import Path

from kb_utils import generate_kb_markdown, load_kb_euclid


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the KB markdown digest")
    parser.add_argument(
        "--output",
        default=None,
        help="Output path (default: kb_markdown.md next to this script)",
    )
    args = parser.parse_args()

    output = Path(args.output) if args.output else Path(__file__).resolve().parent / "kb_markdown.md"

    md = generate_kb_markdown()
    output.write_text(md, encoding="utf-8")

    kb_euclid = load_kb_euclid()
    print(f"KB: {len(kb_euclid):,} bytes Euclid-IR -> {len(md):,} bytes markdown -> {output}")


if __name__ == "__main__":
    main()
