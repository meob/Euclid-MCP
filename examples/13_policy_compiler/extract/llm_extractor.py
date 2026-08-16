"""Stage 2 of the policy compiler: LLM formalization via Ollama (optional).

Turns one source section into Euclid IR using a local LLM. Pure stdlib
(`urllib`), so the example has zero extra dependencies. The LLM is OPTIONAL:
when Ollama is not available, `extract.py` falls back to a warning and a
`UNSAFE` entry for every section, and the committed KBs (already curated) keep
the pipeline runnable and testable without a model.

Model selection: default `llama3.1:8b`. Point `--model` at any model served by
Ollama (including cloud-backed models, e.g. via `ollama pull` of an
OpenAI-compatible served model). `--ollama-url` overrides the endpoint.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.1:8b"
TIMEOUT_SECONDS = 120

_EUCLID_BLOCK_RE = re.compile(r"```euclid\s*\n(.*?)```", re.DOTALL)
_UNSAFE_RE = re.compile(r"^\s*UNSAFE\s*:\s*(.+?)\s*$", re.MULTILINE)
_MODELED_RE = re.compile(r"SECTIONS-MODELED\s*:\s*(yes|no)\b", re.IGNORECASE)


@dataclass
class ExtractionResult:
    section_id: str
    modeled: bool
    fragments: list[str]  # Euclid IR lines (rules with # RULE: / # src:)
    unsafe_reason: str | None = None


class OllamaClient:
    """Minimal Ollama REST client (single request, no streaming)."""

    def __init__(self, base_url: str = DEFAULT_OLLAMA_URL) -> None:
        self._url = base_url.rstrip("/") + "/api/generate"

    def available(self) -> bool:
        try:
            with urllib.request.urlopen(
                self._url, timeout=5
            ) as resp:  # noqa: S310 - local/trusted endpoint
                return resp.status == 200
        except (urllib.error.URLError, OSError):
            return False

    def generate(self, system: str, user: str, model: str) -> str:
        payload = {
            "model": model,
            "system": system,
            "prompt": user,
            "stream": False,
            "options": {"temperature": 0},
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(  # noqa: S310 - local/trusted endpoint
            self._url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("response", "")


def build_user_message(section_id: str, title: str, text: str) -> str:
    return (
        f"SECTION ID: {section_id}\n"
        f"TITLE: {title}\n"
        f"TEXT:\n{text}\n"
    )


def parse_model_output(section_id: str, output: str) -> ExtractionResult:
    """Parse the model answer into structured fragments (deterministic)."""
    blocks = _EUCLID_BLOCK_RE.findall(output)
    fragments: list[str] = []
    for block in blocks:
        for line in block.splitlines():
            line = line.strip()
            if line:
                fragments.append(line)

    unsafe = _UNSAFE_RE.findall(output)
    modeled_match = _MODELED_RE.search(output)
    modeled = bool(blocks or modeled_match and modeled_match.group(1) == "yes")
    return ExtractionResult(
        section_id=section_id,
        modeled=modeled,
        fragments=fragments,
        unsafe_reason=unsafe[0] if unsafe else None,
    )


def load_prompt(prompt_path: Path) -> str:
    return prompt_path.read_text(encoding="utf-8")


def extract_section(
    client: OllamaClient,
    prompt: str,
    section_id: str,
    title: str,
    text: str,
    model: str,
) -> ExtractionResult:
    output = client.generate(
        system=prompt,
        user=build_user_message(section_id, title, text),
        model=model,
    )
    return parse_model_output(section_id, output)
