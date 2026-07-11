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

from euclid_mcp.server import reason


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


def print_result(result: dict) -> None:
    """Pretty-print a single question result."""
    print(f"\n{'='*70}")
    print(f"  {result['id']}: {result['question']}")
    print(f"  Category: {result['category']} | {result['description']}")
    print(f"{'='*70}")
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
        # Show first 3 and summary
        for i, sol in enumerate(result["solutions"][:3], 1):
            subs = sol["substitutions"]
            bindings = ", ".join(f"{k}={v}" for k, v in subs.items()) if subs else "{}"
            print(f"  Solution {i}: {bindings}")
        print(f"  ... and {result['num_solutions'] - 3} more solutions")


def main():
    parser = argparse.ArgumentParser(description="IT Security & Compliance Demo")
    parser.add_argument("--question", help="Run specific question (e.g. Q3)")
    parser.add_argument("--small", action="store_true", help="Use small dataset for quick testing")
    parser.add_argument("--max-solutions", type=int, default=50, help="Max solutions per query")
    args = parser.parse_args()

    print("Loading knowledge base...")
    knowledge = load_knowledge(use_small=args.small)
    fact_count = knowledge.count("\n") + 1
    print(f"  Loaded ~{fact_count} lines of knowledge")

    if args.question:
        q = next((q for q in QUESTIONS if q["id"] == args.question), None)
        if not q:
            print(f"Unknown question: {args.question}")
            print(f"Available: {[q['id'] for q in QUESTIONS]}")
            sys.exit(1)
        questions = [q]
    else:
        questions = QUESTIONS

    print(f"\nRunning {len(questions)} questions...\n")

    results = []
    total_time = 0
    for q in questions:
        result = run_question(knowledge, q, max_solutions=args.max_solutions)
        results.append(result)
        total_time += result["elapsed_ms"]
        print_result(result)

    # Summary
    print(f"\n{'='*70}")
    print(f"  SUMMARY")
    print(f"{'='*70}")
    print(f"  Questions: {len(results)}")
    print(f"  Total time: {total_time}ms")
    print(f"  Avg time per question: {total_time // len(results)}ms")
    non_empty = sum(1 for r in results if r["num_solutions"] > 0)
    print(f"  Questions with results: {non_empty}/{len(results)}")
    total_solutions = sum(r["num_solutions"] for r in results)
    print(f"  Total solutions found: {total_solutions}")


if __name__ == "__main__":
    main()
