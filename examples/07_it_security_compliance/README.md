# IT Security & Compliance Demo

Demonstrates Euclid-MCP reasoning over a realistic IT security knowledge base with 3 layers of rules and 3,872+ facts.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Layer 1: Standards (fixed rules)                       │
│  ├── CIS AWS Benchmarks (50 controls)                  │
│  └── AWS IAM Patterns (10 best practices)              │
├─────────────────────────────────────────────────────────┤
│  Layer 2: Company Policies (configurable rules)         │
│  ├── Role Hierarchy (recursive inheritance)            │
│  ├── Environment Tiers (4-tier with deploy requirements)│
│  ├── Data Classification (4-level with clearance)      │
│  ├── Access Control (permission assignments)           │
│  └── Approval Workflows (multi-step chains)            │
├─────────────────────────────────────────────────────────┤
│  Layer 3: Data Facts (from DB/generator)                │
│  ├── 200 users across 8 departments                    │
│  ├── 300 cloud resources (EC2, S3, RDS, etc.)          │
│  └── ~3,872 facts (users, roles, permissions, resources)│
└─────────────────────────────────────────────────────────┘
```

## Questions

| # | Question | Category | Expected |
|---|----------|----------|----------|
| Q1 | Can user_0005 manage servers? | single-hop | Empty (user not in dataset) |
| Q2 | Which roles can deploy to production? | multi-hop | Users with deploy_code + level >= 5 |
| Q3 | Which users can access secret data? | conjunction | Users with secret clearance |
| Q4 | Can a tech_lead deploy to golden? | multi-role | Users with tech_lead + higher role |
| Q5 | Which users have stale access? | arithmetic | Users with last_login > 90 days |
| Q6 | Which users violate separation of duties? | negative | Empty (no approve_deploy perm) |
| Q7 | Which production resources are unencrypted? | resource-audit | Production + not_encrypted |
| Q8 | Can an intern write code? | negative | Empty (interns only have read_code) |
| Q9 | Which users have excessive permissions? | threshold | Users with permission_count > 15 |
| Q10 | Which S3 buckets in prod are unencrypted? | combined | S3 + production + not_encrypted |

## Usage

```bash
# Quick test with small dataset (30 users, 50 resources)
python demo.py --small

# Run all questions with full dataset
python demo.py

# Run specific question
python demo.py --small --question Q5

# Limit solutions per query
python demo.py --small --max-solutions 10
```

## Data Generation

```bash
# Generate small dataset for testing
python data/generate_rbac_data.py --users 30 --resources 50 --output data/small_generated_facts.euclid

# Generate full dataset
python data/generate_rbac_data.py --users 200 --resources 300
```

## PostgreSQL Extraction

For real data, use the SQL queries in `data/queries/`:

```bash
# Extract from PostgreSQL
python data/extract_from_postgres.py --host localhost --dbname mydb --user admin
```

## Key Features Demonstrated

1. **Multi-hop reasoning**: Q2 chains role → permission → environment tier
2. **Arithmetic comparisons**: Q5 uses `$days > 90` for stale access detection
3. **Conjunction queries**: Q3 combines `can_access_resource` with `resource` filter
4. **Negative tests**: Q6, Q8 verify empty results for invalid access patterns
5. **Proof trees**: Each solution includes a proof tree showing reasoning steps

## Files

- `demo.py` — Main demo script
- `questions.py` — Question definitions with Euclid IR queries
- `policies/` — Company-specific rules (Euclid IR format)
- `standards/` — Industry standards (CIS, AWS IAM)
- `data/` — Data generation and extraction scripts
