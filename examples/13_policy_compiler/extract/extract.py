"""Policy compiler: document -> Euclid-IR KB (stages 1-3 + compilation report).

Two modes:

    python extract.py compile --source source/access_control_policy.md \
        --out kb/access_control_policy.euclid [--model llama3.1:8b] [--report ...]
        Stage 1  parse the source into sections (deterministic, no LLM)
        Stage 2  formalize each section to Euclid IR via Ollama (optional)
        Stage 3  assemble the KB, validate it with check_kb, write files

    python extract.py check --kb kb/access_control_policy.euclid [--report ...]
        Validate a committed/curated KB and emit the compilation report.

Ollama is OPTIONAL. When it is not reachable, `compile` marks every section
`UNSAFE: ollama unavailable` and writes no KB file: the committed KBs in `kb/`
keep the example runnable and testable without a model.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from document_model import DocumentModel, parse_source  # noqa: E402
from llm_extractor import (  # noqa: E402
    DEFAULT_MODEL,
    DEFAULT_OLLAMA_URL,
    ExtractionResult,
    OllamaClient,
    extract_section,
    load_prompt,
)

from euclid_mcp.language import parse  # noqa: E402
from euclid_mcp.validation import run_check_kb as _run_check_kb  # noqa: E402

PROMPT_PATH = Path(__file__).resolve().parent / "compiler_prompt.md"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def build_kb_header(doc: DocumentModel, source: Path, model: str | None) -> list[str]:
    lines = [
        f"# KB compilata da: {doc.title}",
        f"# Sorgente: {source}",
        f"# Compilata con il flusso documento -> Euclid-IR -> check_kb "
        f"(model: {model or 'curatela manuale'}).",
        "# Ogni regola porta: # RULE: <id> e # src: <sezione del documento sorgente>.",
    ]
    return lines


def assemble_kb(doc: DocumentModel, results: list[ExtractionResult]) -> str:
    header = build_kb_header(doc, doc.source, DEFAULT_MODEL)
    chunks: list[str] = [*header, ""]
    for sec, res in zip(doc.sections, results, strict=True):
        if not res.fragments:
            continue
        chunks.append(f"# --- Sezione: {sec.id} ---")
        chunks.extend(res.fragments)
        chunks.append("")
    return "\n".join(chunks).rstrip() + "\n"


def collect_unsafe(results: list[ExtractionResult]) -> list[tuple[str, str]]:
    return [(r.section_id, r.unsafe_reason or "no model output") for r in results if not r.modeled]


def write_report(
    path: Path | None,
    doc: DocumentModel,
    model: str | None,
    kb_text: str | None,
    results: list[ExtractionResult] | None,
) -> None:
    lines: list[str] = []
    unsafe: list[tuple[str, str]] = []
    lines.append("# Compilation report")
    lines.append("")
    lines.append(f"- Source: `{doc.source}`")
    lines.append(f"- Title: {doc.title}")
    lines.append(f"- Model: {model or 'n/a (no LLM stage)'}")
    lines.append(
        f"- Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}"
    )
    lines.append("")

    if results is not None:
        modeled = sum(1 for r in results if r.modeled)
        unsafe = collect_unsafe(results)
        lines.append(f"Sections modeled: {modeled}/{len(results)}")
        lines.append("")
        lines.append("| Section | Modeled | Unsafe reason |")
        lines.append("|---|---|---|")
        for r in results:
            lines.append(f"| {r.section_id} | {'yes' if r.modeled else 'no'} | {r.unsafe_reason or ''} |")
        lines.append("")

    if kb_text is not None:
        check = _run_check_kb(kb_text)
        lines.append("## KB validation (check_kb)")
        lines.append("")
        lines.append(f"- Valid: {check.valid}")
        lines.append(f"- Facts: {check.facts_count}, Rules: {check.rules_count}, Predicates: {check.predicates_count}")
        lines.append(f"- Elapsed: {check.elapsed_ms:.1f} ms")
        if check.errors:
            lines.append("- Errors:")
            for e in check.errors:
                lines.append(f"  - {e.message}")
        if check.warnings:
            lines.append("- Warnings:")
            for w in check.warnings:
                lines.append(f"  - {w.message}")
        lines.append("")

        kb = parse(kb_text)
        if kb.rule_ids:
            lines.append("Rules (id):")
            for idx in sorted(kb.rule_ids):
                lines.append(f"- {kb.rule_ids[idx]}")
            lines.append("")

    if unsafe:
        lines.append("## Unsafe / human review required")
        lines.append("")
        for section_id, reason in unsafe:
            lines.append(f"- {section_id}: {reason}")
        lines.append("")

    body = "\n".join(lines).rstrip() + "\n"
    if path is None:
        print(body)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        print(f"Report written to {path}")


def cmd_compile(args: argparse.Namespace) -> int:
    doc = parse_source(Path(args.source))
    prompt = load_prompt(PROMPT_PATH)
    client = OllamaClient(args.ollama_url)

    if not client.available():
        print("Ollama not reachable: skipping the LLM stage.")
        print("Marking every section UNSAFE; no KB file will be written.")
        results = [
            ExtractionResult(section_id=s.id, modeled=False, fragments=[], unsafe_reason="ollama unavailable")
            for s in doc.sections
        ]
        write_report(
            Path(args.report) if args.report else None,
            doc,
            args.model,
            kb_text=None,
            results=results,
        )
        return 1

    print(f"Model: {args.model}  (Ollama at {args.ollama_url})")
    results: list[ExtractionResult] = []
    for sec in doc.sections:
        print(f"  section {sec.id} ...", end=" ", flush=True)
        res = extract_section(client, prompt, sec.id, sec.title, sec.text, args.model)
        results.append(res)
        print("modeled" if res.modeled else f"UNSAFE: {res.unsafe_reason}")

    kb_text = assemble_kb(doc, results)
    check = _run_check_kb(kb_text)
    if not check.valid:
        print("Assembled KB is NOT valid; not writing the KB file.")
        write_report(
            Path(args.report) if args.report else None,
            doc,
            args.model,
            kb_text=kb_text,
            results=results,
        )
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(kb_text, encoding="utf-8")
    print(f"KB written to {out} ({check.facts_count} facts, {check.rules_count} rules)")

    if args.report:
        write_report(Path(args.report), doc, args.model, kb_text=kb_text, results=results)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    kb_path = Path(args.kb)
    kb_text = kb_path.read_text(encoding="utf-8")
    check = _run_check_kb(kb_text)
    print(
        f"KB {kb_path}: valid={check.valid}, {check.facts_count} facts, "
        f"{check.rules_count} rules, {check.predicates_count} predicates, "
        f"{check.elapsed_ms:.1f} ms"
    )
    for e in check.errors:
        print(f"  ERROR: {e.message}")
    for w in check.warnings:
        print(f"  WARN:  {w.message}")

    if args.report:
        doc = DocumentModel(source=kb_path, title=kb_path.stem)
        write_report(Path(args.report), doc, model=None, kb_text=kb_text, results=None)
    return 0 if check.valid else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="extract.py",
        description="Compile a normative document into a Euclid-IR knowledge base.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_compile = sub.add_parser("compile", help="document -> Euclid-IR KB")
    p_compile.add_argument("--source", required=True, help="Markdown source document")
    p_compile.add_argument("--out", required=True, help="output .euclid KB file")
    p_compile.add_argument("--model", default=DEFAULT_MODEL)
    p_compile.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    p_compile.add_argument("--report", help="optional markdown report path")

    p_check = sub.add_parser("check", help="validate a KB and emit its report")
    p_check.add_argument("--kb", required=True, help="existing .euclid KB file")
    p_check.add_argument("--report", help="optional markdown report path")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "compile":
        raise SystemExit(cmd_compile(args))
    raise SystemExit(cmd_check(args))


if __name__ == "__main__":
    main()
