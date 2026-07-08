import time

from mcp.server.fastmcp import FastMCP

from euclid_mcp.language import parse
from euclid_mcp.models import ReasonResult
from euclid_mcp.prolog_bridge import execute as prolog_execute
from euclid_mcp.translator import to_prolog

mcp = FastMCP(
    "Euclid-MCP",
    instructions="""Euclid-MCP is a deterministic logical reasoning engine.

Write facts, rules, and a query in the Euclid Intermediate Language:

Variables: $name  (e.g., $who, $x, $y)
Implication: IF  (e.g., mortal($x) IF human($x))
Conjunction: AND  (e.g., parent($x, $z) AND ancestor($z, $y))
Query prefix: ?

Examples:
    mortal(socrates)
    human(socrates)
    mortal($x) IF human($x)
    ? mortal($who)

The engine returns solutions with proof trees (fact/rule/and nodes).

YAML format is also supported:
  facts: [parent(tom, bob)]
  rules: [ancestor($x, $y) IF parent($x, $y)]
  query: ancestor(tom, $who)

Prefer the text format — it is more concise and less error-prone.
""",
)


@mcp.tool(
    description="Perform logical deduction on a knowledge base "
    "and return solutions with proof trees for each result",
)
def reason(
    knowledge: str,
    query: str | None = None,
    max_solutions: int = 5,
    max_depth: int = 30,
) -> ReasonResult:
    start = time.monotonic()

    try:
        kb = parse(knowledge)
    except Exception as exc:
        return ReasonResult(
            error=f"Knowledge parsing error: {exc}",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    if query:
        kb.query = query

    if not kb.query:
        return ReasonResult(
            error="No query specified. "
            "Add ? query or query: in the knowledge, "
            "or pass the query parameter.",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    try:
        prolog_code = to_prolog(kb, max_depth=max_depth)
    except Exception as exc:
        return ReasonResult(
            error=f"Prolog code generation error: {exc}",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    try:
        solutions = prolog_execute(prolog_code, timeout=30)
    except RuntimeError as exc:
        return ReasonResult(
            error=str(exc),
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    elapsed = (time.monotonic() - start) * 1000
    return ReasonResult(
        solutions=solutions[:max_solutions],
        query=kb.query,
        elapsed_ms=elapsed,
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
