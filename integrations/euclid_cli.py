#!/usr/bin/env python3
"""
Euclid-MCP CLI wrapper — pipe JSON in, get JSON out.

Intended for n8n executeCommand nodes, shell pipelines, or manual testing.

Usage:
  # From file
  echo '{"knowledge": "red(apple)\\n? red($x)", "max_solutions": 5}' | python3 euclid_cli.py

  # With inline JSON (use proper JSON escapes)
  python3 euclid_cli.py '{"knowledge": "red(apple)\\n? red($x)"}'

  # With separate arguments
  python3 euclid_cli.py --knowledge "red(apple)" --query "red($x)"

Output: JSON to stdout, errors to stderr.
"""
import json
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
os.chdir(_project_root)

from euclid_mcp.server import reason



def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--knowledge":
        knowledge = sys.argv[2]
        query = sys.argv[4] if len(sys.argv) >= 5 and sys.argv[3] == "--query" else None
        data = {"knowledge": knowledge, "query": query}
    elif len(sys.argv) >= 2:
        data = json.loads(sys.argv[1])
    else:
        raw = sys.stdin.read()
        data = json.loads(raw)

    data.setdefault("max_solutions", 5)
    data.setdefault("max_depth", 30)

    result = reason(
        knowledge=data["knowledge"],
        query=data.get("query"),
        max_solutions=data["max_solutions"],
        max_depth=data["max_depth"],
    )

    output = {
        "query": result.query,
        "solutions": [s.model_dump() for s in result.solutions],
        "elapsed_ms": result.elapsed_ms,
    }
    json.dump(output, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
