"""Stage 1 of the policy compiler: deterministic structural parsing.

Turns a source document (Markdown for now) into a DocumentModel of numbered
sections. No LLM is involved: this stage only extracts structure, so the
section ids are stable and can be referenced later as `# src:` anchors.

Future source formats (DISA STIG XML, HTML, DOCX) plug in here behind the same
`parse_source()` entry point.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Section:
    id: str  # stable section id (slug of the heading), used as `# src:` anchor
    title: str
    lines: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


@dataclass
class DocumentModel:
    source: Path
    title: str
    sections: list[Section] = field(default_factory=list)


def _slug(title: str) -> str:
    # Normalize diacritics (à -> a, é -> e) so accented headings produce
    # stable ASCII section ids, then replace every non-alphanumeric run
    # with a single underscore.
    ascii_form = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_form.lower()).strip("_")
    return slug or "sezione"


def parse_markdown(path: Path) -> DocumentModel:
    """Parse a Markdown document into heading-delimited sections.

    - `# `   -> document title
    - `## `  -> starts a new section (id = slug of the heading)
    - `>`    -> meta blockquotes are skipped (not part of the normative text)
    - blank lines and other lines accumulate in the current section
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    title = ""
    sections: list[Section] = []
    current: Section | None = None

    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith("# "):
            title = stripped[2:].strip()
            continue
        if stripped.startswith("## "):
            if current is not None:
                sections.append(current)
            heading = stripped[3:].strip()
            current = Section(id=_slug(heading), title=heading)
            continue
        if stripped.startswith(">"):
            continue
        if current is not None and stripped:
            current.lines.append(stripped)

    if current is not None:
        sections.append(current)

    return DocumentModel(source=path, title=title, sections=sections)


def parse_source(path: Path) -> DocumentModel:
    """Dispatch to the parser for the file type. Raises for unsupported formats."""
    suffix = path.suffix.lower()
    if suffix == ".md":
        return parse_markdown(path)
    raise NotImplementedError(
        f"Unsupported source format '{suffix}' for {path.name}. "
        "Only Markdown is supported today; XML (STIG) parsers can be added "
        "behind this entry point."
    )
