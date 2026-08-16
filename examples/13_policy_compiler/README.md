# Example 13 — Policy Compiler: document → Euclid-IR → KB

The first example in this repo that starts from a **source document in natural
language** and derives a Euclid-IR knowledge base from it, then loads and uses
that KB with Euclid-MCP.

The point of the exercise is to show the full ingestion path for real-world
normative sources (company policies, regulations, security baselines) instead
of hand-written KBs:

```
source/*.md ──stage 1──► sections (deterministic)
sections ──stage 2──► Euclid IR (optional LLM via Ollama)
fragments ──stage 3──► assemble + check_kb ──► kb/*.euclid (committed)
kb/*.euclid ──► reason / explain / what_if / diagnose
```

## What is in here

| Path | Content |
|---|---|
| `source/access_control_policy.md` | Fictional access-control policy (POL-SEC-042): environments, role levels, deployment rights, data classification, emergency access, derogations. |
| `source/ai_act_art6_3.md` | Official extract of the EU AI Act (Reg. (UE) 2024/1689), art. 6(3): the high-risk derogation, its conditions a–d, and the profiling counter-exception (art. 3(1)(4)). |
| `extract/document_model.py` | Stage 1: deterministic Markdown parser → sections with stable ids (ASCII slugs, diacritics normalized). |
| `extract/compiler_prompt.md` | The formalization prompt used in stage 2 (Euclid-IR output contract, `UNSAFE` sentinel). |
| `extract/llm_extractor.py` | Stage 2: minimal Ollama client (stdlib only, `temperature 0`), optional. |
| `extract/extract.py` | Orchestrator: `compile` (stages 1→2→3) and `check` (validate a KB + report). |
| `kb/access_control_policy.euclid` | Committed, curated KB for the policy (6 rules, `SEC-*` ids). |
| `kb/ai_act_art6_3.euclid` | Committed, curated KB for the AI Act extract (8 rules, `AIACT-6-3-*` ids). |
| `kb/compilation_reports.md` | Compilation report (source, model, KB validation, rule ids). |
| `demo.py` | Runs the KBs through reason/explain/what_if/diagnose in both load modes. |

Every rule carries a `# RULE: <id>` (trailing, so the engine surfaces it) and a
`# src: <section>` anchor back to the source document.

## Quick start

```bash
# 1. Validate the KBs first (always check before reasoning)
python extract/extract.py check --kb kb/access_control_policy.euclid
python extract/extract.py check --kb kb/ai_act_art6_3.euclid

# 2. Reason over the policy KB (payload mode)
python demo.py
# 3. AI Act KB
python demo.py --kb ai_act
# 4. Same via file preload (EUCLID_KB_PATH), to mimic a server started with --kb-path
python demo.py --preload --query P2
```

## Regenerating the KBs from the sources (Ollama, optional)

`extract.py compile` runs the three stages. The LLM stage is **optional**:

- Ollama running → each section is formalized to Euclid IR; the assembled KB is
  validated with `check_kb` and written to `--out`.
- Ollama not reachable → every section is marked `UNSAFE: ollama unavailable`
  and no KB file is written. This keeps the example (and CI) runnable without a
  model; the committed KBs are the *curated* output of stage 4.

```bash
python extract/extract.py compile \
  --source source/access_control_policy.md \
  --out kb/access_control_policy.euclid \
  --model llama3.1:8b \
  --report kb/compilation_reports.md
```

Default model is `llama3.1:8b`; pass `--ollama-url` to change the endpoint
(e.g. to reach a cloud-backed model served through Ollama).

## Why two KBs

- **Policy** — shows typical RBAC/compliance reasoning: multi-hop rules with
  arithmetic thresholds, negation (`NOT`), and a denormalized flag.
- **AI Act art. 6(3)** — shows how to encode an official legal text: the
  derogation (primo comma), its conditions (letters a–d), the profiling
  counter-exception (ultimo comma: *always* high-risk). The demo then asks
  `high_risk($s)` over a small registry of AI systems.

## Design notes / engine constraints discovered

- **`==` is arithmetic only.** Euclid IR maps `==` to Prolog `=:=`; comparing
  atoms or unbound variables crashes the engine (`engine_error`). You cannot
  express atom equality in a rule. In `SEC-6-1` the *self-approval* requirement
  is therefore detected at event-ingestion time and materialized as the
  `self_approved/1` flag (a standard denormalized pattern), instead of
  `$approver == $u`.
- **Rule ids are trailing comments.** The parser captures `# RULE:` only at the
  end of the rule (last body line wins). Keep `# src:` *before* `# RULE:` on the
  same line so both anchors survive.
- **Every body predicate must be defined.** `check_kb` reports an *undefined
  predicate* as an error, so a rule may only call predicates that appear in a
  fact or in another rule head.
- **LLM stage is curated, never trusted.** The pipeline proposes; `check_kb`
  rejects; a human (stage 4) reviews `UNSAFE` sections. The committed KBs are
  that curated output.

## Extending to real official sources

- **AI Act (full)** — EUR-Lex text is freely reusable: point `--source` at a
  Markdown extract of more articles and recompile.
- **DISA STIG** — U.S. government work, public domain. The `parse_source()`
  dispatcher in `document_model.py` is the extension point for an XML parser
  (STIGs ship as XML/XCCDF).
- **CIS Benchmarks** — **copyrighted**: do not commit CIS PDF content. Use a
  generic mapper and keep only your derived rules/facts.
- **AWS best practices** — reuse the pattern with an "anagrafica" (registry)
  layer of your own resources.
