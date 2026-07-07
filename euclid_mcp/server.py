import time

from mcp.server.fastmcp import FastMCP

from .language import parse
from .models import ReasonResult
from .prolog_bridge import execute as prolog_execute
from .translator import to_prolog

mcp = FastMCP(
    "Euclid-MCP",
    instructions="""Euclid-MCP e' un motore di deduzione logica.

Trasforma fatti e regole in un linguaggio intermedio semplice in dimostrazioni
formali usando SWI-Prolog come backend.

Il linguaggio intermedio supporta:
  - Fatti:  parent(tom, bob)
  - Regole: ancestor($x, $y) IF parent($x, $y) AND parent($y, $z)
  - Query:  ? ancestor(tom, $who)

Si puo' usare anche formato YAML:
  facts: [parent(tom, bob)]
  rules: [ancestor($x, $y) IF parent($x, $y)]
  query: ancestor(tom, $who)

Variabili con $nome, IF per implicazione, AND per congiunzione.
""",
)


@mcp.tool(
    description="Esegue deduzioni logiche su una base di conoscenza "
    "e restituisce soluzioni con la catena di dimostrazione",
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
            error=f"Errore nel parsing della conoscenza: {exc}",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    if query:
        kb.query = query

    if not kb.query:
        return ReasonResult(
            error="Nessuna query specificata. "
            "Aggiungi ? query o query: nel knowledge, "
            "o passa il parametro query.",
            elapsed_ms=(time.monotonic() - start) * 1000,
        )

    try:
        prolog_code = to_prolog(kb, max_depth=max_depth)
    except Exception as exc:
        return ReasonResult(
            error=f"Errore nella generazione del codice Prolog: {exc}",
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
