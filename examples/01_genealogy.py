"""
01 — Genealogy: recursive family tree reasoning

Classic Prolog example adapted for Euclid-MCP.
Demonstrates:
  • Recursive rules (ancestor defined in terms of parent)
  • Multiple solutions from the same query
  • Proof trees that explain each step of the chain
  • How Euclid replaces the need for an LLM to "reason" step-by-step
"""
from euclid_mcp.models import ProofNode
from euclid_mcp.server import reason


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

# Person data (string literals — UTF-8 preserved as-is)
person(tom, "tom@example.com")
person(bob, "bob@example.com")
person(ann, "ann@example.com")
person(pat, "pat@example.com")
person(liz, "liz@example.com")
person(mia, "mia@example.com")

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
    print("   Proof tree:")
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

# ── Bonus: string literals ──
# String values (emails, URLs, etc.) pass through to Prolog unchanged.
# Use this to attach metadata to entities without losing them in translation.
result2 = reason(knowledge=knowledge, query="person($who, $email)")
print("\n── BONUS: String Literals ──")
print("  Emails preserved as UTF-8 strings:")
for sol in result2.solutions:
    print(f"   {sol.substitutions['who']:6s} → {sol.substitutions['email']}")
print("─" * 55)
