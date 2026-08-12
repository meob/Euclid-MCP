# Benchmark 1 — Reasoning at small scale: LLM alone vs LLM + Euclid-MCP

- **Script:** `benchmarks/reasoning_benchmark.py`
- **Run date:** July 2026 (results captured when the LLM comparison suite was built; re-running requires the Ollama + cloud endpoints)
- **Environment:** Python 3.12, Ollama API (`http://localhost:11434`), cloud model via provider

## What it measures

Whether a small local LLM alone is enough for small, self-contained logical
problems, compared with a large cloud LLM and with a small LLM paired with
Euclid-MCP.

## Conditions

| Id | Condition |
|----|-----------|
| A | `llama3.1:8b` (small local model, alone) |
| B | `qwen3-coder:480b-cloud` (cloud model, alone) |
| C | `llama3.1:8b` + Euclid-MCP |

## Method

5 tasks with **5–15 facts** each: genealogy (deep chain), taxonomy (property
inheritance), taxonomy (negative inference), RBAC (permission inheritance),
RBAC (negative). Each task is a yes/no question with a known ground truth.

Metrics: accuracy (correct yes/no), average response time, average tokens
(input / output).

## Results

| Q | Task | GT | A (8B) | B (480B cloud) | C (8B + Euclid) |
|---|------|----|--------|----------------|-----------------|
| Q1 | Genealogy (deep chain) | Yes | Yes | Yes | Yes |
| Q2 | Taxonomy (property inheritance) | Yes | Yes | Yes | Yes |
| Q3 | Taxonomy (negative inference) | No | No | No | No |
| Q4 | RBAC (permission inheritance) | Yes | Yes | Yes | Yes |
| Q5 | RBAC (negative) | No | No | No | No |
| **Accuracy** | | | **5/5** | **5/5** | **5/5** |
| Avg time | | | 4 772 ms | 2 180 ms | 2 542 ms |
| Avg tokens (in / out) | | | 131 / 118 | 130 / 133 | 254 / 46 |

## Conclusion

At small scale all three conditions are **equivalent in accuracy**. Euclid-MCP
adds input tokens (254 vs 131) because the facts and rules are sent to the
engine, while execution time stays comparable.

## Consequent implementation choices

No engine changes. The result informs product guidance (README and model
instructions): a deterministic engine is only justified when facts no longer
fit reliable LLM context, i.e. above a few hundred facts.
