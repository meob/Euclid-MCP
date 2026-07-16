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

  # Using other tools
  python3 euclid_cli.py --tool diagnose --knowledge "..." --query "red($x)" --mode why
  python3 euclid_cli.py --tool what-if --knowledge "..." --modifications "+ red(blue)" --query "red($x)"
  python3 euclid_cli.py --tool check-kb --knowledge "..."

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

from euclid_mcp.server import check_kb, diagnose, reason, what_if



def _parse_args() -> dict:
    """Parse CLI arguments into a data dict."""
    if len(sys.argv) >= 3 and sys.argv[1] == "--tool":
        tool = sys.argv[2]
        # Parse remaining --key value pairs
        data = {"_tool": tool}
        i = 3
        while i < len(sys.argv):
            if sys.argv[i] == "--knowledge" and i + 1 < len(sys.argv):
                data["knowledge"] = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--query" and i + 1 < len(sys.argv):
                data["query"] = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--mode" and i + 1 < len(sys.argv):
                data["mode"] = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--modifications" and i + 1 < len(sys.argv):
                data["modifications"] = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--max-solutions" and i + 1 < len(sys.argv):
                data["max_solutions"] = int(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == "--max-depth" and i + 1 < len(sys.argv):
                data["max_depth"] = int(sys.argv[i + 1])
                i += 2
            else:
                i += 1
        return data
    elif len(sys.argv) >= 3 and sys.argv[1] == "--knowledge":
        knowledge = sys.argv[2]
        query = sys.argv[4] if len(sys.argv) >= 5 and sys.argv[3] == "--query" else None
        return {"knowledge": knowledge, "query": query}
    elif len(sys.argv) >= 2:
        return json.loads(sys.argv[1])
    else:
        raw = sys.stdin.read()
        return json.loads(raw)


def main():
    data = _parse_args()

    data.setdefault("max_solutions", 5)
    data.setdefault("max_depth", 30)

    tool = data.pop("_tool", "reason")

    if tool == "reason":
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
    elif tool == "diagnose":
        result = diagnose(
            knowledge=data["knowledge"],
            query=data.get("query", ""),
            mode=data.get("mode", "why"),
            max_solutions=data["max_solutions"],
            max_depth=data["max_depth"],
        )
        output = {
            "query": result.query,
            "mode": result.mode,
            "holds": result.holds,
            "findings": [f.model_dump() for f in result.findings],
            "conclusion": result.conclusion,
            "solutions": [s.model_dump() for s in result.solutions],
            "elapsed_ms": result.elapsed_ms,
        }
    elif tool == "what-if":
        result = what_if(
            base_knowledge=data["knowledge"],
            modifications=data.get("modifications", ""),
            query=data.get("query", ""),
            max_solutions=data["max_solutions"],
            max_depth=data["max_depth"],
        )
        output = {
            "query": result.query,
            "modifications": result.modifications,
            "before_count": result.before_count,
            "after_count": result.after_count,
            "delta": result.delta,
            "conclusion": result.conclusion,
            "elapsed_ms": result.elapsed_ms,
        }
    elif tool == "check-kb":
        result = check_kb(knowledge=data["knowledge"])
        output = {
            "valid": result.valid,
            "errors": [e.model_dump() for e in result.errors],
            "warnings": [w.model_dump() for w in result.warnings],
            "facts_count": result.facts_count,
            "rules_count": result.rules_count,
            "predicates_count": result.predicates_count,
            "elapsed_ms": result.elapsed_ms,
        }
    else:
        output = {"error": f"Unknown tool: {tool}. Use reason, diagnose, what-if, or check-kb."}

    json.dump(output, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
