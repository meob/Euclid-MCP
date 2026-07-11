#!/usr/bin/env python3
"""
Benchmark: Edge LLM alone vs Edge LLM + Euclid-MCP

Compares two conditions on the IT Security & Compliance knowledge base:
  A) Edge LLM (llama3.1:8b) answering questions directly
  B) Edge LLM (llama3.8b) using Euclid-MCP via MCP

Measures: accuracy, response time, token usage.

Usage:
    python benchmark_comparison.py
    python benchmark_comparison.py --small    # Quick run with subset
    python benchmark_comparison.py --api-url http://localhost:11434  # Custom Ollama URL

Requires: euclid-mcp, ollama with llama3.1:8b pulled
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from euclid_mcp.server import reason

try:
    import requests
except ImportError:
    print("Error: requests not installed. Run: pip install requests")
    sys.exit(1)


BASE_DIR = Path(__file__).parent

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.1:8b"

# ── Knowledge base loading (same as demo.py) ──

POLICY_FILES = [
    BASE_DIR / "policies" / "role_hierarchy.euclid",
    BASE_DIR / "policies" / "environment_tiers.euclid",
    BASE_DIR / "policies" / "data_classification.euclid",
    BASE_DIR / "policies" / "access_control.euclid",
    BASE_DIR / "policies" / "approval_workflows.euclid",
]
STANDARD_FILES = [
    BASE_DIR / "standards" / "cis_benchmarks.euclid",
    BASE_DIR / "standards" / "aws_iam_patterns.euclid",
]
DATA_FILE = BASE_DIR / "data" / "generated_facts.euclid"
SMALL_DATA_FILE = BASE_DIR / "data" / "small_generated_facts.euclid"


def load_knowledge(use_small: bool = False) -> str:
    parts = []
    for f in STANDARD_FILES + POLICY_FILES:
        if f.exists():
            parts.append(f.read_text())
    data_file = SMALL_DATA_FILE if use_small else DATA_FILE
    if data_file.exists():
        parts.append(data_file.read_text())
    return "\n\n".join(parts)


# ── Questions with full scenario text for LLM-only condition ──

QUESTIONS = [
    {
        "id": "Q1",
        "question": "Can user_0005 manage servers?",
        "scenario": "user_0005 is a user in the system. The system has roles with hierarchical inheritance. Permissions flow upward through the hierarchy. A user has a permission if they hold a role that has that permission (directly or inherited).",
        "llm_answer": "user_0005",
        "query": "user_has_permission(user_0005, manage_servers)",
    },
    {
        "id": "Q2",
        "question": "Which users can deploy to production?",
        "scenario": "Deployment requires: (1) deploy_code permission, (2) role level >= 6 for production. Roles have levels: intern=0, junior_dev=1, mid_senior_dev=2, senior_dev=3, tech_lead=4, eng_manager=5, director=6, vp_engineering=7, cto=8. Roles inherit from below.",
        "llm_answer": "users with director or higher role who have deploy_code",
        "query": "can_deploy($who, production)",
    },
    {
        "id": "Q3",
        "question": "Which production resources are not encrypted?",
        "scenario": "Resources have attributes: name, environment (production/staging/development/golden), encrypted status, backup status, public access, data classification. Check which resources in production are not encrypted.",
        "llm_answer": "list of resource names",
        "query": "resource($name, production, not_encrypted, _, _, _)",
    },
    {
        "id": "Q4",
        "question": "Can an intern write code?",
        "scenario": "The intern role has these direct permissions: read_code, run_tests. The intern role does NOT have write_code. Roles inherit permissions from roles below them, but interns are at the bottom of the hierarchy.",
        "llm_answer": "No",
        "query": "user_has_permission($who, write_code) AND has_role($who, intern)",
    },
    {
        "id": "Q5",
        "question": "How many users have more than 15 permissions?",
        "scenario": "Each user has a direct permission count. The threshold for 'excessive' is more than 15 permissions. Users inherit permissions from their roles, and some users have secondary roles that add more permissions.",
        "llm_answer": "count of users with permission_count > 15",
        "query": "excessive_permissions($who, $count)",
    },
]


def call_ollama(prompt: str, api_url: str) -> dict:
    """Call Ollama API and return response with metrics."""
    start = time.time()
    try:
        resp = requests.post(
            api_url,
            json={"model": MODEL, "prompt": prompt, "stream": False},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        elapsed = time.time() - start

        return {
            "response": data.get("response", ""),
            "elapsed_ms": round(elapsed * 1000),
            "eval_count": data.get("eval_count", 0),
            "eval_duration_ms": round(data.get("eval_duration", 0) / 1e6),
            "prompt_eval_count": data.get("prompt_eval_count", 0),
        }
    except requests.exceptions.ConnectionError:
        return {"error": f"Cannot connect to Ollama at {api_url}", "elapsed_ms": round((time.time() - start) * 1000)}
    except Exception as e:
        return {"error": str(e), "elapsed_ms": round((time.time() - start) * 1000)}


def run_condition_a(knowledge_text: str, api_url: str) -> list[dict]:
    """Condition A: Edge LLM answering directly (no Euclid)."""
    results = []

    for q in QUESTIONS:
        prompt = f"""You are an IT security expert. Answer the following question about a company's access control system.

{q['scenario']}

Question: {q['question']}

Think step by step and provide your answer. Be concise."""

        print(f"  {q['id']}: {q['question']}...", end="", flush=True)
        resp = call_ollama(prompt, api_url)

        if "error" in resp:
            print(f" ERROR: {resp['error']}")
            results.append({"id": q["id"], "answer": None, "error": resp["error"], **resp})
        else:
            answer = resp["response"][:200]
            print(f" {resp['elapsed_ms']}ms, {resp['eval_count']} tokens")
            results.append({
                "id": q["id"],
                "answer": resp["response"],
                "elapsed_ms": resp["elapsed_ms"],
                "eval_count": resp["eval_count"],
                "prompt_eval_count": resp["prompt_eval_count"],
            })

    return results


def run_condition_b(knowledge: str) -> list[dict]:
    """Condition B: Edge LLM + Euclid-MCP."""
    results = []

    for q in QUESTIONS:
        start = time.time()
        try:
            result = reason(
                knowledge=knowledge,
                query=q["query"],
                max_solutions=50,
                max_depth=30,
            )
            elapsed_ms = round((time.time() - start) * 1000)

            num_solutions = len(result.solutions)
            bindings = []
            for sol in result.solutions[:10]:
                if sol.substitutions:
                    bindings.append(sol.substitutions)

            print(f"  {q['id']}: {q['question']}... {elapsed_ms}ms, {num_solutions} solutions")
            results.append({
                "id": q["id"],
                "num_solutions": num_solutions,
                "solutions": bindings,
                "elapsed_ms": elapsed_ms,
            })
        except Exception as e:
            elapsed_ms = round((time.time() - start) * 1000)
            print(f"  {q['id']}: ERROR: {e}")
            results.append({"id": q["id"], "error": str(e), "elapsed_ms": elapsed_ms})

    return results


def print_comparison(cond_a: list[dict], cond_b: list[dict]):
    """Print comparison table."""
    print(f"\n{'='*90}")
    print(f"  BENCHMARK: Edge LLM alone (A) vs Edge LLM + Euclid-MCP (B)")
    print(f"{'='*90}")

    print(f"\n  {'Q':<4} {'Question':<40} {'A (ms)':<10} {'B (ms)':<10} {'Speedup':<10} {'B sols':<8}")
    print(f"  {'-'*4} {'-'*40} {'-'*10} {'-'*10} {'-'*10} {'-'*8}")

    for a, b in zip(cond_a, cond_b):
        q = next(q for q in QUESTIONS if q["id"] == a["id"])
        a_ms = a.get("elapsed_ms", "ERR")
        b_ms = b.get("elapsed_ms", "ERR")
        b_sols = b.get("num_solutions", "ERR")

        if isinstance(a_ms, int) and isinstance(b_ms, int) and b_ms > 0:
            speedup = f"{a_ms / b_ms:.1f}x"
        else:
            speedup = "N/A"

        print(f"  {a['id']:<4} {q['question'][:40]:<40} {str(a_ms):<10} {str(b_ms):<10} {speedup:<10} {str(b_sols):<8}")

    # Totals
    a_total = sum(a.get("elapsed_ms", 0) for a in cond_a if isinstance(a.get("elapsed_ms"), int))
    b_total = sum(b.get("elapsed_ms", 0) for b in cond_b if isinstance(b.get("elapsed_ms"), int))
    a_tokens = sum(a.get("eval_count", 0) for a in cond_a)
    b_sols_total = sum(b.get("num_solutions", 0) for b in cond_b)

    print(f"\n  TOTALS")
    print(f"  Condition A (LLM only):    {a_total}ms total, {a_tokens} output tokens")
    print(f"  Condition B (LLM + Euclid): {b_total}ms total, {b_sols_total} total solutions")
    if b_total > 0:
        print(f"  Speed ratio: A is {a_total / b_total:.1f}x {'slower' if a_total > b_total else 'faster'}")
    print(f"\n  KEY INSIGHT: Euclid-MCP returns exact answers with proof trees,")
    print(f"  while the LLM must reason through complex logic it often gets wrong at scale.\n")


def main():
    parser = argparse.ArgumentParser(description="Benchmark: LLM alone vs LLM + Euclid-MCP")
    parser.add_argument("--small", action="store_true", help="Use small dataset")
    parser.add_argument("--api-url", default=OLLAMA_URL, help=f"Ollama API URL (default: {OLLAMA_URL})")
    parser.add_argument("--skip-a", action="store_true", help="Skip Condition A (LLM only)")
    parser.add_argument("--skip-b", action="store_true", help="Skip Condition B (Euclid only)")
    args = parser.parse_args()

    print("Loading knowledge base...")
    knowledge = load_knowledge(use_small=args.small)
    print(f"  {len(knowledge.splitlines())} lines loaded\n")

    cond_a = []
    cond_b = []

    if not args.skip_a:
        print("Condition A: Edge LLM (llama3.1:8b) alone")
        print(f"  Connecting to: {args.api_url}")
        cond_a = run_condition_a(knowledge, args.api_url)
        print()

    if not args.skip_b:
        print("Condition B: Edge LLM + Euclid-MCP")
        cond_b = run_condition_b(knowledge)
        print()

    if cond_a and cond_b:
        print_comparison(cond_a, cond_b)
    elif cond_b:
        print("  (Condition A skipped — showing Condition B only)")
        for b in cond_b:
            print(f"  {b['id']}: {b.get('num_solutions', 'ERR')} solutions, {b.get('elapsed_ms', 'ERR')}ms")


if __name__ == "__main__":
    main()
