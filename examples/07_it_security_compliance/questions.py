"""
Questions dataset for the IT Security & Compliance demo.

Each question includes:
- id: unique identifier
- question: human-readable question
- query: Euclid IR query to execute
- category: type of reasoning required
- expected_answer: what a correct answer looks like (for validation)
- description: explanation of why this question is interesting
"""

QUESTIONS = [
    {
        "id": "Q1",
        "question": "Can user_0005 manage servers?",
        "query": "user_has_permission(user_0005, manage_servers)",
        "category": "single-hop",
        "expected": "Depends on role",
        "description": "Simple permission check through role hierarchy",
    },
    {
        "id": "Q2",
        "question": "Which roles can deploy code to production?",
        "query": "can_deploy($who, production)",
        "category": "multi-hop",
        "expected": "Roles with level >= 6 AND deploy_code permission",
        "description": "Requires: role level check + permission inheritance + environment tier",
    },
    {
        "id": "Q3",
        "question": "How many users have access to secret data?",
        "query": "can_access_resource($who, $res) AND resource($res, _, _, _, _, secret)",
        "category": "counting",
        "expected": "Users with clearance level >= 4",
        "description": "Intersection of user clearance and resource classification",
    },
    {
        "id": "Q4",
        "question": "Can a tech_lead deploy to golden environment?",
        "query": "can_deploy($who, golden) AND has_role($who, tech_lead)",
        "category": "role-enumeration",
        "expected": "No - tech_lead has level 4, golden requires level 6",
        "description": "Tests environment tier enforcement",
    },
    {
        "id": "Q5",
        "question": "Which users have stale access (not logged in for over 90 days)?",
        "query": "stale_access($who)",
        "category": "temporal",
        "expected": "Users with last_login_days > 90",
        "description": "Uses AWS IAM pattern: stale access detection",
    },
    {
        "id": "Q6",
        "question": "Which users violate separation of duties?",
        "query": "violates_separation_of_duties($who)",
        "category": "cross-policy",
        "expected": "Users with conflicting permissions",
        "description": "Combines deploy + approve, or create_role + assign_role",
    },
    {
        "id": "Q7",
        "question": "Which production resources are not encrypted?",
        "query": "resource($name, production, not_encrypted, _, _, _)",
        "category": "resource-audit",
        "expected": "List of unencrypted production resources",
        "description": "Direct CIS compliance check",
    },
    {
        "id": "Q8",
        "question": "Can an intern write code?",
        "query": "user_has_permission($who, write_code) AND has_role($who, intern)",
        "category": "negative",
        "expected": "No - interns only have read_code and run_tests",
        "description": "Negative test: should return empty (no match)",
    },
    {
        "id": "Q9",
        "question": "Which users have excessive permissions (more than 15)?",
        "query": "excessive_permissions($who, $count)",
        "category": "threshold",
        "expected": "Users with permission_count > 15",
        "description": "AWS IAM pattern: least privilege check",
    },
    {
        "id": "Q10",
        "question": "Can user_0020 access confidential resources?",
        "query": "can_access_resource(user_0020, $res) AND resource($res, _, _, _, _, confidential)",
        "category": "data-classification",
        "expected": "Depends on user_0020's role clearance level",
        "description": "Data classification access check",
    },
]

# Quick-reference: list of just the Euclid queries
QUERIES = [q["query"] for q in QUESTIONS]
