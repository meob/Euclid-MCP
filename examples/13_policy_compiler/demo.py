#!/usr/bin/env python3
"""
Policy Compiler — Demo Script (example 13)

Demonstrates the full "document -> Euclid-IR KB -> reasoning" flow:
  * two committed KBs compiled from source documents
    - kb/access_control_policy.euclid  (fictional access-control policy, POL-SEC-042)
    - kb/ai_act_art6_3.euclid          (EU AI Act, art. 6(3), official text extract)
  * both supported loading modes:
    - payload:  knowledge=<KB text> passed to every tool (default)
    - preload:  EUCLID_KB_PATH / --kb-path file preload (--preload flag)
  * reason / explain / what_if / diagnose, with rule-id citations.

Usage:
    python demo.py                      # all queries, payload mode, policy KB
    python demo.py --kb ai_act          # all queries, AI Act KB
    python demo.py --preload            # demonstrate file preload (EUCLID_KB_PATH)
    python demo.py --query P2           # run a single query id

Requires: euclid-mcp (pip install -e . from the project root)
"""

import argparse
import os
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent

KB_FILES = {
    "policy": BASE_DIR / "kb" / "access_control_policy.euclid",
    "ai_act": BASE_DIR / "kb" / "ai_act_art6_3.euclid",
}

# ── Reason queries ──

QUERIES = {
    "policy": [
        {"id": "P1", "question": "Who can deploy to production? (POL-SEC-042 §4)",
         "query": "can_deploy($who, production)"},
        {"id": "P2", "question": "Who can deploy to staging? (§4)",
         "query": "can_deploy($who, staging)"},
        {"id": "P3", "question": "Who can access customer_db (confidential)? (§5)",
         "query": "can_access_data($who, customer_db)"},
        {"id": "P4", "question": "Who can access pii_db (secret)? (§5)",
         "query": "can_access_data($who, pii_db)"},
        {"id": "P5", "question": "Who gets emergency access during an incident? (§6)",
         "query": "emergency_access($who)"},
        {"id": "P6", "question": "Who has a clearance-derogation on pii_db? (§7)",
         "query": "deroga_access_data($who, pii_db)"},
        {"id": "P7", "question": "Who has no system access at all? (§1)",
         "query": "no_access($who)"},
    ],
    "ai_act": [
        {"id": "A1", "question": "Which AI systems are classified high-risk? (art. 6(3))",
         "query": "high_risk($s)"},
        {"id": "A2", "question": "Which systems qualify for the deroga (not high-risk)? (primo comma)",
         "query": "deroga_applicabile($s)"},
        {"id": "A3", "question": "Which systems are ALWAYS high-risk because of profiling? (ultimo comma)",
         "query": "always_high_risk($s)"},
    ],
}

# ── Explain / diagnose / what-if ──

EXPLAIN_QUERIES = {
    "policy": [
        {"id": "E1", "question": "Why can alice deploy to production?",
         "query": "can_deploy(alice, production)"},
    ],
    "ai_act": [
        {"id": "E2", "question": "Why is hr_screening_01 high-risk despite a deroga condition?",
         "query": "high_risk(hr_screening_01)"},
    ],
}

DIAGNOSE_QUERIES = {
    "policy": [
        {"id": "D1", "mode": "why_not", "question": "Why can't carol (tech_lead) deploy to production?",
         "query": "can_deploy(carol, production)"},
    ],
}

WHAT_IF_SCENARIOS = {
    "policy": [
        {"id": "W1", "question": "What if the production threshold rises from 6 to 7?",
         "query": "can_deploy($who, production)",
         "modifications": "- deploy_requires_level(production, 6)\n+ deploy_requires_level(production, 7)"},
        {"id": "W2", "question": "What if carol's self-approval flag is removed?",
         "query": "emergency_access($who)",
         "modifications": "- self_approved(carol)"},
    ],
    "ai_act": [
        {"id": "W3", "question": "What if resume_rank_02 starts profiling candidates?",
         "query": "deroga_applicabile($s)",
         "modifications": "+ performs_profiling(resume_rank_02)"},
    ],
}


def _import_server():
    # Import lazily so the --preload env var can be set before the server module
    # (and its preloaded-KB bootstrap) is loaded.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from euclid_mcp.server import diagnose, explain, reason, what_if

    return reason, explain, what_if, diagnose


def run(label, fn, **kwargs):
    start = time.time()
    res = fn(**kwargs)
    return res, round((time.time() - start) * 1000)


def print_solutions(sol):
    if not sol:
        print("  (no solutions)")
    seen = set()
    shown = 0
    for s in sol:
        if s.substitutions:
            key = tuple(sorted(s.substitutions.items()))
        else:
            key = ()
        if key in seen:
            continue
        seen.add(key)
        shown += 1
        if s.substitutions:
            print("  - " + ", ".join(f"{k}={v}" for k, v in s.substitutions.items()))
        else:
            print("  - {}")
    if shown == 0:
        print("  (no solutions)")


def main():
    parser = argparse.ArgumentParser(description="Policy Compiler Demo (example 13)")
    parser.add_argument("--kb", choices=list(KB_FILES), default="policy",
                        help="which committed KB to reason over")
    parser.add_argument("--query", help="run a single query id (e.g. P2, A1, W3)")
    parser.add_argument("--preload", action="store_true",
                        help="load the KB via EUCLID_KB_PATH file preload instead of payload")
    parser.add_argument("--max-solutions", type=int, default=10)
    args = parser.parse_args()

    kb_path = KB_FILES[args.kb]

    # --preload: set EUCLID_KB_PATH before the server module is imported so the
    # KB is preloaded once at import time; tools then receive no payload.
    if args.preload:
        os.environ["EUCLID_KB_PATH"] = str(kb_path)
        mode_label = f"file preload (EUCLID_KB_PATH={kb_path.name})"
    else:
        mode_label = "payload (knowledge=<KB text>)"
    reason, explain, what_if, diagnose = _import_server()

    def load_knowledge():
        if args.preload:
            return None
        return kb_path.read_text(encoding="utf-8")

    print(f"KB: {kb_path.name} | load mode: {mode_label}\n")

    # 1. Reason
    print("=" * 70)
    print("  REASON")
    print("=" * 70)
    for q in QUERIES[args.kb]:
        if args.query and q["id"] != args.query:
            continue
        res, ms = run(reason, reason, knowledge=load_knowledge(), query=q["query"],
                      max_solutions=args.max_solutions)
        print(f"\n  {q['id']}: {q['question']}")
        print(f"  query: {q['query']}  ({ms}ms)")
        print_solutions(res.solutions)

    # 2. Explain
    print("\n" + "=" * 70)
    print("  EXPLAIN (rule-id citations)")
    print("=" * 70)
    for q in EXPLAIN_QUERIES[args.kb]:
        if args.query and q["id"] != args.query:
            continue
        res, ms = run(explain, explain, knowledge=load_knowledge(), query=q["query"],
                      max_solutions=args.max_solutions)
        print(f"\n  {q['id']}: {q['question']}  ({ms}ms)")
        for e in res.explanations:
            for step in e.steps:
                print(f"    * {step}")

    # 3. Diagnose
    print("\n" + "=" * 70)
    print("  DIAGNOSE")
    print("=" * 70)
    for q in DIAGNOSE_QUERIES.get(args.kb, []):
        if args.query and q["id"] != args.query:
            continue
        res, ms = run(diagnose, diagnose, knowledge=load_knowledge(), query=q["query"],
                      mode=q["mode"], max_solutions=args.max_solutions)
        print(f"\n  {q['id']}: {q['question']}  (mode={q['mode']}, {ms}ms)")
        print(f"  conclusion: {res.conclusion}")
        for f in res.findings:
            print(f"    - [{f.type}] {f.predicate}: {f.detail}")

    # 4. What-if
    print("\n" + "=" * 70)
    print("  WHAT-IF")
    print("=" * 70)
    for q in WHAT_IF_SCENARIOS[args.kb]:
        if args.query and q["id"] != args.query:
            continue
        base = kb_path.read_text(encoding="utf-8") if not args.preload else None
        res, ms = run(what_if, what_if, base_knowledge=base, query=q["query"],
                      modifications=q["modifications"], max_solutions=args.max_solutions)
        print(f"\n  {q['id']}: {q['question']}  ({ms}ms)")
        print(f"  modification: {q['modifications']}")
        print(f"  before={res.before_count} after={res.after_count} ({res.delta})")
        print(f"  conclusion: {res.conclusion}")


if __name__ == "__main__":
    main()
