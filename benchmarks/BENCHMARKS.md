# Benchmarks — Euclid-MCP

Two benchmarks compare **llama3.1:8b** (small local), **qwen3-coder:480b-cloud** (cloud), and **llama3.1:8b + Euclid-MCP** on logical reasoning tasks.

## 1. `reasoning_benchmark.py` — Small-scale reasoning

**5 tasks** (genealogy, taxonomy, RBAC) with **5–15 facts** each.  
Tests whether LLMs alone can handle small, self-contained logical problems.

| Q | Task | GT | A (8B) | B (480B cloud) | C (8B + Euclid) |
|---|------|----|--------|----------------|-----------------|
| Q1 | Genealogy (deep chain) | Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| Q2 | Taxonomy (property inheritance) | Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| Q3 | Taxonomy (negative inference) | No | ✅ No | ✅ No | ✅ No |
| Q4 | RBAC (permission inheritance) | Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| Q5 | RBAC (negative) | No | ✅ No | ✅ No | ✅ No |
| **Accuracy** | | | **5/5** | **5/5** | **5/5** |
| Avg time | | | 4 772 ms | 2 180 ms | 2 542 ms |
| Avg tokens (in / out) | | | 131 / 118 | 130 / 133 | 254 / 46 |

**Conclusion**: With small KBs, all three conditions are equivalent in accuracy.  
Euclid-MCP matches LLM accuracy, but at slightly higher input tokens (254 vs 131).  
Execution time is comparable (2.5s vs 4.8s / 2.2s).

## 2. `rbac_1000.py` — RBAC at scale

**1 000 synthetic users**, 7 roles with hierarchy, 17 base permissions, 20 direct grants — **1 053 facts** total.  
Questions ask for user counts by permission, specific yes/no queries, and cross-permission intersections.  
This is the scale where LLM working memory fails.

| Q | Task | GT | A (8B) | B (480B cloud) | C (8B + Euclid) |
|---|------|----|--------|----------------|-----------------|
| Q1 | Count users with `delete_repo` | 31 | ❌ 1 | ❌ 1 | ✅ 31 |
| Q2 | Can user_0142 `push_code`? | Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| Q3 | Count users with `deploy` | 103 | ❌ 100 | ❌ 901 | ✅ 103 |
| Q4 | Can user_0834 `read_logs`? | Yes | ❌ No | ✅ Yes | ✅ Yes |
| Q5 | Can user_0222 `manage_billing`? (direct grant) | Yes | ✅ Yes | ❌ No | ✅ Yes |
| **Accuracy** | | | **2/5** | **2/5** | **5/5** |
| Avg time | | | 6 966 ms | 3 695 ms | 963 ms |
| Avg tokens (in / out) | | | 386 / 165 | 435 / 212 | 421 / 12 |

**Conclusion**: At scale, LLMs alone hallucinate systematically — both 8B and 480B cloud give wrong counts and miss explicit facts. Euclid-MCP delivers exact answers every time, while being **faster** (963ms vs 6 966ms) and **more token-efficient** (12 vs 165 output tokens) because the LLM generates only a simple query instead of fallacious reasoning.

## Key takeaway

| KB size | LLM alone | LLM + Euclid-MCP |
|---------|-----------|------------------|
| Small (5–50 facts) | ✅ Sufficient | ⚠️ Comparable accuracy, higher input tokens |
| Large (1 000+ facts) | ❌ Hallucinates | ✅ Exact deduction |

**Euclid-MCP proves its value at scale.** When facts fit in an LLM's context window, the overhead of a deterministic engine is rarely justified. When they don't — above a few hundred facts — Euclid-MCP delivers exact answers while LLMs of any size hallucinate systematically.
