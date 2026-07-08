"""
RBAC Benchmark at scale: 1,000 users, ~1,000 facts, 200+ permissions.
Tests whether LLMs hallucinate when data is too large to track.
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

# ── KB generator ──


def build_kb() -> tuple[str, str, dict]:
    """Generate the full knowledge base and return (full_kb, scenario_desc, metadata)."""
    role_hierarchy = [
        ("admin", "manager"),
        ("manager", "developer"),
        ("developer", "editor"),
        ("editor", "viewer"),
    ]

    role_permissions = {
        "viewer": ["read_doc", "read_report"],
        "editor": ["write_doc", "edit_comment"],
        "developer": ["create_repo", "push_code"],
        "manager": ["approve_pr", "manage_team"],
        "admin": ["delete_repo", "manage_billing", "manage_users"],
        "auditor": ["read_logs", "view_audit_trail"],
        "operator": ["deploy", "restart_service", "monitor"],
    }

    user_ranges = {
        "admin": (1, 30),
        "manager": (31, 100),
        "developer": (101, 300),
        "editor": (301, 500),
        "viewer": (501, 800),
        "auditor": (801, 900),
        "operator": (901, 1000),
    }

    direct_grants_raw = [
        (15, "delete_repo"),
        (50, "read_logs"),
        (105, "deploy"),
        (222, "manage_billing"),
        (340, "push_code"),
        (415, "write_doc"),
        (555, "approve_pr"),
        (610, "read_logs"),
        (750, "deploy"),
        (834, "view_audit_trail"),
        (45, "manage_team"),
        (180, "delete_repo"),
        (275, "restart_service"),
        (370, "create_repo"),
        (460, "approve_pr"),
        (520, "push_code"),
        (680, "read_logs"),
        (810, "deploy"),
        (925, "manage_billing"),
        (990, "restart_service"),
    ]

    # ── Build Euclid KB ──
    lines = []
    lines.append("# ── Role hierarchy ──")
    for parent, child in role_hierarchy:
        lines.append(f"inherits({parent}, {child})")
    lines.append("")
    lines.append("# ── Role permissions ──")
    for role, perms in role_permissions.items():
        for p in perms:
            lines.append(f"permission({role}, {p})")
    lines.append("")
    lines.append("# ── Rules ──")
    lines.append("role_has_permission($r, $p) IF permission($r, $p)")
    lines.append(
        "role_has_permission($r, $p) IF inherits($r, $sub) "
        "AND role_has_permission($sub, $p)"
    )
    lines.append(
        "user_has_permission($u, $p) IF has_role($u, $r) "
        "AND role_has_permission($r, $p)"
    )
    lines.append(
        "user_has_permission($u, $p) IF direct_grant($u, $p)"
    )
    lines.append("")
    lines.append("# ── User-role assignments ──")
    for role, (start, end) in user_ranges.items():
        for uid in range(start, end + 1):
            lines.append(f"has_role(user_{uid:04d}, {role})")
    lines.append("")
    lines.append("# ── Direct grants ──")
    for uid, perm in direct_grants_raw:
        lines.append(f"direct_grant(user_{uid:04d}, {perm})")

    full_kb = "\n".join(lines)

    # ── Build scenario description for LLM ──
    sc = []
    sc.append("We have a role-based access control system with 1,000 users.\n")
    sc.append("ROLE HIERARCHY (inheritance):")
    for parent, child in role_hierarchy:
        sc.append(f"  {parent} inherits from {child}")
    sc.append("")
    sc.append("ROLE PERMISSIONS (base, before inheritance):")
    for role, perms in role_permissions.items():
        perm_list = ", ".join(perms)
        sc.append(f"  {role}: {perm_list}")
    sc.append("")
    grp_list = ", ".join(
        role_hierarchy[0] + tuple(r for r, _ in role_hierarchy)
    )
    sc.append(
        "A role gets all permissions assigned directly to it, "
        "plus all permissions of roles it inherits from."
    )
    sc.append("")
    sc.append("USER-ROLE DISTRIBUTION (users are named user_0001 to user_1000):")
    for role, (start, end) in user_ranges.items():
        sc.append(f"  user_{start:04d} to user_{end:04d}: {role} ({end-start+1} users)")
    sc.append("")
    sc.append("Some users also have DIRECT GRANTS (additional permissions "
              "independent of their role). There are 20 such grants.")

    scenario = "\n".join(sc)

    # ── Metadata for question answers ──
    by_role = {}
    for role, (start, end) in user_ranges.items():
        by_role[role] = list(range(start, end + 1))

    grants = {}
    for uid, perm in direct_grants_raw:
        grants.setdefault(perm, []).append(uid)

    meta = {
        "by_role": by_role,
        "grants": grants,
        "role_hierarchy": role_hierarchy,
        "role_permissions": role_permissions,
        "user_ranges": user_ranges,
    }

    return full_kb, scenario, meta


# ── Answer helpers (compute ground truth from KB metadata) ──


def _all_ancestors(role: str, hierarchy: list[tuple[str, str]]) -> list[str]:
    result = [role]
    for parent, child in hierarchy:
        if parent == role:
            result.extend(_all_ancestors(child, hierarchy))
    return result


def _role_has_perm(role: str, perm: str, hierarchy, role_perms) -> bool:
    ancestors = _all_ancestors(role, hierarchy)
    for a in ancestors:
        if perm in role_perms.get(a, []):
            return True
    return False


def _users_with_perm(perm: str, meta) -> list[int]:
    users = []
    for role, uids in meta["by_role"].items():
        if _role_has_perm(role, perm, meta["role_hierarchy"], meta["role_permissions"]):
            users.extend(uids)
    users.extend(meta["grants"].get(perm, []))
    return sorted(set(users))


KB_FULL, SCENARIO, META = build_kb()


# ── Questions ──

QUESTIONS = [
    {
        "id": "Q1",
        "label": "Count users with delete_repo",
        "question": (
            "Exactly how many users have the 'delete_repo' permission? "
            "Count carefully considering role inheritance and direct grants. "
            "Answer with a single number."
        ),
        "expected_type": "number",
        "ground_truth": len(_users_with_perm("delete_repo", META)),
        "expected_query": "? user_has_permission($who, delete_repo)",
    },
    {
        "id": "Q2",
        "label": "Specific user: can user_0142 push_code?",
        "question": (
            "Can user_0142 push_code? "
            "Trace their role and all inherited permissions. "
            "Answer with Yes or No."
        ),
        "expected_type": "yesno",
        "ground_truth": "Yes" if _role_has_perm(
            "developer", "push_code", META["role_hierarchy"], META["role_permissions"]
        ) else "No",
        "expected_query": "? user_has_permission(user_0142, push_code)",
    },
    {
        "id": "Q3",
        "label": "Count users with deploy",
        "question": (
            "Exactly how many users have the 'deploy' permission? "
            "Count carefully considering role inheritance and direct grants. "
            "Answer with a single number."
        ),
        "expected_type": "number",
        "ground_truth": len(_users_with_perm("deploy", META)),
        "expected_query": "? user_has_permission($who, deploy)",
    },
    {
        "id": "Q4",
        "label": "Specific user: can user_0834 read_logs?",
        "question": (
            "Can user_0834 read_logs? "
            "Trace their role and all inherited permissions. "
            "Answer with Yes or No."
        ),
        "expected_type": "yesno",
        "ground_truth": "Yes" if _role_has_perm(
            "auditor", "read_logs", META["role_hierarchy"], META["role_permissions"]
        ) else "No",
        "expected_query": "? user_has_permission(user_0834, read_logs)",
    },
    {
        "id": "Q5",
        "label": "Specific user (direct grant): can user_0222 manage_billing?",
        "question": (
            "Can user_0222 manage_billing? "
            "user_0222 is a developer. The 'manage_billing' permission belongs to the admin role. "
            "Check if there is any direct grant or other path. Answer with Yes or No."
        ),
        "expected_type": "yesno",
        "ground_truth": "Yes",  # direct_grant(user_0222, manage_billing)
        "expected_query": "? user_has_permission(user_0222, manage_billing)",
    },
]


# ── Ollama ──


def call_ollama(model: str, system: str, prompt: str, timeout: int = 300) -> dict | None:
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


def count_tokens(data: dict | None) -> tuple[int, int]:
    if data is None:
        return (0, 0)
    return (data.get("prompt_eval_count", 0), data.get("eval_count", 0))


def extract_number(text: str) -> int | None:
    m = re.search(r'(?:\bANSWER\s*:\s*)?(\d+)', text)
    if m:
        return int(m.group(1))
    return None


def extract_yesno(text: str) -> str | None:
    m = re.search(r'ANSWER\s*:\s*(Yes|No)', text, re.IGNORECASE)
    if m:
        return m.group(1).capitalize()
    m = re.search(r'\b(Yes|No)\b', text)
    if m:
        return m.group(1).capitalize()
    return None


def extract_euclid(text: str) -> str | None:
    lines = text.strip().split("\n")
    euclid_lines = []
    in_fence = False
    for line in lines:
        s = line.strip()
        if s.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            euclid_lines.append(line)
    if not euclid_lines:
        for line in lines:
            s = line.strip()
            if s.startswith("?") or s.startswith("?"):
                euclid_lines.append(line)
                break
    return "\n".join(euclid_lines).strip() if euclid_lines else None


# ── Conditions ──


def run_direct(q: dict, model: str) -> dict:
    is_yesno = q["expected_type"] == "yesno"

    if is_yesno:
        system = (
            "You manage a large RBAC system with 1,000 users. "
            "Answer concisely. End with 'ANSWER: Yes' or 'ANSWER: No'."
        )
        prompt = (
            f"SCENARIO:\n{SCENARIO}\n\n"
            f"QUESTION: {q['question']}\n\n"
            f"REASONING:\n"
        )
    else:
        system = (
            "You manage a large RBAC system with 1,000 users. "
            "Answer concisely with a single number. "
            "Think step by step, then end with 'ANSWER: <number>'."
        )
        prompt = (
            f"SCENARIO:\n{SCENARIO}\n\n"
            f"QUESTION: {q['question']}\n\n"
            f"REASONING:\n"
        )

    start = time.monotonic()
    data = call_ollama(model, system, prompt)
    elapsed = (time.monotonic() - start) * 1000
    raw = (data.get("message", {}) or {}).get("content", "") if data and "error" not in data else ""
    in_tok, out_tok = count_tokens(data)

    if is_yesno:
        answer = extract_yesno(raw)
        correct = (answer or "").lower() == q["ground_truth"].lower()
    else:
        answer = extract_number(raw)
        correct = answer == q["ground_truth"]

    return {
        "raw": raw,
        "answer": str(answer) if answer is not None else None,
        "correct": correct,
        "elapsed_ms": elapsed,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "error": data.get("error") if data else "no response",
    }


def run_with_euclid(q: dict, model: str) -> dict:
    system = (
        "You formulate queries for a logical reasoning engine (Euclid-IR). "
        "Given a scenario, output a SINGLE Euclid query line.\n\n"
        "Query format:\n"
        "  ? user_has_permission(USER, PERM)     — for a specific user\n"
        "  ? user_has_permission($who, PERM)     — to list all users\n\n"
        "Output ONLY the query line, nothing else."
    )
    prompt = (
        f"SCENARIO:\n{SCENARIO}\n\n"
        f"QUESTION: {q['question']}\n\n"
        f"Query:\n"
    )
    start = time.monotonic()
    data = call_ollama(model, system, prompt)
    elapsed_llm = (time.monotonic() - start) * 1000
    raw = (data.get("message", {}) or {}).get("content", "") if data and "error" not in data else ""
    in_tok, out_tok = count_tokens(data)

    query_line = extract_euclid(raw)
    if not query_line:
        return {
            "raw": raw,
            "answer": None,
            "correct": False,
            "elapsed_ms": elapsed_llm,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "error": "could not extract query",
            "generated_query": None,
        }

    full_kb = KB_FULL + "\n" + query_line

    start = time.monotonic()
    result = reason(knowledge=full_kb, max_solutions=2000)
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
            "generated_query": query_line,
        }

    is_yesno = q["expected_type"] == "yesno"

    subs_list = [s.substitutions for s in result.solutions]

    if is_yesno:
        has_sol = len(result.solutions) > 0
        answer = "Yes" if has_sol else "No"
        correct = answer.lower() == q["ground_truth"].lower()
    else:
        distinct_users = set()
        for sub in subs_list:
            for v in sub.values():
                distinct_users.add(str(v))
        answer = len(distinct_users) if distinct_users else len(result.solutions)
        correct = answer == q["ground_truth"]

    return {
        "raw": raw,
        "answer": str(answer),
        "correct": correct,
        "elapsed_ms": elapsed_total,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "error": None,
        "generated_query": query_line,
        "euclid_solutions": len(result.solutions),
        "euclid_distinct": answer,
        "euclid_subs": subs_list,
    }


# ── Report ──


def print_report(all_results: list, total_q: int):
    conds = [
        ("A", f"{SMALL_MODEL} (direct)"),
        ("B", f"{CLOUD_MODEL} (direct)"),
        ("C", f"{SMALL_MODEL} + Euclid"),
    ]

    print()
    print("=" * 100)
    print("  RBAC AT SCALE — 1,000 users, 1,000+ facts")
    print("=" * 100)

    # Table
    widths = [33, 33, 33]
    print(f"\n  {'':<6}" + "┌" + "┬".join(["─" * w for w in widths]) + "┐")
    print(f"  {'Cond':<6}" + "".join(f"│ {c[0]:>3} — {c[1]:<24}" for c in conds))
    print(f"  {'':<6}" + "├" + "┼".join(["─" * w for w in widths]) + "┤")

    for i, q in enumerate(QUESTIONS):
        cells = []
        for j in range(3):
            r = all_results[j * total_q + i]
            mark = "✅" if r.get("correct") else "❌"
            ans = r.get("answer") or "?"
            gt = str(q["ground_truth"])
            cells.append(f"{mark} ans={ans:<6} gt={gt:<6}")
        print(f"  {q['id']:<6}" + "│ " + " │ ".join(cells) + " │")
        if i < total_q - 1:
            print(f"  {'':<6}" + "├" + "┼".join(["─" * w for w in widths]) + "┤")
        else:
            print(f"  {'':<6}" + "└" + "┴".join(["─" * w for w in widths]) + "┘")

    # Summary
    print()
    for metric, fmt, key in [
        ("Accuracy", "{}/{}", "correct"),
        ("Avg time (ms)", "{:.0f}", "elapsed_ms"),
        ("Avg input tokens", "{:.0f}", "input_tokens"),
        ("Avg output tokens", "{:.0f}", "output_tokens"),
        ("KB size", "{} facts", None),
    ]:
        if key is None:
            facts = len(KB_FULL.split("\n"))
            print(f"  {metric:<20}" + " │ " + " │ ".join(f"{facts:^32}" for _ in range(3)) + " │")
        elif key == "correct":
            vals = []
            for j in range(3):
                batch = all_results[j * total_q : (j + 1) * total_q]
                n = sum(1 for r in batch if r.get(key))
                vals.append(fmt.format(n, total_q))
            print(f"  {metric:<20}" + " │ " + " │ ".join(f"{v:^32}" for v in vals) + " │")
        else:
            vals = []
            for j in range(3):
                batch = all_results[j * total_q : (j + 1) * total_q]
                avg = sum(r.get(key, 0) for r in batch) / total_q
                vals.append(fmt.format(avg))
            print(f"  {metric:<20}" + " │ " + " │ ".join(f"{v:^32}" for v in vals) + " │")

    # Condition C detail
    print()
    print("  CONDITION C — Detail")
    print("  " + "─" * 92)
    for i, q in enumerate(QUESTIONS):
        r = all_results[2 * total_q + i]
        print(f"\n  {q['id']}: {q['label']}")
        print(f"  Generated query: {r.get('generated_query', '?')}")
        print(f"  Euclid: {r.get('answer', '?')} "
              f"(GT={q['ground_truth']}, {r.get('euclid_solutions', 0)} solutions)")
        if r.get("error"):
            print(f"  ERROR: {r['error']}")

    # Condition A/B raw answers for hard questions
    print()
    print("  RAW ANSWERS — Q1 (counting delete_repo)")
    for j, (label, _) in enumerate(conds):
        r = all_results[j * total_q + 0]
        raw = r.get("raw", "")
        first_line = raw.split("\n")[0][:120] if raw else "(empty)"
        print(f"  {label}: first line = {first_line}")
        print(f"  {label}: full answer = {r.get('answer', '?')} "
              f"(GT={QUESTIONS[0]['ground_truth']}, {'✅' if r['correct'] else '❌'})")

    print()
    print("=" * 100)


# ── Main ──


def main():
    total_q = len(QUESTIONS)
    all_results = []

    kb_facts = len(KB_FULL.split("\n"))
    print(f"\n  RBAC @ Scale: {total_q} questions, {kb_facts} facts in KB\n")

    # Condition A
    print(f"  ── A: {SMALL_MODEL} (direct) ──")
    for i, q in enumerate(QUESTIONS):
        print(f"    [{i+1}/{total_q}] {q['id']} {q['label']}... ", end="", flush=True)
        r = run_direct(q, SMALL_MODEL)
        all_results.append(r)
        print(f"{'✅' if r['correct'] else '❌'} ans={r.get('answer','?')} gt={q['ground_truth']} ({r['elapsed_ms']:.0f}ms)")

    # Condition B
    print(f"\n  ── B: {CLOUD_MODEL} (direct) ──")
    for i, q in enumerate(QUESTIONS):
        print(f"    [{i+1}/{total_q}] {q['id']} {q['label']}... ", end="", flush=True)
        r = run_direct(q, CLOUD_MODEL)
        all_results.append(r)
        print(f"{'✅' if r['correct'] else '❌'} ans={r.get('answer','?')} gt={q['ground_truth']} ({r['elapsed_ms']:.0f}ms)")

    # Condition C
    print(f"\n  ── C: {SMALL_MODEL} + Euclid-MCP ──")
    for i, q in enumerate(QUESTIONS):
        print(f"    [{i+1}/{total_q}] {q['id']} {q['label']}... ", end="", flush=True)
        r = run_with_euclid(q, SMALL_MODEL)
        all_results.append(r)
        mark = "✅" if r.get("correct") else "❌"
        err = r.get("error", "")
        print(f"  {mark} ans={r.get('answer','?')} gt={q['ground_truth']} ({r['elapsed_ms']:.0f}ms) {err}")

    print_report(all_results, total_q)


if __name__ == "__main__":
    main()
