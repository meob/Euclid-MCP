#!/usr/bin/env python3
"""
IT Security & Compliance — Demo Script

Demonstrates Euclid-MCP reasoning over a realistic IT security knowledge base.
Loads 3 layers of rules (CIS benchmarks, company policies, RBAC data) and
answers security/compliance questions with proof trees.

Usage:
    python demo.py                    # Run all questions
    python demo.py --question Q3      # Run specific question
    python demo.py --small            # Use small subset for quick testing

Requires: euclid-mcp (pip install -e . from the project root)
"""

import argparse
import sys
import time
from pathlib import Path

# Add parent project to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from euclid_mcp.server import diagnose, reason, what_if


# ── Knowledge base files (loaded in order) ──

BASE_DIR = Path(__file__).parent

POLICY_FILES = [
    # Layer 2: Company policies
    BASE_DIR / "policies" / "role_hierarchy.euclid",
    BASE_DIR / "policies" / "environment_tiers.euclid",
    BASE_DIR / "policies" / "data_classification.euclid",
    BASE_DIR / "policies" / "access_control.euclid",
    BASE_DIR / "policies" / "approval_workflows.euclid",
]

STANDARD_FILES = [
    # Layer 1: Standards
    BASE_DIR / "standards" / "cis_benchmarks.euclid",
    BASE_DIR / "standards" / "aws_iam_patterns.euclid",
]

DATA_FILE = BASE_DIR / "data" / "generated_facts.euclid"
SMALL_DATA_FILE = BASE_DIR / "data" / "small_generated_facts.euclid"

# ── Questions ──

QUESTIONS = [
    {
        "id": "Q1",
        "question": "Can user_0005 manage servers?",
        "query": "user_has_permission(user_0005, manage_servers)",
        "category": "single-hop",
        "description": "Simple permission check through role hierarchy",
    },
    {
        "id": "Q2",
        "question": "Which roles can deploy code to production?",
        "query": "can_deploy($who, production)",
        "category": "multi-hop",
        "description": "Role level + permission + environment tier",
    },
    {
        "id": "Q3",
        "question": "Which users can access secret data?",
        "query": "can_access_resource($who, $res) AND resource($res, _, _, _, _, secret)",
        "category": "counting",
        "description": "User clearance >= resource classification",
    },
    {
        "id": "Q4",
        "question": "Can a tech_lead deploy to golden environment?",
        "query": "can_deploy($who, golden) AND has_role($who, tech_lead)",
        "category": "multi-role",
        "description": "Users with tech_lead role who can deploy to golden (via higher role)",
    },
    {
        "id": "Q5",
        "question": "Which users have stale access (over 90 days)?",
        "query": "stale_access($who)",
        "category": "temporal",
        "description": "AWS IAM pattern: stale access detection",
    },
    {
        "id": "Q6",
        "question": "Which users violate separation of duties?",
        "query": "violates_separation_of_duties($who)",
        "category": "cross-policy",
        "description": "Deploy + approve conflict, or create + assign conflict",
    },
    {
        "id": "Q7",
        "question": "Which production resources are not encrypted?",
        "query": "resource($name, production, not_encrypted, _, _, _)",
        "category": "resource-audit",
        "description": "CIS compliance: unencrypted production resources",
    },
    {
        "id": "Q8",
        "question": "Can an intern write code?",
        "query": "user_has_permission($who, write_code) AND has_role($who, intern)",
        "category": "negative",
        "description": "Interns only have read_code — should be empty",
    },
    {
        "id": "Q9",
        "question": "Which users have excessive permissions (more than 15)?",
        "query": "excessive_permissions($who, $count)",
        "category": "threshold",
        "description": "AWS IAM pattern: least privilege violation",
    },
    {
        "id": "Q10",
        "question": "Which S3 buckets in production are not encrypted?",
        "query": "resource($name, production, not_encrypted, _, _, _) AND resource_type($name, s3)",
        "category": "combined",
        "description": "CIS + resource type intersection",
    },
]

# ── Diagnostic questions (for diagnose mode) ──

DIAGNOSE_QUESTIONS = [
    {
        "id": "Q11",
        "question": "Why does eng_0008 have manage_servers permission?",
        "query": "user_has_permission(eng_0008, manage_servers)",
        "mode": "why",
        "description": "Explain why a sysadmin has manage_servers",
    },
    {
        "id": "Q12",
        "question": "Why doesn't eng_0002 (intern) have deploy_code permission?",
        "query": "user_has_permission(eng_0002, deploy_code)",
        "mode": "why_not",
        "description": "Explain why an intern lacks deploy permission",
    },
    {
        "id": "Q13",
        "question": "What would eng_0002 need to deploy code?",
        "query": "user_has_permission(eng_0002, deploy_code)",
        "mode": "what_needs",
        "description": "What is needed for intern to gain deploy permission",
    },
]

# ── What-if scenarios ──

WHAT_IF_SCENARIOS = [
    {
        "id": "W1",
        "question": "What if eng_0002 (intern) is promoted to senior_dev?",
        "query": "user_has_permission(eng_0002, deploy_code)",
        "modifications": "- has_role(eng_0002, intern)\n+ has_role(eng_0002, senior_dev)",
        "description": "Impact of promoting intern to senior_dev",
    },
    {
        "id": "W2",
        "question": "What if a new encrypted production database is added?",
        "query": "resource($name, production, encrypted, _, _, _) AND resource_type($name, database)",
        "modifications": "+ resource(new_db, production, encrypted, db_team, 2026-07-01, database) AND resource_type(new_db, database)",
        "description": "Impact of adding compliant resource",
    },
    {
        "id": "W3",
        "question": "What if ops_0001 (helpdesk) gets the sysadmin role?",
        "query": "user_has_permission(ops_0001, manage_servers)",
        "modifications": "+ has_role(ops_0001, sysadmin)",
        "description": "Impact of giving helpdesk the sysadmin role",
    },
]


def load_knowledge(use_small: bool = False) -> str:
    """Load and combine all knowledge base files."""
    parts = []

    # Layer 1: Standards
    for f in STANDARD_FILES:
        if f.exists():
            parts.append(f"# ── {f.stem} ──")
            parts.append(f.read_text())

    # Layer 2: Policies
    for f in POLICY_FILES:
        if f.exists():
            parts.append(f"# ── {f.stem} ──")
            parts.append(f.read_text())

    # Layer 3: Data
    data_file = SMALL_DATA_FILE if use_small else DATA_FILE
    if data_file.exists():
        parts.append(f"# ── {data_file.stem} ──")
        parts.append(data_file.read_text())

    return "\n\n".join(parts)


def run_question(knowledge: str, q: dict, max_solutions: int = 50) -> dict:
    """Run a single question and return the result."""
    start = time.time()
    result = reason(
        knowledge=knowledge,
        query=q["query"],
        max_solutions=max_solutions,
        max_depth=30,
    )
    elapsed = time.time() - start

    return {
        "id": q["id"],
        "question": q["question"],
        "category": q["category"],
        "description": q["description"],
        "num_solutions": len(result.solutions),
        "solutions": [
            {
                "substitutions": sol.substitutions,
                "proof_type": sol.proof.type if sol.proof else None,
            }
            for sol in result.solutions
        ],
        "elapsed_ms": round(elapsed * 1000),
    }


def run_diagnose(knowledge: str, q: dict, max_solutions: int = 50) -> dict:
    """Run diagnose on a single question and return the result."""
    start = time.time()
    result = diagnose(
        knowledge=knowledge,
        query=q["query"],
        mode=q.get("mode", "why"),
        max_solutions=max_solutions,
        max_depth=30,
    )
    elapsed = time.time() - start

    return {
        "id": q["id"],
        "question": q["question"],
        "mode": q.get("mode", "why"),
        "description": q.get("description", ""),
        "holds": result.holds,
        "findings": [
            {"type": f.type, "predicate": f.predicate, "detail": f.detail}
            for f in result.findings
        ],
        "conclusion": result.conclusion,
        "num_solutions": len(result.solutions),
        "elapsed_ms": round(elapsed * 1000),
    }


def run_what_if(knowledge: str, q: dict, max_solutions: int = 50) -> dict:
    """Run what-if analysis on a single scenario and return the result."""
    start = time.time()
    result = what_if(
        base_knowledge=knowledge,
        modifications=q["modifications"],
        query=q["query"],
        max_solutions=max_solutions,
        max_depth=30,
    )
    elapsed = time.time() - start

    return {
        "id": q["id"],
        "question": q["question"],
        "description": q.get("description", ""),
        "modifications": result.modifications,
        "before_count": result.before_count,
        "after_count": result.after_count,
        "delta": result.delta,
        "conclusion": result.conclusion,
        "elapsed_ms": round(elapsed * 1000),
    }


def print_result(result: dict, mode: str = "reason") -> None:
    """Pretty-print a single question result."""
    print(f"\n{'='*70}")
    print(f"  {result['id']}: {result['question']}")
    if mode == "reason":
        print(f"  Category: {result['category']} | {result['description']}")
    else:
        print(f"  Mode: {result.get('mode', mode)} | {result.get('description', '')}")
    print(f"{'='*70}")

    if mode == "reason":
        print(f"  Solutions found: {result['num_solutions']} | Time: {result['elapsed_ms']}ms")
        if result["num_solutions"] == 0:
            print("  Answer: No match (empty result)")
        elif result["num_solutions"] <= 5:
            for i, sol in enumerate(result["solutions"], 1):
                subs = sol["substitutions"]
                proof = sol["proof_type"]
                if subs:
                    bindings = ", ".join(f"{k}={v}" for k, v in subs.items())
                    print(f"  Solution {i}: {bindings} (proof: {proof})")
                else:
                    print(f"  Solution {i}: {{}} (proof: {proof})")
        else:
            for i, sol in enumerate(result["solutions"][:3], 1):
                subs = sol["substitutions"]
                bindings = ", ".join(f"{k}={v}" for k, v in subs.items()) if subs else "{}"
                print(f"  Solution {i}: {bindings}")
            print(f"  ... and {result['num_solutions'] - 3} more solutions")

    elif mode == "diagnose":
        holds_str = "YES" if result["holds"] else "NO"
        print(f"  Holds: {holds_str} | Time: {result['elapsed_ms']}ms")
        if result["findings"]:
            print(f"  Findings ({len(result['findings'])}):")
            for f in result["findings"]:
                print(f"    - [{f['type']}] {f['predicate']}: {f['detail']}")
        print(f"  Conclusion: {result['conclusion']}")

    elif mode == "what-if":
        print(f"  Before: {result['before_count']} solution(s) | After: {result['after_count']} solution(s) | Time: {result['elapsed_ms']}ms")
        print(f"  Modification: {result['modifications']}")
        print(f"  Conclusion: {result['conclusion']}")


def main():
    parser = argparse.ArgumentParser(description="IT Security & Compliance Demo")
    parser.add_argument("--question", help="Run specific question (e.g. Q3)")
    parser.add_argument(
        "--mode",
        choices=["reason", "diagnose", "what-if"],
        default="reason",
        help="Tool to use: reason (default), diagnose, or what-if",
    )
    parser.add_argument(
        "--diagnose-mode",
        choices=["why", "why_not", "what_needs"],
        default=None,
        help="Override diagnose mode for --mode diagnose",
    )
    parser.add_argument("--small", action="store_true", help="Use small dataset for quick testing")
    parser.add_argument("--max-solutions", type=int, default=50, help="Max solutions per query")
    args = parser.parse_args()

    print("Loading knowledge base...")
    knowledge = load_knowledge(use_small=args.small)
    fact_count = knowledge.count("\n") + 1
    print(f"  Loaded ~{fact_count} lines of knowledge")

    # Select question set based on mode
    if args.mode == "diagnose":
        available = DIAGNOSE_QUESTIONS
    elif args.mode == "what-if":
        available = WHAT_IF_SCENARIOS
    else:
        available = QUESTIONS

    if args.question:
        q = next((q for q in available if q["id"] == args.question), None)
        if not q:
            print(f"Unknown question: {args.question}")
            print(f"Available: {[q['id'] for q in available]}")
            sys.exit(1)
        questions = [q]
    else:
        questions = available

    # Override diagnose mode if specified
    if args.mode == "diagnose" and args.diagnose_mode:
        for q in questions:
            q["mode"] = args.diagnose_mode

    print(f"\nRunning {len(questions)} questions [{args.mode}]...\n")

    results = []
    total_time = 0
    for q in questions:
        if args.mode == "diagnose":
            result = run_diagnose(knowledge, q, max_solutions=args.max_solutions)
        elif args.mode == "what-if":
            result = run_what_if(knowledge, q, max_solutions=args.max_solutions)
        else:
            result = run_question(knowledge, q, max_solutions=args.max_solutions)
        results.append(result)
        total_time += result["elapsed_ms"]
        print_result(result, mode=args.mode)

    # Summary
    print(f"\n{'='*70}")
    print(f"  SUMMARY")
    print(f"{'='*70}")
    print(f"  Questions: {len(results)} | Mode: {args.mode}")
    print(f"  Total time: {total_time}ms")
    print(f"  Avg time per question: {total_time // len(results)}ms")

    if args.mode == "reason":
        non_empty = sum(1 for r in results if r["num_solutions"] > 0)
        print(f"  Questions with results: {non_empty}/{len(results)}")
        total_solutions = sum(r["num_solutions"] for r in results)
        print(f"  Total solutions found: {total_solutions}")
    elif args.mode == "diagnose":
        holds_count = sum(1 for r in results if r["holds"])
        print(f"  Queries that hold: {holds_count}/{len(results)}")
    elif args.mode == "what-if":
        for r in results:
            print(f"  {r['id']}: {r['delta']} ({r['before_count']} -> {r['after_count']})")


if __name__ == "__main__":
    main()
