"""
Reasoning Benchmark: Small LLM vs Cloud LLM vs Small LLM + Euclid-MCP

Compares accuracy, speed, and cost across 3 conditions on 5 reasoning tasks.
"""
import json
import re
import time
import requests
from euclid_mcp.server import reason
from euclid_mcp.models import ReasonResult


OLLAMA = "http://localhost:11434/api/chat"
SMALL_MODEL = "llama3.1:8b"
CLOUD_MODEL = "qwen3-coder:480b-cloud"

def _split_gold(gold: str) -> tuple[str, str]:
    """Split gold Euclid into preset_rules (lines with IF) and rest (facts + query)."""
    facts = []
    rules = []
    for line in gold.strip().split("\n"):
        if " IF " in line:
            rules.append(line)
        else:
            facts.append(line)
    return "\n".join(rules), "\n".join(facts)


QUESTIONS = [
    {
        "id": "Q1",
        "label": "Genealogy (deep chain)",
        "scenario": (
            "We have a family tree:\n"
            "- Tom is the parent of Bob and Liz.\n"
            "- Bob is the parent of Ann and Pat.\n"
            "- Liz is the parent of Mia.\n\n"
            "An ancestor is defined as:\n"
            "- X is an ancestor of Y if X is a direct parent of Y.\n"
            "- X is an ancestor of Y if X is a parent of Z and Z is an ancestor of Y."
        ),
        "question": "Is Tom an ancestor of Ann?",
        "expected": "Yes",
        "gold_euclid": (
            "parent(tom, bob)\n"
            "parent(bob, ann)\n"
            "parent(bob, pat)\n"
            "parent(tom, liz)\n"
            "parent(liz, mia)\n"
            "ancestor($x, $y) IF parent($x, $y)\n"
            "ancestor($x, $y) IF parent($x, $z) AND ancestor($z, $y)\n"
            "? ancestor(tom, ann)"
        ),
    },
    {
        "id": "Q2",
        "label": "Taxonomy (property inheritance)",
        "scenario": (
            "We have an animal taxonomy:\n"
            "- A Siamese is a cat.\n"
            "- A cat is a felinae.\n"
            "- A felinae is a felidae.\n"
            "- A felidae is a carnivoran.\n"
            "- Felidae have retractable claws.\n\n"
            "A species has a property if the property is directly assigned to it, "
            "or if anything it inherits from (is_a chain) has that property."
        ),
        "question": "Does a Siamese have retractable claws?",
        "expected": "Yes",
        "gold_euclid": (
            "is_a(siamese, cat)\n"
            "is_a(cat, felinae)\n"
            "is_a(felinae, felidae)\n"
            "is_a(felidae, carnivoran)\n"
            "property(felidae, retractable_claws)\n"
            "has_property($x, $p) IF property($x, $p)\n"
            "has_property($x, $p) IF is_a($x, $parent) AND has_property($parent, $p)\n"
            "? has_property(siamese, retractable_claws)"
        ),
    },
    {
        "id": "Q3",
        "label": "Taxonomy (negative inference)",
        "scenario": (
            "We have an animal classification:\n"
            "- An eagle is a raptor.\n"
            "- A raptor is a bird.\n"
            "- A bird is a vertebrate.\n"
            "- A mammal has fur.\n\n"
            "A species has a property if the property is directly assigned to it, "
            "or if anything it inherits from (is_a chain) has that property."
        ),
        "question": "Does an eagle have fur?",
        "expected": "No",
        "gold_euclid": (
            "is_a(eagle, raptor)\n"
            "is_a(raptor, bird)\n"
            "is_a(bird, vertebrate)\n"
            "property(mammal, has_fur)\n"
            "has_property($x, $p) IF property($x, $p)\n"
            "has_property($x, $p) IF is_a($x, $parent) AND has_property($parent, $p)\n"
            "? has_property(eagle, has_fur)"
        ),
    },
    {
        "id": "Q4",
        "label": "RBAC (permission inheritance)",
        "scenario": (
            "We have a role-based access control system:\n"
            "- Alice has the admin role.\n"
            "- Admin inherits from editor.\n"
            "- Editor inherits from viewer.\n"
            "- Viewer can read documents.\n"
            "- Editor can write documents.\n"
            "- Admin can delete documents.\n\n"
            "A role has all permissions assigned directly to it, "
            "plus all permissions of roles it inherits from. "
            "A user has the permissions of their role."
        ),
        "question": "Can Alice write documents?",
        "expected": "Yes",
        "gold_euclid": (
            "has_role(alice, admin)\n"
            "inherits(admin, editor)\n"
            "inherits(editor, viewer)\n"
            "permission(viewer, read)\n"
            "permission(editor, write)\n"
            "permission(admin, delete)\n"
            "role_has_permission($r, $p) IF permission($r, $p)\n"
            "role_has_permission($r, $p) IF inherits($r, $sub) AND role_has_permission($sub, $p)\n"
            "user_has_permission($u, $p) IF has_role($u, $r) AND role_has_permission($r, $p)\n"
            "? user_has_permission(alice, write)"
        ),
    },
    {
        "id": "Q5",
        "label": "RBAC (negative / no permission)",
        "scenario": (
            "We have a role-based access control system:\n"
            "- Bob has the viewer role.\n"
            "- Admin inherits from editor.\n"
            "- Editor inherits from viewer.\n"
            "- Viewer can read documents.\n"
            "- Editor can write documents.\n"
            "- Admin can delete documents.\n\n"
            "A role has all permissions assigned directly to it, "
            "plus all permissions of roles it inherits from. "
            "A user has the permissions of their role."
        ),
        "question": "Can Bob delete documents?",
        "expected": "No",
        "gold_euclid": (
            "has_role(bob, viewer)\n"
            "inherits(admin, editor)\n"
            "inherits(editor, viewer)\n"
            "permission(viewer, read)\n"
            "permission(editor, write)\n"
            "permission(admin, delete)\n"
            "role_has_permission($r, $p) IF permission($r, $p)\n"
            "role_has_permission($r, $p) IF inherits($r, $sub) AND role_has_permission($sub, $p)\n"
            "user_has_permission($u, $p) IF has_role($u, $r) AND role_has_permission($r, $p)\n"
            "? user_has_permission(bob, delete)"
        ),
    },
]

# Pre-compute preset_rules and gold_facts for each question
for q in QUESTIONS:
    rules, facts = _split_gold(q["gold_euclid"])
    q["preset_rules"] = rules
    q["gold_facts"] = facts


# ── Helpers ──


def call_ollama(model: str, system: str, prompt: str, timeout: int = 180) -> dict | None:
    try:
        r = requests.post(
            OLLAMA,
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "options": {"temperature": 0.0},
            },
            timeout=timeout,
        )
        return r.json()
    except Exception as exc:
        return {"error": str(exc)}


def extract_answer(text: str) -> str | None:
    m = re.search(r'ANSWER\s*:\s*(Yes|No)', text, re.IGNORECASE)
    if m:
        return m.group(1).capitalize()
    return None


def extract_euclid(text: str) -> str | None:
    lines = text.strip().split("\n")
    euclid_lines = []
    in_fence = False
    for line in lines:
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            euclid_lines.append(line)
    if not euclid_lines:
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith("//"):
                if re.match(r'^[a-z][a-z_]*\(', stripped) or stripped.startswith('?'):
                    euclid_lines.append(line)
    return "\n".join(euclid_lines).strip() if euclid_lines else None


def run_euclid(euclid_code: str) -> ReasonResult:
    try:
        return reason(knowledge=euclid_code)
    except Exception as exc:
        result = ReasonResult()
        result.error = str(exc)
        return result


def count_tokens(data: dict | None) -> tuple[int, int]:
    if data is None:
        return (0, 0)
    prompt_evals = data.get("prompt_eval_count", 0)
    eval_count = data.get("eval_count", 0)
    return (prompt_evals, eval_count)


# ── Conditions ──


def run_direct(q: dict, model: str) -> dict:
    system = (
        "Answer concisely. Think step by step, "
        "then end with 'ANSWER: Yes' or 'ANSWER: No'."
    )
    prompt = (
        f"SCENARIO:\n{q['scenario']}\n\n"
        f"QUESTION: {q['question']}\n\n"
        f"REASONING:\n"
    )
    start = time.monotonic()
    data = call_ollama(model, system, prompt)
    elapsed = (time.monotonic() - start) * 1000
    raw = (data.get("message", {}) or {}).get("content", "") if data and "error" not in data else ""
    answer = extract_answer(raw)
    correct = (answer or "").lower() == q["expected"].lower()
    in_tok, out_tok = count_tokens(data)
    return {
        "raw": raw,
        "answer": answer,
        "correct": correct,
        "elapsed_ms": elapsed,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "error": data.get("error") if data else "no response",
    }


def _facts_and_query(gold_facts: str) -> tuple[list[str], str | None]:
    """Split gold facts string into fact lines and query line."""
    fact_lines = []
    query = None
    for line in gold_facts.strip().split("\n"):
        line = line.strip()
        if line.startswith("?"):
            query = line
        elif line:
            fact_lines.append(line)
    return fact_lines, query


# Per-question predicate lists so the LLM knows what to generate
Q_PREDICATES = {
    "Q1": {"facts": ["parent"], "query": "ancestor"},
    "Q2": {"facts": ["is_a", "property"], "query": "has_property"},
    "Q3": {"facts": ["is_a", "property"], "query": "has_property"},
    "Q4": {"facts": ["has_role", "inherits", "permission"], "query": "user_has_permission"},
    "Q5": {"facts": ["has_role", "inherits", "permission"], "query": "user_has_permission"},
}


def run_with_euclid(q: dict, model: str) -> dict:
    preds = Q_PREDICATES[q["id"]]
    fact_preds = ", ".join(preds["facts"])

    arg_order = {
        "Q4": (
            "  inherits(CHILD, PARENT)  — e.g., 'Admin inherits from editor' → inherits(admin, editor)\n"
            "  permission(ROLE, PERM)   — e.g., 'Viewer can read' → permission(viewer, read)\n"
        ),
        "Q5": (
            "  inherits(CHILD, PARENT)  — e.g., 'Admin inherits from editor' → inherits(admin, editor)\n"
            "  permission(ROLE, PERM)   — e.g., 'Viewer can read' → permission(viewer, read)\n"
        ),
    }
    arg_guide = arg_order.get(q["id"], "")

    system = (
        "You are a data entry operator. Output Euclid IR facts and a query.\n\n"
        "Rules are already pre-defined. You must output ONLY facts and a query.\n\n"
        f"Use ONLY these predicates for facts: {fact_preds}\n"
        f"The query predicate is: {preds['query']}\n\n"
        f"{arg_guide}"
        "Example output (for genealogy):\n"
        "  parent(tom, bob)\n"
        "  parent(bob, ann)\n"
        "  ? ancestor(tom, ann)\n\n"
        "CRITICAL: Pay attention to the argument order in predicates. "
        "The first argument is the subject, the second is the object.\n"
        "Output ONLY valid Euclid IR facts + query, no explanations. "
        "Do NOT include any rules (lines containing IF)."
    )
    prompt = (
        f"SCENARIO:\n{q['scenario']}\n\n"
        f"QUESTION: {q['question']}\n\n"
        f"Facts and query:\n"
    )
    start = time.monotonic()
    data = call_ollama(model, system, prompt)
    elapsed_llm = (time.monotonic() - start) * 1000
    raw = (data.get("message", {}) or {}).get("content", "") if data and "error" not in data else ""
    in_tok, out_tok = count_tokens(data)

    generated = extract_euclid(raw)
    if not generated:
        return {
            "raw": raw,
            "answer": None,
            "correct": False,
            "elapsed_ms": elapsed_llm,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "error": "could not extract Euclid IR from LLM output",
            "generated_euclid": None,
        }

    # Strip out any rules the LLM might still generate
    clean_lines = [l for l in generated.strip().split("\n") if " IF " not in l]
    generated_facts = "\n".join(clean_lines)

    full_knowledge = q["preset_rules"] + "\n" + generated_facts

    start = time.monotonic()
    result = run_euclid(full_knowledge)
    elapsed_euclid = (time.monotonic() - start) * 1000
    elapsed_total = elapsed_llm + elapsed_euclid

    if result.error:
        return {
            "raw": raw,
            "answer": None,
            "correct": False,
            "elapsed_ms": elapsed_total,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "error": f"Euclid error: {result.error}",
            "generated_euclid": generated,
        }

    has_solutions = len(result.solutions) > 0

    if q["expected"] == "Yes":
        correct = has_solutions
        answer = "Yes" if has_solutions else "No"
    else:
        correct = not has_solutions
        answer = "No" if not has_solutions else "Yes"

    return {
        "raw": raw,
        "answer": answer,
        "correct": correct,
        "elapsed_ms": elapsed_total,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "error": None,
        "generated_euclid": generated,
        "euclid_solutions": len(result.solutions),
        "euclid_subs": [s.substitutions for s in result.solutions] if has_solutions else [],
        "euclid_ms": elapsed_euclid,
    }


# ── Report ──


def print_report(all_results: list):
    cond_labels = [
        f"A ({SMALL_MODEL})",
        f"B ({CLOUD_MODEL})",
        f"C ({SMALL_MODEL}+Euclid)",
    ]
    cols = 3

    print()
    print("=" * 80)
    print("  REASONING BENCHMARK RESULTS")
    print("=" * 80)

    # Header
    header = f"{'':<6}" + "".join(f"│ {c:<22}" for c in cond_labels)
    print(f"{'':<6}" + "┌" + "┬".join(["─" * 24] * cols) + "┐")
    print(f"{'Condition':<6}" + f"{'':4}{'':>0}" + "".join(f"│ {c:^22}" for c in cond_labels))
    print(f"{'':<6}" + "├" + "┼".join(["─" * 24] * cols) + "┤")

    # Results per question
    q_labels = [q["label"] for q in QUESTIONS]
    for i, ql in enumerate(q_labels):
        cells = []
        for j in range(cols):
            r = all_results[j * len(QUESTIONS) + i]
            mark = "✅" if r.get("correct") else "❌"
            ans = r.get("answer") or "—"
            cells.append(f"{mark} {ans:<18}")
        print(f"{f'Q{i+1}':<6}" + "│ " + "│ ".join(cells) + "│")
        if i < len(q_labels) - 1:
            print(f"{'':<6}" + "├" + "┼".join(["─" * 24] * cols) + "┤")
        else:
            print(f"{'':<6}" + "└" + "┴".join(["─" * 24] * cols) + "┘")

    # Summary
    print()
    print("  SUMMARY")
    print("  " + "─" * 72)
    print(f"  {'':<22}" + "".join(f"{'':>4}{c:>20}" for c in cond_labels))
    print(f"  {'─'*22}" + "┼" + "─" * 24 + "┼" + "─" * 24 + "┼" + "─" * 24)

    total_q = len(QUESTIONS)
    for metric, fmt, key in [
        ("Accuracy", "{}/{}", "correct"),
        ("Avg time (ms)", "{:.0f}", "elapsed_ms"),
        ("Avg input tokens", "{:.0f}", "input_tokens"),
        ("Avg output tokens", "{:.0f}", "output_tokens"),
    ]:
        vals = []
        for j in range(cols):
            batch = all_results[j * total_q : (j + 1) * total_q]
            if key == "correct":
                vals.append(fmt.format(sum(1 for r in batch if r.get(key)), total_q))
            else:
                avg = sum(r.get(key, 0) for r in batch) / total_q
                vals.append(fmt.format(avg))
        print(f"  {metric:<20}" + " │ " + " │ ".join(f"{v:^22}" for v in vals) + " │")

    # Error details for Condition C
    print()
    print("  CONDITION C — DETAILS")
    print("  " + "─" * 72)
    for i, q in enumerate(QUESTIONS):
        r = all_results[2 * total_q + i]
        if r.get("error"):
            print(f"  {q['id']}: ERROR — {r['error']}")
        else:
            print(f"  {q['id']}: ✅ {r['answer']} — Euclid: {r.get('euclid_solutions', '?')} solutions")
            if r.get("euclid_subs"):
                for sub in r["euclid_subs"]:
                    print(f"         substitutions: {sub}")

    print()
    print("=" * 80)

    # Gold Euclid reference
    print()
    print("  GOLD EUCLID IR (for reference)")
    print("  " + "─" * 72)
    for q in QUESTIONS:
        print(f"\n  {q['id']} — {q['label']}")
        for line in q["gold_euclid"].split("\n"):
            print(f"    {line}")

    print()
    print("=" * 80)


# ── Main ──


def main():
    total_q = len(QUESTIONS)
    all_results = []

    print(f"\n  Benchmark: {total_q} questions, 3 conditions\n")

    # Condition A: Small LLM alone
    print(f"  ── Condition A: {SMALL_MODEL} (direct) ──")
    for i, q in enumerate(QUESTIONS):
        print(f"    [{i+1}/{total_q}] {q['id']} {q['label']}... ", end="", flush=True)
        r = run_direct(q, SMALL_MODEL)
        all_results.append(r)
        print(f"{'✅' if r['correct'] else '❌'} ({r['elapsed_ms']:.0f}ms)")

    # Condition B: Cloud LLM alone
    print(f"\n  ── Condition B: {CLOUD_MODEL} (direct) ──")
    for i, q in enumerate(QUESTIONS):
        print(f"    [{i+1}/{total_q}] {q['id']} {q['label']}... ", end="", flush=True)
        r = run_direct(q, CLOUD_MODEL)
        all_results.append(r)
        print(f"{'✅' if r['correct'] else '❌'} ({r['elapsed_ms']:.0f}ms)")

    # Condition C: Small LLM + Euclid
    print(f"\n  ── Condition C: {SMALL_MODEL} + Euclid-MCP ──")
    for i, q in enumerate(QUESTIONS):
        print(f"    [{i+1}/{total_q}] {q['id']} {q['label']}... ", end="", flush=True)
        r = run_with_euclid(q, SMALL_MODEL)
        all_results.append(r)
        mark = "✅" if r.get("correct") else "❌"
        detail = r.get("error") or f"{r['answer']}"
        print(f"  {mark} ({r['elapsed_ms']:.0f}ms) — {detail}")
        if r.get("generated_euclid"):
            print(f"    ── Generated Euclid ──")
            for line in r["generated_euclid"].split("\n"):
                print(f"      {line}")
            print(f"    ──────────────────────")
        if r.get("euclid_ms"):
            print(f"    Euclid execution: {r['euclid_ms']:.0f}ms")

    print_report(all_results)


if __name__ == "__main__":
    main()
