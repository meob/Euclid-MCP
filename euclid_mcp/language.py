import re

from .models import KB
from .sanitizer import sanitize

VERSION_PATTERN = re.compile(r"^@version\s+(\d+\.\d+)")

_RESERVED_KEYWORDS = {"if", "and", "not"}

# Regex for quoted strings (double or single quote, with escape support)
_STRING_RE = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'')


def _extract_strings(text: str) -> tuple[str, list[str]]:
    """Extract quoted strings, replace with placeholders, return mapping."""
    strings: list[str] = []
    def _replace(m: re.Match) -> str:
        strings.append(m.group(0))
        return f"__STR_{len(strings) - 1}__"
    cleaned = _STRING_RE.sub(_replace, text)
    return cleaned, strings


def _restore_strings(text: str, strings: list[str]) -> str:
    """Restore quoted strings from placeholders."""
    for i, s in enumerate(strings):
        text = text.replace(f"__STR_{i}__", s)
    return text


def _normalize_term(term: str) -> str:
    """Normalize identifiers in a term to lowercase.

    Preserves $variables, quoted strings, numbers, and raises on
    reserved keywords used as predicate names.
    """
    cleaned, strings = _extract_strings(term)
    result = cleaned.lower()
    for i, s in enumerate(strings):
        result = result.replace(f"__str_{i}__", s)
    return result


def _validate_no_keywords(term: str) -> None:
    """Check that predicate names are not reserved keywords."""
    m = re.match(r"([a-z]\w*)\s*\(", term.strip())
    if m and m.group(1) in _RESERVED_KEYWORDS:
        raise ValueError(
            f"Reserved keyword '{m.group(1)}' cannot be used as predicate name"
        )


def parse(text: str) -> KB:
    text = text.strip()
    if not text:
        return KB()

    # Security: reject dangerous Prolog patterns before parsing
    sanitize(text)

    version = _extract_version(text)
    if _is_yaml(text):
        kb = _parse_yaml(text)
        kb.version = version
        return _normalize_kb(kb)
    kb = _parse_text(text)
    kb.version = version
    return _normalize_kb(kb)


def _extract_version(text: str) -> str | None:
    """Extract @version directive from the first line(s)."""
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        # Skip comments (#, //, %)
        if stripped.startswith(("#", "//", "%")):
            continue
        m = VERSION_PATTERN.match(stripped)
        if m:
            return m.group(1)
        # First non-comment, non-empty line is not @version
        break
    return None


def _is_yaml(text: str) -> bool:
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("---"):
        return True
    # Skip @version line for YAML detection
    lines = text.split("\n")
    for line in lines:
        s = line.strip()
        if not s or s.startswith(("#", "//", "%")):
            continue
        if VERSION_PATTERN.match(s):
            continue
        stripped = s
        break
    if stripped.startswith("{") or stripped.startswith("---"):
        return True
    try:
        import yaml
        data = yaml.safe_load(text)
        if isinstance(data, dict):
            keys = {k.lower() for k in data}
            if keys & {"facts", "rules", "query"}:
                return True
    except Exception:
        pass
    return False


def _parse_yaml(text: str) -> KB:
    import yaml
    # Strip @version line before YAML parsing
    lines = text.split("\n")
    filtered = []
    for line in lines:
        if VERSION_PATTERN.match(line.strip()):
            continue
        filtered.append(line)
    data = yaml.safe_load("\n".join(filtered))
    if not isinstance(data, dict):
        return _parse_text(text)

    facts = _ensure_list(data.get("facts", []))
    rules = _ensure_list(data.get("rules", []))
    query = data.get("query")
    if isinstance(query, str):
        query = query.strip().rstrip(".")
    return KB(facts=facts, rules=rules, query=query)


def _parse_text(text: str) -> KB:
    facts: list[str] = []
    rules: list[str] = []
    query: str | None = None

    lines = text.split("\n")
    i = 0
    while i < len(lines):
        raw_line = lines[i]
        # Extract strings before stripping comments (strings may contain #)
        raw_line, line_strings = _extract_strings(raw_line)
        # Strip comments (#, //, %)
        line = re.sub(r"(?<!\S)\s*(#|//|%).*$", "", raw_line).strip()
        i += 1
        if not line:
            continue
        # Skip @version directive
        if VERSION_PATTERN.match(line):
            continue
        line = line.rstrip(".")

        if line.startswith("?"):
            query = _restore_strings(line.lstrip("? ").strip(), line_strings)
        elif " IF " in line or line.endswith(" IF"):
            if " IF " in line:
                head, body_str = line.split(" IF ", 1)
            else:
                head = line[:-3]  # Remove trailing " IF"
                body_str = ""
            body_str = body_str.strip()
            # Multi-line rule: if body is empty or ends with AND, keep reading
            while body_str == "" or body_str.endswith("AND"):
                if i >= len(lines):
                    break
                next_raw = lines[i]
                next_raw, next_strings = _extract_strings(next_raw)
                line_strings.extend(next_strings)
                next_line = re.sub(r"(?<!\S)\s*(#|//|%).*$", "", next_raw).strip()
                i += 1
                if not next_line:
                    continue
                next_line = next_line.rstrip(".")
                if body_str == "":
                    body_str = next_line
                elif body_str.endswith("AND"):
                    body_str = body_str + " " + next_line
                else:
                    body_str = body_str + " " + next_line
            body_parts = re.split(r"\s+AND\s+", body_str)
            body = ", ".join(p.strip() for p in body_parts)
            rules.append(_restore_strings(f"{head.strip()} IF {body}", line_strings))
        else:
            facts.append(_restore_strings(line, line_strings))

    return KB(facts=facts, rules=rules, query=query)


def _normalize_kb(kb: KB) -> KB:
    """Normalize all identifiers in a KB to lowercase."""
    kb.facts = [_normalize_term(f) for f in kb.facts]
    kb.rules = [_normalize_term(r) for r in kb.rules]
    if kb.query:
        kb.query = _normalize_term(kb.query)
    for f in kb.facts:
        _validate_no_keywords(f)
    for r in kb.rules:
        head = re.split(r"\s+if\s+", r, maxsplit=1)[0].strip()
        _validate_no_keywords(head)
    if kb.query:
        _validate_no_keywords(kb.query)
    return kb


def _ensure_list(val):
    if isinstance(val, list):
        return [str(v).strip().rstrip(".") for v in val]
    if isinstance(val, str):
        return [val.strip().rstrip(".")]
    return []
