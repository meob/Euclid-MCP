import time

from mcp.server.fastmcp import FastMCP

from euclid_mcp.language import parse
from euclid_mcp.models import ReasonResult
from euclid_mcp.prolog_bridge import execute as prolog_execute
from euclid_mcp.translator import to_prolog

# Security limits
MAX_KNOWLEDGE_LENGTH = 500_000  # 500 KB
MAX_DEPTH_LIMIT = 500
MAX_SOLUTIONS_LIMIT = 1000

mcp = FastMCP(
    "Euclid-MCP",
    instructions="""Euclid-MCP is a deterministic logical reasoning engine.
Write facts and rules in Euclid IR, the engine returns solutions with proof trees.

Syntax:
  Variables: $name  |  Implication: IF  |  Conjunction: AND  |  Query prefix: ?
  Negation: NOT  |  Arithmetic: >, >=, <, <=, =:=, =\\=  |  Multi-line rules supported

Examples:
    human(socrates)
    mortal($x) IF human($x)
    ? mortal($who)

YAML format also supported (see AGENTS.md for full reference).
Use when: logical rules, compliance checks, RBAC, proof trees, deterministic answers.
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

    # Security: validate limits
    if not (1 <= max_solutions <= MAX_SOLUTIONS_LIMIT):
        return ReasonResult(
            error=f"max_solutions must be between 1 and {MAX_SOLUTIONS_LIMIT}",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )
    if not (1 <= max_depth <= MAX_DEPTH_LIMIT):
        return ReasonResult(
            error=f"max_depth must be between 1 and {MAX_DEPTH_LIMIT}",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    # Security: reject oversized input
    if len(knowledge) > MAX_KNOWLEDGE_LENGTH:
        return ReasonResult(
            error=f"Knowledge exceeds maximum allowed size "
            f"({len(knowledge):,} > {MAX_KNOWLEDGE_LENGTH:,} bytes)",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

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
        prolog_code = to_prolog(kb, max_depth=max_depth, max_solutions=max_solutions)
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
