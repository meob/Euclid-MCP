"""
02 — RBAC: Role-Based Access Control

Real-world security example. Demonstrates:
  • Role hierarchy (admin → editor → viewer)
  • Permission mapping through role chains
  • AND for multi-condition access (e.g., "can edit" needs write + read)
  • Proof tree as an AUDIT TRAIL — every access decision is explainable
  • Business rules that are safe, demonstrable, and hallucination-free
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
# ── Users ──
user(alice)
user(bob)
user(carl)

# ── Roles ──
role(admin)
role(editor)
role(viewer)

# ── Role hierarchy ──
# admin inherits everything from editor, editor inherits from viewer
inherits(admin, editor)
inherits(editor, viewer)

# ── User-role assignments ──
has_role(alice, admin)
has_role(bob, editor)
has_role(carl, viewer)

# ── Permissions attached to roles ──
permission(viewer, read)
permission(editor, write)
permission(admin, delete)

# ── Rule: a role gets all permissions from roles it inherits ──
role_has_permission($role, $perm) IF permission($role, $perm)
role_has_permission($role, $perm) IF inherits($role, $sub) AND role_has_permission($sub, $perm)

# ── Rule: user has permission if their role has it ──
user_has_permission($user, $perm) IF has_role($user, $role) AND role_has_permission($role, $perm)

# ── Complex permission: "edit" requires both read and write ──
can_edit($user) IF user_has_permission($user, read) AND user_has_permission($user, write)

# ── Queries ──
? user_has_permission($who, $perm)
"""

result = reason(knowledge=knowledge, max_solutions=20)

print("=" * 55)
print("  RBAC — Role-Based Access Control")
print("  Who has which permissions?")
print("=" * 55)

print(f"\nQuery: {result.query}")
print(f"Elapsed: {result.elapsed_ms:.1f} ms")
print(f"Solutions found: {len(result.solutions)}\n")

for i, sol in enumerate(result.solutions, 1):
    print(f"── Solution #{i} ──")
    for var, val in sol.substitutions.items():
        print(f"   {var} = {val}")
    print(f"   Proof tree (audit trail):")
    show_proof(sol.proof)
    print()

print("─" * 55)
print("  KEY INSIGHT")
print("  With RAG + vector DB, an LLM might hallucinate that")
print("  'bob can delete' or 'alice cannot read'. With Euclid-MCP")
print("  the permission check is DETERMINISTIC and the proof tree")
print("  serves as an AUDIT TRAIL for compliance.")
print("  → Business rules belong in Euclid, not in a vector DB.")
print("─" * 55)

# ── Bonus: who can edit? ──
result2 = reason(knowledge=knowledge, query="can_edit($user)")
print("\n── BONUS: Who can edit? (requires read AND write) ──")
for sol in result2.solutions:
    print(f"   {sol.substitutions['user']} → CAN_EDIT = Yes")
    show_proof(sol.proof)
    print()
