"""
03 — Classification: biological taxonomy

Educational example showing hierarchical classification.
Demonstrates:
  • is_a chains (property inheritance)
  • Multiple parents / multiple classification paths
  • How Euclid infers properties transitively
  • How a small LLM can answer "does X have property Y?"
    without memorizing taxonomy — it just asks Euclid
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
# ── Taxonomy: is_a hierarchy ──
is_a(siamese, cat)
is_a(cat, felinae)
is_a(felinae, felidae)
is_a(felidae, carnivora)
is_a(carnivora, mammal)
is_a(mammal, vertebrate)
is_a(vertebrate, animal)

is_a(golden_retriever, dog)
is_a(dog, caninae)
is_a(caninae, canidae)
is_a(canidae, carnivora)

is_a(eagle, accipitridae)
is_a(accipitridae, bird_of_prey)
is_a(bird_of_prey, bird)
is_a(bird, vertebrate)

# ── Properties of specific nodes ──
property(animal, multicellular)
property(vertebrate, has_backbone)
property(mammal, warm_blooded)
property(mammal, has_fur)
property(carnivora, eats_meat)
property(felidae, retractable_claws)
property(bird, has_feathers)
property(bird_of_prey, sharp_beak)
property(felinae, cannot_roar)

# ── Rule: inherit properties through is_a chain ──
has_property($x, $prop) IF property($x, $prop)
has_property($x, $prop) IF is_a($x, $parent) AND has_property($parent, $prop)

# ── Queries ──
? has_property(siamese, $what)
"""

result = reason(knowledge=knowledge, max_solutions=20)

print("=" * 55)
print("  CLASSIFICATION — Biological Taxonomy")
print("  What properties does a Siamese cat have?")
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
print("  An LLM with 3B parameters may not know whether a Siamese")
print("  cat has retractable claws. But it CAN describe facts like")
print("  'siamese is_a cat', 'cat is_a felinae', 'felinae cannot roar'.")
print("  Euclid chains the facts into provable answers.")
print("  → A small LLM + Euclid > a large LLM alone for taxonomy QA.")
print("─" * 55)

# ── Bonus: compare two animals ──
print("\n── BONUS: Compare Siamese vs Golden Retriever ──")
for animal in ["siamese", "golden_retriever"]:
    r = reason(knowledge=knowledge, query=f"has_property({animal}, $p)")
    props = {s.substitutions["p"] for s in r.solutions}
    print(f"   {animal}: {', '.join(sorted(props))}")
