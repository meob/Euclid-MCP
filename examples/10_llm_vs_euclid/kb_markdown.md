# IT Security & Compliance Knowledge Base

## Role Hierarchy (child inherits from parent)

- cto -> vp_engineering -> director -> eng_manager -> tech_lead -> senior_dev -> mid_senior_dev -> junior_dev -> intern
- devops_engineer -> sysadmin -> helpdesk
- director -> eng_manager -> tech_lead -> senior_dev -> mid_senior_dev -> junior_dev -> intern
- eng_manager -> tech_lead -> senior_dev -> mid_senior_dev -> junior_dev -> intern
- junior_dev -> intern
- mid_senior_dev -> junior_dev -> intern
- security_engineer -> security_analyst
- senior_dev -> mid_senior_dev -> junior_dev -> intern
- sysadmin -> helpdesk
- tech_lead -> senior_dev -> mid_senior_dev -> junior_dev -> intern
- vp_engineering -> director -> eng_manager -> tech_lead -> senior_dev -> mid_senior_dev -> junior_dev -> intern

## Deploy Role Levels

- cto: level 8
- director: level 6
- eng_manager: level 5
- intern: level 0
- junior_dev: level 1
- mid_senior_dev: level 2
- senior_dev: level 3
- tech_lead: level 4
- vp_engineering: level 7

## Deploy Requirements per Environment

- production: minimum role level 6
- golden: minimum role level 6
- staging: minimum role level 4
- development: minimum role level 2
- sandbox: minimum role level 1

## Permissions per Role (direct assignments)

- business_analyst: create_reports, view_analytics
- cto: approve_budget, manage_all_engineering, manage_directors, set_policy, view_financials
- devops_engineer: deploy_code, manage_ci_cd, manage_infrastructure, manage_servers, read_logs
- director: approve_budget, approve_pto, manage_department, manage_team, view_budget
- eng_manager: approve_pto, manage_team, view_budget
- helpdesk: read_logs, reset_password, view_tickets
- intern: read_code
- junior_dev: read_code, run_tests, write_code
- mid_senior_dev: read_code, review_code, run_tests, write_code
- product_manager: approve_features, manage_backlog, view_analytics
- security_analyst: read_logs, scan_vulnerabilities, view_audit
- security_engineer: manage_encryption, manage_firewall, read_logs, rotate_keys, scan_vulnerabilities, view_audit
- senior_dev: merge_pr, read_code, review_code, run_tests, write_code
- sysadmin: access_database, manage_servers, manage_users, read_logs
- tech_lead: deploy_code, merge_pr, read_code, review_code, run_tests, write_code
- vp_engineering: approve_budget, manage_department, manage_directors, view_financials

## Data Classification Levels

- public (level 1)
- internal (level 2)
- confidential (level 3)
- secret (level 4)

## Role Data Clearance

- business_analyst: internal
- cto: secret
- devops_engineer: confidential
- director: secret
- eng_manager: confidential
- helpdesk: internal
- intern: public
- junior_dev: internal
- mid_senior_dev: confidential
- product_manager: internal
- security_analyst: confidential
- security_engineer: secret
- senior_dev: confidential
- sysadmin: confidential
- tech_lead: confidential
- vp_engineering: secret

## Users (30 total)

| User | Role | Dept | Last Login (days) | Perms | MFA |
|------|------|------|-------------------|-------|-----|
| dat_0003 | eng_manager | data | 36 | 3 | no |
| dat_0012 | tech_lead | data | 24 | 6 | no |
| dat_0023 | mid_senior_dev | data | 18 | 4 | yes |
| dat_0029 | tech_lead | data | 51 | 10 | yes |
| eng_0002 | intern | engineering | 67 | 2 | no |
| eng_0008 | sysadmin | engineering | 61 | 7 | yes |
| eng_0014 | senior_dev | engineering | 66 | 5 | no |
| eng_0024 | business_analyst | engineering | 185 | 8 | no |
| infra_0009 | director | infrastructure | 18 | 5 | yes |
| infra_0010 | mid_senior_dev | infrastructure | 73 | 4 | no |
| infra_0011 | senior_dev | infrastructure | 3 | 5 | yes |
| infra_0016 | vp_engineering | infrastructure | 28 | 4 | yes |
| infra_0022 | mid_senior_dev | infrastructure | 14 | 4 | no |
| ops_0001 | helpdesk | operations | 306 | 3 | no |
| ops_0006 | sysadmin | operations | 2 | 4 | no |
| ops_0015 | helpdesk | operations | 8 | 3 | yes |
| ops_0020 | helpdesk | operations | 59 | 3 | yes |
| ops_0025 | devops_engineer | operations | 13 | 5 | yes |
| ops_0027 | helpdesk | operations | 2 | 3 | yes |
| plf_0004 | eng_manager | platform | 26 | 3 | no |
| plf_0005 | senior_dev | platform | 209 | 5 | yes |
| plf_0026 | vp_engineering | platform | 24 | 4 | no |
| prd_0018 | sysadmin | product | 18 | 6 | yes |
| prd_0021 | senior_dev | product | 5 | 6 | no |
| prd_0028 | product_manager | product | 82 | 3 | no |
| prd_0030 | product_manager | product | 1 | 3 | yes |
| sec_0007 | security_engineer | security | 24 | 6 | no |
| sec_0013 | helpdesk | security | 29 | 8 | yes |
| sre_0017 | helpdesk | sre | 120 | 3 | yes |
| sre_0019 | sysadmin | sre | 1 | 4 | yes |

## Cloud Resources (50 total)

By environment:
- production: 8
- golden: 6
- staging: 19
- development: 17

By encryption:
- encrypted: 28
- not_encrypted: 22

By type:
- dynamodb: 2
- ec2: 3
- ecs: 5
- eks: 4
- kms: 8
- lambda: 5
- rds: 4
- s3: 2
- sns: 6
- sqs: 11

## Key Rules Summary

- A user has a permission if their role has it (roles inherit from parent roles)
- can_deploy(user, env): user must have deploy_code permission AND role level >= env requirement
- can_access_resource(user, resource): user clearance level >= resource classification level
- stale_access(user): active user who hasn't logged in for >90 days
- excessive_permissions(user, count): user with >15 direct permissions
- violates_separation_of_duties(user): user has both deploy + approve, or create + assign
- service_account_risk(user): service account with interactive console access
- compliant_deployment: deploy_code + role level >= env level + 1

## Allowed Queries (Euclid-IR examples)

user_has_permission($who, deploy_code)
can_deploy($who, production)
stale_access($who)
resource($name, production, not_encrypted, _, _, _)
excessive_permissions($who, $count)
violates_separation_of_duties($who)
can_access_resource($who, $res) AND resource($res, _, _, _, _, secret)
user_clearance($who, $level)