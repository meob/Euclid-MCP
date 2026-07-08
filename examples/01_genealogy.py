"""
01 — Genealogy: recursive family tree reasoning

Classic Prolog example adapted for Euclid-MCP.
Demonstrates:
  • Recursive rules (ancestor defined in terms of parent)
  • Multiple solutions from the same query
  • Proof trees that explain each step of the chain
  • How Euclid replaces the need for an LLM to "reason" step-by-step
"""
from euclid_mcp.server import reason
from euclid_mcp.models import ProofNode


def show_proof(node: ProofNode, indent: int = 0) -> None:
    pad = "  " * indent
    if node.type == "fact":
        print(f"{pad}├─ FACT: {node.goal}")
    elif node.type == "rule":
        print(f"{pad}├─ RULE: {node.goal}")
        print(f"{pad}│  └─ body: {node.body}")
        if node.subproof:
            show_proof(node.subproof, indent + 2)
    elif node.type == "and":
        print(f"{pad}├─ AND")
        if node.left:
            show_proof(node.left, indent + 1)
        if node.right:
            show_proof(node.right, indent + 1)


knowledge = """
# Family tree
parent(tom, bob)
parent(bob, ann)
parent(bob, pat)
parent(tom, liz)
parent(liz, mia)

# Ancestor: direct or through chain
ancestor($x, $y) IF parent($x, $y)
ancestor($x, $y) IF parent($x, $z) AND ancestor($z, $y)

? ancestor(tom, $who)
"""

result = reason(knowledge=knowledge, max_solutions=10)

print("=" * 55)
print("  GENEALOGY — Family Tree Reasoning")
print("  Who are Tom's ancestors?")
print("=" * 55)

print(f"\nQuery: {result.query}")
print(f"Elapsed: {result.elapsed_ms:.1f} ms")
print(f"Solutions found: {len(result.solutions)}\n")

for i, sol in enumerate(result.solutions, 1):
    print(f"── Solution #{i} ──")
    for var, val in sol.substitutions.items():
        print(f"   {var} = {val}")
    print(f"   Proof tree:")
    show_proof(sol.proof)
    print()

print("─" * 55)
print("  KEY INSIGHT")
print("  An LLM asked 'Who are Tom's descendants?' would need to")
print("  manually trace each chain. Euclid-MCP does it deterministically")
print("  and provides a verifiable proof for each answer.")
print("  → A small LLM can delegate reasoning to Euclid and just")
print("    describe the facts. No step-by-step CoT needed.")
print("─" * 55)
