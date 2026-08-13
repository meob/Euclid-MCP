# Euclid-MCP Examples

Euclid-MCP is a hybrid cognitive architecture: a lightweight LLM describes the world in facts, and a deterministic engine performs the actual deduction. The LLM never needs to reason — it only needs to describe.


## Real-world examples

After installing Euclid-MCP (via pip or from source with an active virtualenv):

```bash
# Genealogy — recursive family tree reasoning
python examples/01_genealogy.py

# RBAC — Role-Based Access Control
python examples/02_rbac.py

# Classification — biological taxonomy
python examples/03_classification.py

# Business rules — loan eligibility
python examples/04_loan_eligibility.py

# Compliance auditor — cloud resource policy enforcement
python examples/05_compliance_auditor/auditor.py

# Loan officer — CSV-driven eligibility with detailed breakdown
python examples/06_loan_eligibility/loan_officer.py

# IT Security & Compliance — multi-layer policy reasoning (rule IDs + explanations)
python examples/07_it_security_compliance/demo.py --small

# Cluedo Detective — solve Cluedo mysteries with deductive elimination
python examples/08_cluedo/cluedo.py

# LLM vs Euclid-MCP — interactive side-by-side comparison
python examples/10_llm_vs_euclid/demo.py

# KB validation — check_kb on valid and broken knowledge bases
python examples/12_kb_check/demo.py
```

Each example runs a complete reasoning session and prints solutions with proof trees — no LLM required.  
Use them as templates for integrating Euclid-MCP into your own agents.

First easy examples show the reasoning capability of Euclid-MCP.

Examples 05 and 06 demonstrate a **data-driven agent workflow**:
- Read external data (JSON, CSV) that simulates API/CRM exports
- Convert structured data to Euclid facts in Python
- Load policy rules from `.euclid` files (separated from data)
- Call `reason()` for deduction
- Format results into human-readable reports with proof chains

This mirrors how a real agent would work: collect data, describe it as facts, let Euclid reason, and present the results.

### Example 07: IT Security & Compliance

The most advanced example demonstrating:
- **3-layer architecture**: Standards (CIS, AWS IAM) → Company Policies → Data Facts
- **Arithmetic comparisons**: `$days > 90` for stale access detection
- **Multi-line rules**: Complex policies split across lines
- **Conjunction queries**: Combining multiple predicates
- **Negative tests**: Verifying empty results for invalid access patterns
- **Rule IDs**: policy rules tagged with `# RULE: <id>` and cited in proofs
- **Explanations**: `--mode explain` renders readable reasoning steps with
  rule ID citations for a full audit trail

```bash
# Quick test (30 users, 50 resources, ~577 facts)
python3 examples/07_it_security_compliance/demo.py --small

# Full dataset (200 users, 300 resources, ~3,869 facts)
python3 examples/07_it_security_compliance/demo.py

# Natural-language explanations with rule ID citations
python3 examples/07_it_security_compliance/demo.py --small --mode explain
```

### Example 10: LLM vs Euclid-MCP

Interactive side-by-side comparison: a plain LLM vs the same LLM augmented with Euclid-MCP's reasoning engine. Same model, same knowledge base, dramatically different results.

```bash
# Requires: Ollama running with llama3.1:8b pulled
ollama pull llama3.1:8b

# Run the interactive demo
python3 examples/10_llm_vs_euclid/demo.py

# Options
python3 examples/10_llm_vs_euclid/demo.py --model llama3.1:8b   # Explicit model
python3 examples/10_llm_vs_euclid/demo.py --bot-a-only           # Plain LLM only
python3 examples/10_llm_vs_euclid/demo.py --bot-b-only           # Euclid bot only
python3 examples/10_llm_vs_euclid/demo.py --verbose              # Show proof chains

# Scripted mode — run preset questions in sequence, then exit (ideal for demos)
python3 examples/10_llm_vs_euclid/demo.py --scripted
python3 examples/10_llm_vs_euclid/demo.py --scripted --pause     # Enter between questions
python3 examples/10_llm_vs_euclid/demo.py --scripted --delay 2   # 2s pause between questions

# Regenerate the condensed markdown digest of the KB (Bot A's context), persisted
# in kb_markdown.md so the same digest can be reviewed/versioned
python3 examples/10_llm_vs_euclid/generate_kb_markdown.py
```

- **Bot A** (plain): entire KB injected as markdown context — like RAG, grows with history
- **Bot B** (Euclid): short system prompt + tool calling via `reason`, `diagnose`, `what_if`, `check_kb`
- Language-agnostic: speak in any language, the engine translates to Euclid-IR automatically
- Demonstrates proof trees, deterministic answers, and query diagnosis vs LLM hallucination

