#!/usr/bin/env python3
"""
Extract RBAC data from PostgreSQL and convert to Euclid IR facts.

Reads the schema defined in schema.sql and produces Euclid IR facts
that can be loaded into Euclid-MCP for logical reasoning.

Usage:
    python extract_from_postgres.py --dsn "postgresql://user:pass@localhost/mydb"
    python extract_from_postgres.py --dsn "postgresql://user:pass@localhost/mydb" --output generated_facts.euclid

Requires: psycopg2-binary (pip install psycopg2-binary)
"""

import argparse
import sys
from pathlib import Path

try:
    import psycopg2
except ImportError:
    print("Error: psycopg2 not installed.")
    print("Install with: pip install psycopg2-binary")
    sys.exit(1)


QUERIES_DIR = Path(__file__).parent / "queries"
QUERY_FILES = [
    "users.sql",
    "roles.sql",
    "permissions.sql",
    "resources.sql",
    "assignments.sql",
]


def extract_facts(dsn: str) -> list[str]:
    """Execute all extraction queries and return Euclid IR fact lines."""
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    cur = conn.cursor()

    all_facts: list[str] = []

    for qfile in QUERY_FILES:
        qpath = QUERIES_DIR / qfile
        if not qpath.exists():
            print(f"Warning: {qpath} not found, skipping.")
            continue

        sql = qpath.read_text()
        try:
            cur.execute(sql)
            rows = cur.fetchall()
            for row in rows:
                fact = row[0].strip()
                if fact and not fact.startswith("--"):
                    all_facts.append(fact)
        except Exception as e:
            print(f"Error executing {qfile}: {e}")
            conn.close()
            sys.exit(1)

    conn.close()
    return all_facts


def deduplicate(facts: list[str]) -> list[str]:
    """Remove duplicate facts while preserving order."""
    seen: set[str] = set()
    unique: list[str] = []
    for f in facts:
        if f not in seen:
            seen.add(f)
            unique.append(f)
    return unique


def main():
    parser = argparse.ArgumentParser(
        description="Extract RBAC data from PostgreSQL to Euclid IR"
    )
    parser.add_argument(
        "--dsn",
        required=True,
        help="PostgreSQL connection string (e.g. postgresql://user:pass@localhost/mydb)",
    )
    parser.add_argument(
        "--output",
        default=str(Path(__file__).parent / "generated_facts.euclid"),
        help="Output file path (default: generated_facts.euclid)",
    )
    args = parser.parse_args()

    print(f"Connecting to: {args.dsn.split('@')[-1] if '@' in args.dsn else args.dsn}")
    facts = extract_facts(args.dsn)
    facts = deduplicate(facts)

    output_path = Path(args.output)

    with open(output_path, "w") as f:
        f.write("# Extracted from PostgreSQL\n")
        f.write(f"# Total facts: {len(facts)}\n\n")
        for fact in facts:
            f.write(fact + "\n")

    print(f"Extracted {len(facts)} facts -> {output_path}")


if __name__ == "__main__":
    main()
