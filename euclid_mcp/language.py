import re
from .models import KB


def parse(text: str) -> KB:
    text = text.strip()
    if not text:
        return KB()

    if _is_yaml(text):
        return _parse_yaml(text)
    return _parse_text(text)


def _is_yaml(text: str) -> bool:
    stripped = text.lstrip()
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
    data = yaml.safe_load(text)
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
        # Strip comments (# or //) but not inside atoms (e.g. ://)
        line = re.sub(r"(?<!\S)\s*(#|//).*$", "", lines[i]).strip()
        i += 1
        if not line:
            continue
        line = line.rstrip(".")

        if line.startswith("?"):
            query = line.lstrip("? ").strip()
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
                next_line = re.sub(r"(?<!\S)\s*(#|//).*$", "", lines[i]).strip()
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
            rules.append(f"{head.strip()} IF {body}")
        else:
            facts.append(line)

    return KB(facts=facts, rules=rules, query=query)


def _ensure_list(val):
    if isinstance(val, list):
        return [str(v).strip().rstrip(".") for v in val]
    if isinstance(val, str):
        return [val.strip().rstrip(".")]
    return []
