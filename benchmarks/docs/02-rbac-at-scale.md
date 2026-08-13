# Benchmark 2 — RBAC at scale: LLM alone vs LLM + Euclid-MCP

- **Script:** `benchmarks/rbac_1000.py`
- **Run date:** July 2026 (results captured when the LLM comparison suite was built; re-running requires the Ollama + cloud endpoints)
- **Environment:** Python 3.12, Ollama API (`http://localhost:11434`), cloud model via provider

## What it measures

Whether LLMs hallucinate when the data is too large to track reliably, and
whether Euclid-MCP keeps producing exact answers at that scale.

## Conditions

| Id | Condition |
|----|-----------|
| A | `llama3.1:8b` (small local model, alone) |
| B | `qwen3-coder:480b-cloud` (cloud model, alone) |
| C | `llama3.1:8b` + Euclid-MCP |

## Method

A synthetic RBAC domain: **1 000 users**, 7 roles with a hierarchy, 17 base
permissions, 20 direct grants — **1 053 facts** total. Five questions mix
counts (users with a permission), specific yes/no checks, and cross-permission
intersections.

Metrics: accuracy, average response time, average tokens (input / output).

## Results

| Q | Task | GT | A (8B) | B (480B cloud) | C (8B + Euclid) |
|---|------|----|--------|----------------|-----------------|
| Q1 | Count users with `delete_repo` | 31 | 1 | 1 | 31 |
| Q2 | Can `user_0142` `push_code`? | Yes | Yes | Yes | Yes |
| Q3 | Count users with `deploy` | 103 | 100 | 901 | 103 |
| Q4 | Can `user_0834` `read_logs`? | Yes | No | Yes | Yes |
| Q5 | Can `user_0222` `manage_billing`? (direct grant) | Yes | Yes | No | Yes |
| **Accuracy** | | | **2/5** | **2/5** | **5/5** |
| Avg time | | | 6 966 ms | 3 695 ms | 963 ms |
| Avg tokens (in / out) | | | 386 / 165 | 435 / 212 | 421 / 12 |

## Conclusion

At scale both LLMs **hallucinate systematically**: wrong counts, missed direct
grants, and — in the worst case — counts that exceed the true population.
Euclid-MCP answers **exactly, every time**, and is both faster (963 ms vs
6 966 ms) and more token-efficient (12 vs 165 output tokens), because the LLM
only generates a simple query instead of fallacious reasoning.

## Consequent implementation choices

No engine changes. This benchmark is the core evidence for Euclid-MCP's value
proposition and is referenced from the README.
