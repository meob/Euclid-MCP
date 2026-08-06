#!/usr/bin/env python3
"""
LLM vs Euclid-MCP — Interactive Side-by-Side Demo

Two bots, same model (llama3.1:8b), same knowledge base:
  - Bot A: plain LLM, KB as markdown context
  - Bot B: LLM + Euclid-MCP reasoning engine via tool calling

Speak freely in any language. Bot B decides when to call the engine.

Usage:
    python demo.py                          # Default model (llama3.1:8b)
    python demo.py --model llama3.1:8b      # Explicit model
    python demo.py --bot-a-only             # Test plain LLM only
    python demo.py --bot-b-only             # Test Euclid bot only
    python demo.py --scripted               # Run preset questions, then exit
    python demo.py --scripted --pause       # Press Enter between questions
    python demo.py --scripted --delay 2     # 2s pause between questions

Requires: pip install ollama + euclid-mcp installed
"""

import argparse
import os
import sys
import time
from pathlib import Path

# ── Auto-detect venv and re-exec if needed ──

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_VENV_PYTHON = _PROJECT_ROOT / ".venv" / "bin" / "python"

def _ensure_venv():
    """Re-exec with venv Python if not already inside it."""
    if _VENV_PYTHON.exists() and ".venv" not in sys.prefix:
        print(f"{C.DIM}Activating virtualenv...{C.RESET}")
        os.execv(str(_VENV_PYTHON), [str(_VENV_PYTHON)] + sys.argv)


class C:
    """ANSI color codes — defined early for use in _ensure_venv."""
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    MAGENTA = "\033[95m"
    BLUE = "\033[94m"
    WHITE = "\033[97m"
    BG_BLUE = "\033[44m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    UNDERLINE = "\033[4m"

_ensure_venv()

try:
    import ollama as ollama_lib
except ImportError:
    print(f"{C.RED}Error: 'ollama' package not found. Install with: pip install ollama{C.RESET}")
    sys.exit(1)

# Ensure project root is importable
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from kb_utils import generate_kb_markdown, load_kb_euclid
from tools import EUCLID_TOOLS, execute_tool

# ── System Prompts ──

SYSTEM_PROMPT_PLAIN = """You are an IT security assistant. You have access to a company knowledge base about users, roles, permissions, and cloud resources.

{kb_markdown}

Answer questions about this knowledge base. Be precise. If you are not sure, say so. Answer in the same language the user uses."""

SYSTEM_PROMPT_EUCLID = """You are an IT security assistant with access to a DETERMINISTIC logical reasoning engine.

The knowledge base contains: 30 users, their roles, permissions, cloud resources, and security policies for an IT company.

IMPORTANT: Users are identified by IDs like dat_0003, eng_0008, ops_0006, etc. There are NO names like "alice" or "bob". If the user asks about a person by a common name, tell them the KB uses technical IDs and offer to list all users or search by department/role.

ROLE HIERARCHY (each inherits from below):
intern -> junior_dev -> mid_senior_dev -> senior_dev -> tech_lead -> eng_manager -> director -> vp_engineering -> cto

DEPLOY ENVIRONMENT LEVELS:
production=6, golden=6, staging=4, development=2, sandbox=1

AVAILABLE TOOLS:
- reason: Run logical deduction. ALWAYS use this for questions about users, roles, permissions, access, compliance, deployments, resources, or any factual query about the knowledge base.
- diagnose: Explain why a query succeeds or fails. Use when something should work but doesn't.
- what_if: Test scenario changes. Use + to add facts, - to remove them.
- check_kb: Validate the knowledge base for errors.

AVAILABLE PREDICATES (use in reason tool):
- has_role($user, $role) — check user's role
- user_has_permission($user, $perm) — check effective permission for a user
- can_deploy($user, $env) — can user deploy to environment
- can_access_resource($user, $resource) — can user access resource
- resource($name, $env, $encryption, $backup, $access, $classification) — query resources
- stale_access($user) — hasn't logged in for 90+ days
- excessive_permissions($user, $count) — has more than 15 permissions
- violates_separation_of_duties($user) — has conflicting permissions
- department($user, $dept) — user's department
- permission_count($user, $count) — number of permissions
- last_login_days($user, $days) — days since last login

VARIABLE SYNTAX: Use $name for variables (e.g. $who, $role, $perm). Do NOT use ? or * as wildcards.
To query all permissions for user dat_0003: user_has_permission(dat_0003, $perm)
To query all sysadmins: has_role($who, sysadmin)
To query all users and roles: has_role($who, $role)

RULES:
1. For ANY question about the knowledge base, you MUST call the reason tool. Do NOT guess.
2. NEVER fabricate user names or data. Only report what the tool returns.
3. Translate the user's natural language into the appropriate predicate call.
4. After getting results, explain them clearly in the user's language.
5. List ALL solutions found. If none, say the answer is NO.
6. For non-KB questions (greetings, general knowledge), answer directly without tools."""


# ── Preset questions for --scripted mode ──

SCRIPTED_QUESTIONS = [
    "Who can deploy to production?",
    "Which users have stale access?",
    "Can intern_01 write code?",
    "Which production resources are not encrypted?",
    "What if alice gets the sysadmin role?",
    "Why can't a helpdesk user access secret data?",
]


# ── Helper Functions ──


def check_ollama(model: str) -> bool:
    """Check if Ollama is running and the model is available."""
    try:
        models = ollama_lib.list()
        available = [m.model for m in models.models]
        # Check for exact match or prefix match (ollama appends :latest)
        found = any(model in m for m in available)
        if not found:
            print(f"{C.RED}Model '{model}' not found.{C.RESET}")
            print(f"Available models: {', '.join(available)}")
            print(f"Pull it with: ollama pull {model}")
            return False
        return True
    except Exception as e:
        print(f"{C.RED}Cannot connect to Ollama: {e}{C.RESET}")
        print("Start Ollama with: ollama serve")
        return False


def print_separator(char="━", width=70):
    print(f"{C.DIM}{char * width}{C.RESET}")


def print_header(text: str):
    print_separator()
    print(f"{C.BOLD}{C.WHITE}  {text}{C.RESET}")
    print_separator()


def format_plain_response(text: str, width: int = 70) -> str:
    """Wrap text for display."""
    words = text.split()
    lines = []
    current_line = []
    current_len = 0
    for word in words:
        if current_len + len(word) + 1 > width and current_line:
            lines.append(" ".join(current_line))
            current_line = [word]
            current_len = len(word)
        else:
            current_line.append(word)
            current_len += len(word) + 1
    if current_line:
        lines.append(" ".join(current_line))
    return "\n".join(lines)


# ── Bot A: Plain LLM ──


def ask_bot_a(
    question: str,
    kb_markdown: str,
    model: str,
    history: list[dict],
) -> tuple[str, float]:
    """Send question to plain LLM and return response + elapsed time."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT_PLAIN.format(kb_markdown=kb_markdown)}]
    messages.extend(history)
    messages.append({"role": "user", "content": question})

    start = time.monotonic()
    response = ollama_lib.chat(model=model, messages=messages)
    elapsed = (time.monotonic() - start) * 1000

    return response["message"]["content"], elapsed


# ── Bot B: LLM + Euclid-MCP ──

import json
import re as _re


def _parse_text_tool_call(text: str) -> tuple[str, dict] | None:
    """Fallback: extract tool call from text if model outputs it as JSON string.

    Handles various patterns the model might produce.
    """
    # Find all JSON-like objects in text
    for match in _re.finditer(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text):
        try:
            obj = json.loads(match.group())
            name = obj.get("name", "")
            if name not in ("reason", "diagnose", "what_if", "check_kb"):
                continue
            args = obj.get("parameters", obj.get("arguments", {}))
            if not isinstance(args, dict):
                continue
            # Fix common query syntax errors
            if "query" in args:
                args["query"] = _fix_query_syntax(args["query"])
            return name, args
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def _fix_query_syntax(query: str) -> str:
    """Fix common Euclid-IR syntax errors the model produces."""
    # Fix "$var = value" or "$var='value'" patterns -> just value
    query = _re.sub(r"\$\w+\s*=\s*'([^']*)'", r'\1', query)
    query = _re.sub(r'\$\w+\s*=\s*"([^"]*)"', r'\1', query)
    query = _re.sub(r'\$\w+\s*=\s*(\w+)', r'\1', query)
    # Fix ? wildcards -> $var
    query = query.replace('?', '$x')
    # Fix * wildcards -> $any
    query = query.replace('*', '$any')
    return query


def ask_bot_b(
    question: str,
    kb_euclid: str,
    model: str,
    history: list[dict],
) -> tuple[str, list, float]:
    """Send question to LLM with tool calling. Returns response, new history, elapsed."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT_EUCLID}]
    messages.extend(history)
    messages.append({"role": "user", "content": question})

    start = time.monotonic()

    # First call — model may request tool use
    response = ollama_lib.chat(model=model, messages=messages, tools=EUCLID_TOOLS)

    tool_calls_used = []

    # Process tool calls iteratively (up to 3 rounds)
    for _ in range(3):
        # Check for structured tool calls
        has_tool_calls = bool(response["message"].get("tool_calls"))

        # Fallback: parse text-based tool calls if model output them as text
        if not has_tool_calls and response["message"].get("content"):
            parsed = _parse_text_tool_call(response["message"]["content"])
            if parsed:
                func_name, func_args = parsed
                # Inject structured tool call into message
                response["message"]["tool_calls"] = [{
                    "function": {
                        "name": func_name,
                        "arguments": func_args,
                    }
                }]
                has_tool_calls = True

        if not has_tool_calls:
            break

        # Append assistant message with tool calls
        messages.append(response["message"])

        # Execute each tool call
        for tc in response["message"]["tool_calls"]:
            func_name = tc["function"]["name"]
            func_args = dict(tc["function"]["arguments"])
            # Fix query syntax for reason/diagnose/what_if
            if "query" in func_args:
                func_args["query"] = _fix_query_syntax(func_args["query"])
            if "modifications" in func_args:
                func_args["modifications"] = _fix_query_syntax(func_args["modifications"])
            tool_calls_used.append((func_name, func_args))

            result = execute_tool(func_name, func_args, kb_euclid)
            messages.append({"role": "tool", "content": result})

        # Second call — model interprets results
        response = ollama_lib.chat(model=model, messages=messages, tools=EUCLID_TOOLS)

    elapsed = (time.monotonic() - start) * 1000
    return response["message"]["content"], tool_calls_used, elapsed


# ── Display ──


def display_results(
    question: str,
    resp_a: tuple[str, float] | None,
    resp_b: tuple[str, list, float] | None,
):
    """Display side-by-side results."""
    print()
    print_header(f"You: {question}")

    if resp_a:
        text_a, time_a = resp_a
        print()
        print(f"  {C.BOLD}{C.GREEN}PLAIN LLM{C.RESET} {C.DIM}(llama3.1:8b, no reasoning engine){C.RESET}")
        print(f"  {C.DIM}Time: {time_a:.0f}ms{C.RESET}")
        print()
        for line in format_plain_response(text_a).splitlines():
            print(f"  {C.GREEN}{line}{C.RESET}")
        print()

    if resp_b:
        text_b, tool_calls, time_b = resp_b
        print(f"  {C.BOLD}{C.CYAN}EUCLID-MCP{C.RESET} {C.DIM}(llama3.1:8b + Prolog engine){C.RESET}")
        print(f"  {C.DIM}Time: {time_b:.0f}ms{C.RESET}")
        if tool_calls:
            print(f"  {C.YELLOW}Tools called:{C.RESET}")
            for name, args in tool_calls:
                args_str = ", ".join(f"{k}={v}" for k, v in args.items())
                print(f"    {C.MAGENTA}→ {name}({args_str}){C.RESET}")
        print()
        for line in format_plain_response(text_b).splitlines():
            print(f"  {C.CYAN}{line}{C.RESET}")
        print()

    print_separator()


def print_help():
    print(f"""
{C.BOLD}Commands:{C.RESET}
  {C.CYAN}quit{C.RESET} / {C.CYAN}exit{C.RESET}    Exit the demo
  {C.CYAN}help{C.RESET}          Show this help
  {C.CYAN}clear{C.RESET}         Clear conversation history
  {C.CYAN}switch{C.RESET}        Toggle bot display (both / a-only / b-only)
  {C.CYAN}history{C.RESET}       Show conversation history

{C.BOLD}Try these questions:{C.RESET}
  - Who can deploy to production?
  - Which users have stale access?
  - Can intern_01 write code?
  - Which production resources are not encrypted?
  - What if alice gets the sysadmin role?
  - Why can't a helpdesk user access secret data?
""")


# ── Question Execution ──


def run_question(
    question: str,
    kb_markdown: str,
    kb_euclid: str,
    model: str,
    history_a: list[dict],
    history_b: list[dict],
    show_a: bool,
    show_b: bool,
) -> None:
    """Ask both bots a question and display the side-by-side results."""
    resp_a = None
    resp_b = None

    if show_a:
        try:
            resp_a = ask_bot_a(question, kb_markdown, model, history_a)
            history_a.append({"role": "user", "content": question})
            history_a.append({"role": "assistant", "content": resp_a[0]})
        except Exception as e:
            resp_a = (f"Error: {e}", 0)
            print(f"{C.RED}Bot A error: {e}{C.RESET}")

    if show_b:
        try:
            resp_b = ask_bot_b(question, kb_euclid, model, history_b)
            history_b.append({"role": "user", "content": question})
            history_b.append({"role": "assistant", "content": resp_b[0]})
        except Exception as e:
            resp_b = (f"Error: {e}", [], 0)
            print(f"{C.RED}Bot B error: {e}{C.RESET}")

    display_results(question, resp_a, resp_b)


# ── Main Loop ──


def main():
    parser = argparse.ArgumentParser(description="LLM vs Euclid-MCP interactive demo")
    parser.add_argument("--model", default="llama3.1:8b", help="Ollama model to use")
    parser.add_argument("--bot-a-only", action="store_true", help="Show only plain LLM")
    parser.add_argument("--bot-b-only", action="store_true", help="Show only Euclid bot")
    parser.add_argument(
        "--scripted",
        action="store_true",
        help="Run preset questions in sequence, then exit",
    )
    parser.add_argument(
        "--pause",
        action="store_true",
        help="With --scripted: press Enter between questions",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="With --scripted: seconds to wait between questions (default: 1.5)",
    )
    args = parser.parse_args()

    model = args.model
    show_a = not args.bot_b_only
    show_b = not args.bot_a_only

    print(f"""
{C.BOLD}{C.CYAN}╔══════════════════════════════════════════════════════════════╗
║           LLM vs Euclid-MCP — Interactive Demo              ║
║                                                              ║
║  Same model ({model:20s})         ║
║  Same knowledge base (IT Security: 30 users, 50 resources)  ║
║  Bot A: plain LLM          Bot B: LLM + reasoning engine    ║
║                                                              ║
║  Speak freely in any language. Type 'help' for commands.     ║
╚══════════════════════════════════════════════════════════════╝{C.RESET}
""")

    # Check Ollama
    print(f"{C.DIM}Checking Ollama...{C.RESET}")
    if not check_ollama(model):
        sys.exit(1)
    print(f"{C.GREEN}Ollama OK, model '{model}' ready{C.RESET}")

    # Load knowledge base
    print(f"{C.DIM}Loading knowledge base...{C.RESET}")
    kb_euclid = load_kb_euclid()
    kb_markdown = generate_kb_markdown()
    print(f"{C.GREEN}KB loaded: {len(kb_euclid):,} bytes Euclid-IR, {len(kb_markdown):,} bytes markdown{C.RESET}")
    print()

    # Conversation history for each bot
    history_a: list[dict] = []
    history_b: list[dict] = []

    # Scripted mode: run preset questions and exit
    if args.scripted:
        n = len(SCRIPTED_QUESTIONS)
        pace = "press Enter" if args.pause else f"{args.delay:.1f}s pause"
        print(f"{C.YELLOW}Scripted mode: {n} preset questions, {pace} between them.{C.RESET}\n")
        for i, question in enumerate(SCRIPTED_QUESTIONS, start=1):
            print(f"{C.BOLD}{C.BLUE}▸ Question {i}/{n}:{C.RESET}")
            run_question(
                question, kb_markdown, kb_euclid, model,
                history_a, history_b, show_a, show_b,
            )
            if i < n and args.pause:
                try:
                    input(f"{C.DIM}Press Enter for the next question...{C.RESET}")
                except (KeyboardInterrupt, EOFError):
                    break
            elif i < n:
                time.sleep(args.delay)
        print(f"{C.GREEN}Demo complete.{C.RESET}")
        return

    # Interactive loop
    while True:
        try:
            question = input(f"{C.BOLD}{C.WHITE}You: {C.RESET}").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{C.DIM}Goodbye!{C.RESET}")
            break

        if not question:
            continue

        # Commands
        cmd = question.lower()
        if cmd in ("quit", "exit", "q"):
            print(f"{C.DIM}Goodbye!{C.RESET}")
            break
        if cmd == "help":
            print_help()
            continue
        if cmd == "clear":
            history_a.clear()
            history_b.clear()
            print(f"{C.YELLOW}Conversation cleared.{C.RESET}")
            continue
        if cmd == "switch":
            if show_a and show_b:
                show_a, show_b = False, True
                print(f"{C.YELLOW}Showing: Euclid bot only{C.RESET}")
            elif show_b:
                show_a, show_b = True, False
                print(f"{C.YELLOW}Showing: Plain LLM only{C.RESET}")
            else:
                show_a, show_b = True, True
                print(f"{C.YELLOW}Showing: Both bots{C.RESET}")
            continue
        if cmd == "history":
            if not history_a and not history_b:
                print(f"{C.DIM}No history yet.{C.RESET}")
            else:
                for msg in history_a:
                    role = msg["role"]
                    content = msg["content"][:80] + "..." if len(msg["content"]) > 80 else msg["content"]
                    print(f"  {C.DIM}[{role}]{C.RESET} {content}")
            continue

        run_question(
            question, kb_markdown, kb_euclid, model,
            history_a, history_b, show_a, show_b,
        )


if __name__ == "__main__":
    main()
