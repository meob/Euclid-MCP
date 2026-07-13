# Evaluating Euclid-MCP with Ollama

Test Euclid-MCP interactively using local LLMs via [ollmcp](https://github.com/jonigl/mcp-client-for-ollama).

Two modes:
- **Mode A**: Small KB — LLM translates both facts and questions to Euclid-IR
- **Mode B**: Large KB — pre-loaded, LLM translates only the question


## Prerequisites

```bash
# 1. Python 3.10+ with euclid-mcp
pip install -e .  # from project root

# 2. SWI-Prolog
# macOS:
brew install swi-prolog
# Debian/Ubuntu:
sudo apt-get install swi-prolog
# RedHat/CentOS/Fedora:
sudo dnf install swi-prolog

# 3. Ollama
# macOS:
brew install ollama
# Linux (any distro):
curl -fsSL https://ollama.com/install.sh | sh
ollama serve  # start in background

# 4. Pull a model (llama3.1 or qwen2.5 recommended)
ollama pull llama3.1:8b

# 5. ollmcp
pip install mcp-client-for-ollama
```


## Quick Start

### 1. Add Euclid-MCP as MCP server

```bash
ollmcp add euclid-mcp python3 -m euclid_mcp --cwd /path/to/euclid-mcp
```

### 2. Verify connection

```bash
ollmcp servers list
# Should show euclid-mcp connected
```

### 3. Start interactive session

```bash
ollmcp --model llama3.1:8b
```

In the TUI, type `/tools` to verify Euclid-MCP tools are available.


## Mode A: Small KB — LLM Translates Everything

The KB fits in the system prompt. The LLM translates both facts/rules AND questions to Euclid-IR.

### Example 1: Genealogy

**System prompt** (paste into ollmcp or set in config):

```
You are a logical reasoning assistant. You have access to a reasoning engine.

Knowledge base (Euclid IR):
  parent(tom, bob)
  parent(bob, ann)
  parent(tom, liz)
  parent(bob, pat)
  parent(pat, jim)
  ancestor($x, $y) IF parent($x, $y)
  ancestor($x, $y) IF parent($x, $z) AND ancestor($z, $y)

Instructions:
- For questions about family relationships, use the reason() tool
- Pass the knowledge and query as separate parameters
- Interpret the results and answer in natural language
```

**Questions to ask:**

| Question | Expected Euclid-IR Query |
|----------|--------------------------|
| Who are Tom's ancestors? | `ancestor(tom, $who)` |
| Who are Bob's descendants? | `ancestor($who, bob)` |
| Is Jim related to Tom? | `ancestor(tom, jim)` |
| Who are Ann's ancestors? | `ancestor(ann, $who)` |

### Example 2: RBAC (Role-Based Access Control)

**System prompt:**

```
You are an access control assistant. Use the reason() tool for permission checks.

Knowledge base (Euclid IR):
  role(intern)
  role(junior_dev)
  role(senior_dev)
  role(tech_lead)
  role(director)
  inherits(junior_dev, intern)
  inherits(senior_dev, junior_dev)
  inherits(tech_lead, senior_dev)
  inherits(director, tech_lead)
  role_permission(intern, read_code)
  role_permission(junior_dev, write_code)
  role_permission(senior_dev, merge_pr)
  role_permission(tech_lead, deploy_code)
  role_permission(director, manage_team)
  user(alice)
  user(bob)
  has_role(alice, tech_lead)
  has_role(bob, junior_dev)
  user_has_permission($user, $perm) IF user($user) AND has_role($user, $role) AND role_permission($role, $perm)
  role_has_permission($role, $perm) IF role_permission($role, $perm)
  role_has_permission($role, $perm) IF inherits($role, $parent) AND role_has_permission($parent, $perm)

Instructions:
- For permission questions, use reason() with the knowledge and query
- Explain the permission chain in your answer
```

**Questions to ask:**

| Question | Expected Euclid-IR Query |
|----------|--------------------------|
| Can Alice deploy code? | `user_has_permission(alice, deploy_code)` |
| Can Bob merge PRs? | `user_has_permission(bob, merge_pr)` |
| Who can deploy code? | `user_has_permission($who, deploy_code)` |
| What can Alice do? | `user_has_permission(alice, $perm)` |


## Mode B: Large KB — Pre-loaded, Translate Only the Query

For large knowledge bases (100+ facts), the KB is pre-loaded from a file. The LLM only translates the user's question.

### IT Security & Compliance

**KB file:** `examples/07_it_security_compliance/data/it_security_small.euclid`
(30 users, 50 resources, ~578 facts)

**System prompt:**

```
You are an IT security compliance assistant. You have access to a logical reasoning engine.

The knowledge base is loaded from the file at the path shown below.
For each question:
1. Translate the question to a Euclid-IR query
2. Call reason() with the knowledge file content and the query
3. Interpret the results

KB file: /path/to/euclid-mcp/examples/07_it_security_compliance/data/it_security_small.euclid

Key predicates available:
- user(UserId) — users in the system
- has_role(UserId, Role) — user-role assignments
- user_has_permission(UserId, Permission) — check permissions (resolves inheritance)
- can_deploy(UserId, Environment) — deployment eligibility
- can_access_resource(UserId, Resource) — data classification access
- stale_access(UserId) — users not logged in for 90+ days
- excessive_permissions(UserId, Count) — users with 15+ permissions
- resource(Name, Env, Encrypted, Backup, Access, Classification) — resources

Example queries:
- user_has_permission(user_0005, manage_servers)
- can_deploy($who, production)
- can_access_resource($who, $res) AND resource($res, _, _, _, _, secret)
- stale_access($who)
```

**Questions to ask:**

| Question | Expected Euclid-IR Query |
|----------|--------------------------|
| Can user_0005 manage servers? | `user_has_permission(user_0005, manage_servers)` |
| Which users can deploy to production? | `can_deploy($who, production)` |
| Which users have stale access? | `stale_access($who)` |
| Who can access secret resources? | `can_access_resource($who, $res) AND resource($res, _, _, _, _, secret)` |
| Which production resources are not encrypted? | `resource($name, production, not_encrypted, _, _, _)` |
| Can an intern write code? | `user_has_permission($who, write_code) AND has_role($who, intern)` |
| Which users have excessive permissions? | `excessive_permissions($who, $count)` |


## Running Benchmarks

Compare LLM alone vs LLM + Euclid-MCP:

```bash
# Full benchmark (5 questions, requires ollama + llama3.1:8b)
python examples/07_it_security_compliance/benchmark_comparison.py

# Quick test (small dataset)
python examples/07_it_security_compliance/benchmark_comparison.py --small

# Skip LLM-only condition (faster)
python examples/07_it_security_compliance/benchmark_comparison.py --skip-a
```

### Interpreting results

| Metric | LLM alone | LLM + Euclid-MCP |
|--------|-----------|-------------------|
| Accuracy | Often wrong at scale | Exact (deterministic) |
| Speed | Slow (reasoning overhead) | Fast (direct deduction) |
| Tokens | High (full reasoning chain) | Low (tool call + result) |
| Proof | None | Full proof tree |

Key insight: with 100+ facts, LLMs alone score ~2/5 on accuracy while Euclid-MCP scores 5/5.


## Tips

### Model selection

| Model | Size | Tool calling | Recommended for |
|-------|------|-------------|-----------------|
| llama3.1:8b | 8B | Yes | Mode A (small KB) |
| qwen2.5:7b | 7B | Yes | Mode A, faster |
| llama3.1:70b | 70B | Yes | Mode B (large KB) |
| mistral:7b | 7B | Limited | Simple queries |

### Troubleshooting

**ollmcp can't connect to Euclid-MCP:**
```bash
# Check server status
ollmcp servers list

# Re-add if needed
ollmcp remove euclid-mcp
ollmcp add euclid-mcp python3 -m euclid_mcp --cwd /path/to/euclid-mcp
```

**LLM doesn't call the tool:**
- Make sure tool calling is enabled in the model
- Use a model that supports function calling (llama3.1, qwen2.5)
- Check that the system prompt mentions the tool

**SWI-Prolog not found:**
```bash
which swipl
# If not found, install:
# macOS:      brew install swi-prolog
# Debian/Ubuntu: sudo apt-get install swi-prolog
# RedHat:     sudo dnf install swi-prolog
```
