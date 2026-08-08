"""
Knowledge Base utilities:
  - load_kb_euclid(): loads all example 07 files into a single Euclid-IR string
  - generate_kb_markdown(): produces a condensed markdown summary for Bot A
"""

import re
from pathlib import Path

EXAMPLE_07 = Path(__file__).resolve().parent.parent / "07_it_security_compliance"

POLICY_FILES = [
    "policies/role_hierarchy.euclid",
    "policies/environment_tiers.euclid",
    "policies/data_classification.euclid",
    "policies/access_control.euclid",
    "policies/approval_workflows.euclid",
]

STANDARD_FILES = [
    "standards/cis_benchmarks.euclid",
    "standards/aws_iam_patterns.euclid",
]

DATA_FILE = "data/small_generated_facts.euclid"


def load_kb_euclid() -> str:
    """Load and concatenate all Euclid-IR files from example 07."""
    parts = []
    for f in STANDARD_FILES + POLICY_FILES:
        path = EXAMPLE_07 / f
        if path.exists():
            parts.append(f"# ── {f} ──")
            parts.append(path.read_text())
    data_path = EXAMPLE_07 / DATA_FILE
    if data_path.exists():
        parts.append(f"# ── {DATA_FILE} ──")
        parts.append(data_path.read_text())
    return "\n\n".join(parts)


# ── Parsers for generating markdown summary ──


def _parse_facts(euclid_text: str) -> list[tuple[str, list[str]]]:
    """Extract (predicate_name, [args]) from Euclid-IR text."""
    facts = []
    for line in euclid_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"([a-z_]\w*)\s*\((.+)\)\s*$", line)
        if m:
            args = [a.strip().strip("'\"") for a in m.group(2).split(",")]
            facts.append((m.group(1), args))
        else:
            m = re.match(r"([a-z_]\w*)\s*$", line)
            if m:
                facts.append((m.group(1), []))
    return facts


def _build_hierarchy(facts: list[tuple[str, list[str]]]) -> dict[str, str]:
    """Build child -> parent mapping from inherits/2 facts."""
    h = {}
    for name, args in facts:
        if name == "inherits" and len(args) == 2:
            h[args[0]] = args[1]
    return h


def _role_chain(role: str, hierarchy: dict[str, str]) -> list[str]:
    """Return full inheritance chain from role to root."""
    chain = [role]
    current = role
    while current in hierarchy:
        current = hierarchy[current]
        chain.append(current)
    return chain


def generate_kb_markdown() -> str:
    """Generate a condensed markdown summary of the IT Security KB."""
    euclid = load_kb_euclid()
    facts = _parse_facts(euclid)
    hierarchy = _build_hierarchy(facts)

    lines = []
    lines.append("# IT Security & Compliance Knowledge Base")
    lines.append("")

    # ── Role Hierarchy ──
    lines.append("## Role Hierarchy (child inherits from parent)")
    lines.append("")
    roles = sorted(set(args[0] for name, args in facts if name == "role" and args))
    for role in roles:
        chain = _role_chain(role, hierarchy)
        if len(chain) > 1:
            lines.append(f"- {' -> '.join(chain)}")
    lines.append("")

    # ── Deploy level mapping ──
    lines.append("## Deploy Role Levels")
    lines.append("")
    deploy_levels = {}
    for name, args in facts:
        if name == "deploy_role_level" and len(args) == 2:
            deploy_levels[args[0]] = args[1]
    for role in sorted(deploy_levels.keys()):
        lines.append(f"- {role}: level {deploy_levels[role]}")
    lines.append("")

    # ── Deploy requirements per environment ──
    lines.append("## Deploy Requirements per Environment")
    lines.append("")
    deploy_reqs = {}
    for name, args in facts:
        if name == "deploy_requires_level" and len(args) == 2:
            deploy_reqs[args[0]] = args[1]
    for env in ["production", "golden", "staging", "development", "sandbox"]:
        if env in deploy_reqs:
            lines.append(f"- {env}: minimum role level {deploy_reqs[env]}")
    lines.append("")

    # ── Permissions per role ──
    lines.append("## Permissions per Role (direct assignments)")
    lines.append("")
    role_perms: dict[str, list[str]] = {}
    for name, args in facts:
        if name == "role_permission" and len(args) == 2:
            role_perms.setdefault(args[0], []).append(args[1])
    for role in sorted(role_perms.keys()):
        perms = ", ".join(sorted(role_perms[role]))
        lines.append(f"- {role}: {perms}")
    lines.append("")

    # ── Data Classification ──
    lines.append("## Data Classification Levels")
    lines.append("")
    classifications = {}
    for name, args in facts:
        if name == "classification" and len(args) >= 2:
            classifications[args[0]] = args[1]
    for cls in ["public", "internal", "confidential", "secret"]:
        if cls in classifications:
            lines.append(f"- {cls} (level {classifications[cls]})")
    lines.append("")

    # ── Role Clearance ──
    lines.append("## Role Data Clearance")
    lines.append("")
    clearances = {}
    for name, args in facts:
        if name == "role_clearance" and len(args) == 2:
            clearances[args[0]] = args[1]
    for role in sorted(clearances.keys()):
        lines.append(f"- {role}: {clearances[role]}")
    lines.append("")

    # ── Users ──
    lines.append("## Users (30 total)")
    lines.append("")
    users: dict[str, dict] = {}
    for name, args in facts:
        if name == "user" and len(args) == 1:
            users.setdefault(args[0], {})
        elif name == "has_role" and len(args) == 2:
            users.setdefault(args[0], {})["role"] = args[1]
        elif name == "department" and len(args) == 2:
            users.setdefault(args[0], {})["dept"] = args[1]
        elif name == "last_login_days" and len(args) == 2:
            users.setdefault(args[0], {})["last_login"] = args[1]
        elif name == "permission_count" and len(args) == 2:
            users.setdefault(args[0], {})["perm_count"] = args[1]
        elif name == "account_type" and len(args) == 2:
            users.setdefault(args[0], {})["acct_type"] = args[1]
        elif name == "mfa_enabled" and len(args) == 1:
            users.setdefault(args[0], {})["mfa"] = True

    lines.append("| User | Role | Dept | Last Login (days) | Perms | MFA |")
    lines.append("|------|------|------|-------------------|-------|-----|")
    for u in sorted(users.keys()):
        d = users[u]
        role = d.get("role", "?")
        dept = d.get("dept", "?")
        login = d.get("last_login", "?")
        pc = d.get("perm_count", "?")
        mfa = "yes" if d.get("mfa") else "no"
        lines.append(f"| {u} | {role} | {dept} | {login} | {pc} | {mfa} |")
    lines.append("")

    # ── Resources ──
    lines.append("## Cloud Resources (50 total)")
    lines.append("")
    resources: dict[str, dict] = {}
    for name, args in facts:
        if name == "resource" and len(args) >= 6:
            resources[args[0]] = {
                "env": args[1],
                "encryption": args[2],
                "backup": args[3],
                "access": args[4],
                "classification": args[5],
            }
        elif name == "resource_type" and len(args) == 2:
            resources.setdefault(args[0], {})["type"] = args[1]

    env_counts: dict[str, int] = {}
    enc_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    for r in resources.values():
        env_counts[r.get("env", "?")] = env_counts.get(r.get("env", "?"), 0) + 1
        enc_counts[r.get("encryption", "?")] = enc_counts.get(r.get("encryption", "?"), 0) + 1
        type_counts[r.get("type", "?")] = type_counts.get(r.get("type", "?"), 0) + 1

    lines.append("By environment:")
    for env in ["production", "golden", "staging", "development"]:
        if env in env_counts:
            lines.append(f"- {env}: {env_counts[env]}")
    lines.append("")
    lines.append("By encryption:")
    for enc in ["encrypted", "not_encrypted"]:
        if enc in enc_counts:
            lines.append(f"- {enc}: {enc_counts[enc]}")
    lines.append("")
    lines.append("By type:")
    for t in sorted(type_counts.keys()):
        lines.append(f"- {t}: {type_counts[t]}")
    lines.append("")

    # ── Key Rules Summary ──
    lines.append("## Key Rules Summary")
    lines.append("")
    lines.append("- A user has a permission if their role has it (roles inherit from parent roles)")
    lines.append("- can_deploy(user, env): user must have deploy_code permission AND role level >= env requirement")
    lines.append("- can_access_resource(user, resource): user clearance level >= resource classification level")
    lines.append("- stale_access(user): active user who hasn't logged in for >90 days")
    lines.append("- excessive_permissions(user, count): user with >15 direct permissions")
    lines.append("- violates_separation_of_duties(user): user has both deploy + approve, or create + assign")
    lines.append("- service_account_risk(user): service account with interactive console access")
    lines.append("- compliant_deployment: deploy_code + role level >= env level + 1")
    lines.append("")
    lines.append("## Allowed Queries (Euclid-IR examples)")
    lines.append("")
    lines.append("user_has_permission($who, deploy_code)")
    lines.append("can_deploy($who, production)")
    lines.append("stale_access($who)")
    lines.append("resource($name, production, not_encrypted, _, _, _)")
    lines.append("excessive_permissions($who, $count)")
    lines.append("violates_separation_of_duties($who)")
    lines.append("can_access_resource($who, $res) AND resource($res, _, _, _, _, secret)")
    lines.append("user_clearance($who, $level)")

    return "\n".join(lines)
