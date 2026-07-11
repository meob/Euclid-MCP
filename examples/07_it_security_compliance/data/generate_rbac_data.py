#!/usr/bin/env python3
"""
Generate realistic RBAC data and convert to Euclid IR facts.

Creates a synthetic but plausible IT organization with:
- 200 users across 8 departments
- 25 roles with hierarchical inheritance
- 30 permissions (engineering, operations, security, management)
- 300 cloud resources across 4 environments
- Realistic user-role assignments

The generated data matches the PostgreSQL schema in schema.sql,
so the same reasoning rules apply to both real and generated data.

Usage:
    python generate_rbac_data.py
    python generate_rbac_data.py --output custom_output.euclid
    python generate_rbac_data.py --users 100 --resources 150
"""

import argparse
import random
import string
from pathlib import Path

random.seed(42)

# ── Constants ──

DEPARTMENTS = [
    "engineering", "operations", "security", "product",
    "data", "platform", "infrastructure", "sre",
]

RESOURCE_TYPES = ["ec2", "s3", "rds", "dynamodb", "lambda", "ecs", "eks", "sqs", "sns", "kms"]

ENVIRONMENTS = ["production", "staging", "development", "golden"]

CLASSIFICATIONS = ["public", "internal", "confidential", "secret"]

RESOURCE_TEAMS = [
    "web-platform", "data-platform", "ml-ops", "infrastructure",
    "backend", "mobile", "security-ops", "devops",
]

# ── Roles and hierarchy ──

ROLES = {
    # Engineering
    "intern":           {"level": 0,  "dept": "engineering"},
    "junior_dev":       {"level": 1,  "dept": "engineering"},
    "mid_senior_dev":   {"level": 2,  "dept": "engineering"},
    "senior_dev":       {"level": 3,  "dept": "engineering"},
    "tech_lead":        {"level": 4,  "dept": "engineering"},
    "eng_manager":      {"level": 5,  "dept": "engineering"},
    "director":         {"level": 6,  "dept": "engineering"},
    "vp_engineering":   {"level": 7,  "dept": "engineering"},
    "cto":              {"level": 8,  "dept": "engineering"},
    # Operations
    "helpdesk":         {"level": 1,  "dept": "operations"},
    "sysadmin":         {"level": 3,  "dept": "operations"},
    "devops_engineer":  {"level": 4,  "dept": "operations"},
    # Security
    "security_analyst": {"level": 2,  "dept": "security"},
    "security_engineer":{"level": 4,  "dept": "security"},
    # Product
    "product_manager":  {"level": 3,  "dept": "product"},
    "business_analyst": {"level": 2,  "dept": "product"},
}

ROLE_HIERARCHY = {
    "junior_dev":       "intern",
    "mid_senior_dev":   "junior_dev",
    "senior_dev":       "mid_senior_dev",
    "tech_lead":        "senior_dev",
    "eng_manager":      "tech_lead",
    "director":         "eng_manager",
    "vp_engineering":   "director",
    "cto":              "vp_engineering",
    "sysadmin":         "helpdesk",
    "security_engineer":"security_analyst",
    "devops_engineer":  "sysadmin",
}

# ── Permissions ──

PERMISSIONS = {
    # Engineering
    "read_code":        {"cat": "read",      "critical": False},
    "write_code":       {"cat": "write",     "critical": False},
    "run_tests":        {"cat": "read",      "critical": False},
    "review_code":      {"cat": "read",      "critical": False},
    "merge_pr":         {"cat": "write",     "critical": False},
    "deploy_code":      {"cat": "deploy",    "critical": True},
    # Operations
    "read_logs":        {"cat": "read",      "critical": False},
    "reset_password":   {"cat": "write",     "critical": False},
    "view_tickets":     {"cat": "read",      "critical": False},
    "manage_users":     {"cat": "admin",     "critical": True},
    "manage_servers":   {"cat": "admin",     "critical": True},
    "access_database":  {"cat": "admin",     "critical": True},
    "manage_ci_cd":     {"cat": "admin",     "critical": False},
    "manage_infrastructure": {"cat": "admin","critical": True},
    # Security
    "view_audit":       {"cat": "read",      "critical": False},
    "scan_vulnerabilities": {"cat": "read",  "critical": False},
    "manage_firewall":  {"cat": "admin",     "critical": True},
    "manage_encryption":{"cat": "admin",     "critical": True},
    "rotate_keys":      {"cat": "admin",     "critical": True},
    # Management
    "manage_team":      {"cat": "admin",     "critical": False},
    "approve_pto":      {"cat": "write",     "critical": False},
    "view_budget":      {"cat": "read",      "critical": False},
    "approve_budget":   {"cat": "admin",     "critical": True},
    "manage_department":{"cat": "admin",     "critical": True},
    "view_financials":  {"cat": "read",      "critical": False},
    "manage_directors": {"cat": "admin",     "critical": True},
    "manage_all_engineering": {"cat": "admin","critical": True},
    "set_policy":       {"cat": "admin",     "critical": True},
    # Product
    "view_analytics":   {"cat": "read",      "critical": False},
    "manage_backlog":   {"cat": "write",     "critical": False},
    "approve_features": {"cat": "write",     "critical": False},
    "create_reports":   {"cat": "read",      "critical": False},
}

ROLE_PERMISSIONS: dict[str, list[str]] = {
    "intern":           ["read_code", "run_tests"],
    "junior_dev":       ["read_code", "write_code", "run_tests"],
    "mid_senior_dev":   ["read_code", "write_code", "run_tests", "review_code"],
    "senior_dev":       ["read_code", "write_code", "run_tests", "review_code", "merge_pr"],
    "tech_lead":        ["read_code", "write_code", "run_tests", "review_code", "merge_pr", "deploy_code"],
    "eng_manager":      ["manage_team", "approve_pto", "view_budget"],
    "director":         ["manage_team", "approve_pto", "view_budget", "approve_budget", "manage_department"],
    "vp_engineering":   ["manage_department", "approve_budget", "view_financials", "manage_directors"],
    "cto":              ["manage_all_engineering", "approve_budget", "view_financials", "manage_directors", "set_policy"],
    "helpdesk":         ["read_logs", "reset_password", "view_tickets"],
    "sysadmin":         ["read_logs", "manage_users", "manage_servers", "access_database"],
    "devops_engineer":  ["read_logs", "manage_servers", "deploy_code", "manage_ci_cd", "manage_infrastructure"],
    "security_analyst": ["read_logs", "view_audit", "scan_vulnerabilities"],
    "security_engineer":["read_logs", "view_audit", "scan_vulnerabilities", "manage_firewall", "manage_encryption", "rotate_keys"],
    "product_manager":  ["view_analytics", "manage_backlog", "approve_features"],
    "business_analyst": ["view_analytics", "create_reports"],
}


def generate_username(index: int, dept: str) -> str:
    """Generate realistic username: dept abbreviation + padded number."""
    dept_abbr = {
        "engineering": "eng", "operations": "ops", "security": "sec",
        "product": "prd", "data": "dat", "platform": "plf",
        "infrastructure": "infra", "sre": "sre",
    }
    abbr = dept_abbr.get(dept, dept[:3])
    return f"{abbr}_{index:04d}"


def generate_users(count: int) -> list[dict]:
    """Generate user records with realistic attribute distribution."""
    users = []
    for i in range(1, count + 1):
        dept = random.choice(DEPARTMENTS)
        username = generate_username(i, dept)

        # Higher-level roles are rarer
        role_weights = [5, 20, 25, 20, 10, 8, 5, 4, 3]  # intern..cto
        role_names = ["intern", "junior_dev", "mid_senior_dev", "senior_dev",
                       "tech_lead", "eng_manager", "director", "vp_engineering", "cto"]

        # Adjust weights by department
        if dept in ("operations", "sre"):
            role_weights = [3, 10, 15, 15, 12, 10, 5, 3, 2]
            role_names = ["helpdesk", "helpdesk", "sysadmin", "sysadmin",
                          "devops_engineer", "devops_engineer", "director", "vp_engineering", "cto"]
        elif dept == "security":
            role_weights = [5, 15, 20, 20, 10, 5, 3, 2, 1]
            role_names = ["security_analyst", "security_analyst", "security_engineer", "security_engineer",
                          "security_engineer", "security_engineer", "director", "vp_engineering", "cto"]
        elif dept == "product":
            role_weights = [10, 25, 25, 15, 10, 5, 3, 2, 1]
            role_names = ["business_analyst", "product_manager", "product_manager", "product_manager",
                          "tech_lead", "eng_manager", "director", "vp_engineering", "cto"]

        primary_role = random.choices(role_names, weights=role_weights, k=1)[0]

        # Some users have secondary roles
        secondary_role = None
        if random.random() < 0.15:
            all_roles = list(ROLES.keys())
            secondary_role = random.choice(all_roles)

        # Account attributes
        is_service = random.random() < 0.05
        account_type = "service" if is_service else "human"
        has_console = not is_service and random.random() < 0.85
        has_ak = random.random() < 0.2
        mfa = random.random() < 0.6 if not is_service else random.random() < 0.3

        # Last login: realistic distribution
        if random.random() < 0.1:
            last_login_days = random.randint(90, 365)  # stale
        elif random.random() < 0.3:
            last_login_days = random.randint(30, 90)
        else:
            last_login_days = random.randint(0, 30)

        users.append({
            "username": username,
            "department": dept,
            "primary_role": primary_role,
            "secondary_role": secondary_role,
            "account_type": account_type,
            "has_console_access": has_console,
            "has_access_key": has_ak,
            "mfa_enabled": mfa,
            "last_login_days": last_login_days,
        })

    return users


def generate_resources(count: int) -> list[dict]:
    """Generate cloud resource records."""
    resources = []
    prefixes = {
        "ec2": "i", "s3": "s3", "rds": "db", "dynamodb": "tbl",
        "lambda": "fn", "ecs": "svc", "eks": "cluster", "sqs": "queue",
        "sns": "topic", "kms": "key",
    }

    for i in range(1, count + 1):
        rtype = random.choice(RESOURCE_TYPES)
        prefix = prefixes.get(rtype, "res")

        # Environment distribution: most in dev/staging, fewer in prod
        env_weights = [15, 35, 40, 10]  # production, staging, development, golden
        env = random.choices(ENVIRONMENTS, weights=env_weights, k=1)[0]

        # Classification correlates with environment
        if env in ("production", "golden"):
            class_weights = [5, 20, 45, 30]
        elif env == "staging":
            class_weights = [15, 40, 35, 10]
        else:
            class_weights = [30, 40, 25, 5]

        classification = random.choices(CLASSIFICATIONS, weights=class_weights, k=1)[0]

        # Encrypted: production/golden mostly encrypted
        if env in ("production", "golden"):
            encrypted = random.random() < 0.85
        elif env == "staging":
            encrypted = random.random() < 0.6
        else:
            encrypted = random.random() < 0.3

        # Backup: production/golden mostly backed up
        has_backup = random.random() < 0.8 if env in ("production", "golden") else random.random() < 0.4

        # Public: only dev/sandbox
        is_public = random.random() < 0.15 if env == "development" else random.random() < 0.02

        team = random.choice(RESOURCE_TEAMS)
        name = f"{prefix}_{team.replace('-', '_')}_{i:04d}"

        resources.append({
            "name": name,
            "resource_type": rtype,
            "environment": env,
            "encrypted": encrypted,
            "has_backup": has_backup,
            "is_public": is_public,
            "data_classification": classification,
            "owner_team": team,
        })

    return resources


def to_euclid_facts(users: list[dict], resources: list[dict]) -> list[str]:
    """Convert generated data to Euclid IR fact lines."""
    facts: list[str] = []

    # Users
    for u in users:
        facts.append(f"user({u['username']})")
        facts.append(f"is_active({u['username']})")
        facts.append(f"department({u['username']}, {u['department']})")
        facts.append(f"account_type({u['username']}, {u['account_type']})")
        if u["mfa_enabled"]:
            facts.append(f"mfa_enabled({u['username']})")
        if u["has_console_access"]:
            facts.append(f"has_console_access({u['username']})")
        if u["has_access_key"]:
            facts.append(f"has_access_key({u['username']})")
        facts.append(f"last_login_days({u['username']}, {u['last_login_days']})")
        facts.append(f"has_role({u['username']}, {u['primary_role']})")
        if u["secondary_role"]:
            facts.append(f"has_role({u['username']}, {u['secondary_role']})")

        # Permission count (derived)
        all_perms = set(ROLE_PERMISSIONS.get(u["primary_role"], []))
        if u["secondary_role"]:
            all_perms.update(ROLE_PERMISSIONS.get(u["secondary_role"], []))
        facts.append(f"permission_count({u['username']}, {len(all_perms)})")

        # Direct permissions (for users, not just roles)
        for perm in all_perms:
            facts.append(f"has_permission({u['username']}, {perm})")

    # Resources
    for r in resources:
        enc = "encrypted" if r["encrypted"] else "not_encrypted"
        bak = "has_backup" if r["has_backup"] else "no_backup"
        pub = "public_access" if r["is_public"] else "private_access"
        facts.append(f"resource({r['name']}, {r['environment']}, {enc}, {bak}, {pub}, {r['data_classification']})")
        facts.append(f"resource_type({r['name']}, {r['resource_type']})")
        facts.append(f"owner_team({r['name']}, {r['owner_team']})")

        # CIS control applicability
        if r["resource_type"] == "s3":
            facts.append(f"cis_applies_to({r['name']}, cis_2_1)")
            facts.append(f"cis_applies_to({r['name']}, cis_2_2)")
            facts.append(f"cis_applies_to({r['name']}, cis_2_3)")
        elif r["resource_type"] == "rds":
            facts.append(f"cis_applies_to({r['name']}, cis_2_7)")
            facts.append(f"cis_applies_to({r['name']}, cis_2_8)")
            facts.append(f"cis_applies_to({r['name']}, cis_6_1)")
        elif r["resource_type"] == "ec2":
            facts.append(f"cis_applies_to({r['name']}, cis_7_1)")
            facts.append(f"cis_applies_to({r['name']}, cis_7_2)")

    return facts


def main():
    parser = argparse.ArgumentParser(description="Generate realistic RBAC data as Euclid IR")
    parser.add_argument("--users", type=int, default=200, help="Number of users (default: 200)")
    parser.add_argument("--resources", type=int, default=300, help="Number of resources (default: 300)")
    parser.add_argument("--output", default=None, help="Output file (default: generated_facts.euclid)")
    args = parser.parse_args()

    users = generate_users(args.users)
    resources = generate_resources(args.resources)
    facts = to_euclid_facts(users, resources)

    output_path = Path(args.output) if args.output else Path(__file__).parent / "generated_facts.euclid"

    with open(output_path, "w") as f:
        f.write("# Generated RBAC data — Euclid IR\n")
        f.write(f"# {len(users)} users, {len(resources)} resources\n")
        f.write(f"# Total facts: {len(facts)}\n\n")
        for fact in facts:
            f.write(fact + "\n")

    print(f"Generated {len(facts)} facts ({len(users)} users, {len(resources)} resources) -> {output_path}")

    # Print summary
    role_dist: dict[str, int] = {}
    for u in users:
        role_dist[u["primary_role"]] = role_dist.get(u["primary_role"], 0) + 1
    print("\nRole distribution:")
    for role, count in sorted(role_dist.items(), key=lambda x: -x[1]):
        print(f"  {role}: {count}")

    env_dist: dict[str, int] = {}
    for r in resources:
        env_dist[r["environment"]] = env_dist.get(r["environment"], 0) + 1
    print("\nEnvironment distribution:")
    for env, count in sorted(env_dist.items(), key=lambda x: -x[1]):
        print(f"  {env}: {count}")


if __name__ == "__main__":
    main()
