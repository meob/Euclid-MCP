"""
04 — Loan Eligibility: transparent business rules

Real-world financial decision-making. Demonstrates:
  • Multiple conditions combined with AND
  • Business rules that are explicit, auditable, and hallucination-free
  • The proof tree as a compliance / explainability artifact
  • How Euclid replaces opaque RAG lookups with deterministic logic
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
# ── Applicant characteristics ──
adult(alice)
good_income(alice)
good_credit(alice)
employed(alice)

adult(bob)
low_income(bob)
fair_credit(bob)
employed(bob)

adult(carl)
good_income(carl)
good_credit(carl)
employed(carl)

adult(diana)
good_income(diana)
excellent_credit(diana)
# diana is NOT employed

senior(thomas)
low_income(thomas)
good_credit(thomas)
# thomas is not employed and is a senior

# ── Individual eligibility rules ──
meets_age($p) IF adult($p)
meets_income($p) IF good_income($p)
meets_credit($p) IF good_credit($p)
meets_credit($p) IF excellent_credit($p)
meets_employment($p) IF employed($p)

# ── Overall eligibility: ALL four conditions must hold ──
eligible($p) IF meets_age($p) AND meets_income($p) AND meets_credit($p) AND meets_employment($p)

# ── Conditional: meets all but employment ──
conditional($p) IF meets_age($p) AND meets_income($p) AND meets_credit($p)

# ── Reason for rejection (separate checks) ──
rejected($p, poor_credit) IF adult($p) AND good_income($p) AND employed($p) AND fair_credit($p)
rejected($p, low_income) IF adult($p) AND employed($p) AND good_credit($p) AND low_income($p)
rejected($p, unemployed) IF adult($p) AND good_income($p) AND good_credit($p)

# ── Queries ──
? eligible($who)
"""

result = reason(knowledge=knowledge, max_solutions=10)

print("=" * 55)
print("  LOAN ELIGIBILITY — Transparent Business Rules")
print("  Who is eligible for a loan?")
print("=" * 55)

print(f"\nQuery: {result.query}")
print(f"Elapsed: {result.elapsed_ms:.1f} ms")
print(f"Solutions found: {len(result.solutions)}\n")

for i, sol in enumerate(result.solutions, 1):
    print(f"── Solution #{i} ──")
    for var, val in sol.substitutions.items():
        print(f"   {var} = {val}")
    print(f"   Proof tree (compliance trail):")
    show_proof(sol.proof)
    print()

# ── Check each applicant individually ──
print("─" * 55)
print("  DETAILED CHECK — Per applicant")
print("─" * 55)
for person in ["alice", "bob", "carl", "diana", "thomas"]:
    r = reason(knowledge=knowledge, query=f"eligible({person})")
    result_text = "✅ ELIGIBLE" if r.solutions else "❌ NOT ELIGIBLE"
    print(f"\n  {person}: {result_text}")
    if not r.solutions:
        # Show which condition fails
        for cond in ["meets_age", "meets_income", "meets_credit", "meets_employment"]:
            cr = reason(knowledge=knowledge, query=f"{cond}({person})")
            mark = "✅" if cr.solutions else "❌"
            print(f"     {mark} {cond}")
        # Check conditional
        cond_r = reason(knowledge=knowledge, query=f"conditional({person})")
        if cond_r.solutions:
            print(f"     → Could be approved if employed")
    else:
        show_proof(r.solutions[0].proof)

print("\n" + "─" * 55)
print("  KEY INSIGHT")
print("  Loan decisions must be EXPLAINABLE and AUDITABLE.")
print("  A proof tree shows exactly which rule passed/failed,")
print("  unlike an LLM's 'the applicant seems qualified'.")
print("  → Business rules in Euclid = deterministic + auditable.")
print("  → No hallucinations, no RAG, no vector DB needed.")
print("─" * 55)
