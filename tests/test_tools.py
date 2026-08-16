"""Unit tests for all 5 MCP tools: reason, explain, diagnose, what_if, check_kb."""

import asyncio
import hashlib
import json
import logging

from mcp import Client

from euclid_mcp.server import (
    check_kb,
    diagnose,
    explain,
    list_kbs,
    mcp,
    reason,
    register_kb,
    unregister_kb,
    what_if,
)

# =============================================================================
# reason
# =============================================================================


class TestReason:
    def test_happy_path(self):
        r = reason("human(socrates)\nmortal($x) IF human($x)\n? mortal($who)")
        assert r.error is None
        assert len(r.solutions) == 1
        assert r.solutions[0].substitutions["who"] == "socrates"
        assert r.solutions[0].proof.type in ("rule", "fact")

    def test_logs_call(self, caplog):
        with caplog.at_level(logging.INFO, logger="euclid_mcp.server"):
            reason("human(socrates)\n? human($who)")
        messages = [rec.getMessage() for rec in caplog.records]
        assert any("tool=reason" in m and "solutions=1" in m for m in messages)

    def test_multiple_solutions(self):
        r = reason(
            "parent(tom, bob)\nparent(tom, liz)\n? parent(tom, $who)",
            max_solutions=10,
        )
        assert r.error is None
        assert len(r.solutions) == 2
        names = {s.substitutions["who"] for s in r.solutions}
        assert names == {"bob", "liz"}

    def test_no_query(self):
        r = reason("human(socrates)")
        assert r.error is not None
        assert "No query" in r.error

    def test_override_query(self):
        r = reason(
            "human(socrates)\nhuman(plato)\n? human($who)",
            query="human(plato)",
        )
        assert r.error is None
        assert len(r.solutions) >= 1

    def test_repeated_same_kb_is_consistent(self):
        kb = (
            "parent(tom, bob)\nparent(bob, ann)\n"
            "ancestor($x, $y) IF parent($x, $y)\n"
            "ancestor($x, $y) IF parent($x, $z) AND ancestor($z, $y)\n"
        )
        r1 = reason(knowledge=kb, query="ancestor(tom, $who)", max_solutions=10)
        r2 = reason(knowledge=kb, query="ancestor(tom, $who)", max_solutions=10)
        assert r1.error is None and r2.error is None
        assert [
            s.substitutions for s in r1.solutions
        ] == [s.substitutions for s in r2.solutions]

    def test_query_param_overrides_embedded_query_on_cached_kb(self):
        kb = "parent(tom, bob)\nparent(tom, liz)\n? parent(tom, $who)"
        embedded = reason(knowledge=kb, max_solutions=10)
        overridden = reason(knowledge=kb, query="parent($who, bob)", max_solutions=10)
        assert embedded.error is None and overridden.error is None
        assert {s.substitutions.get("who") for s in embedded.solutions} == {"bob", "liz"}
        assert overridden.solutions[0].substitutions["who"] == "tom"

    def test_max_solutions(self):
        r = reason(
            "parent(tom, bob)\nparent(tom, liz)\nparent(tom, ann)\n? parent(tom, $who)",
            max_solutions=2,
        )
        assert r.error is None
        assert len(r.solutions) == 2

    def test_empty_kb(self):
        r = reason("? fact(x)")
        assert r.error is None
        assert len(r.solutions) == 0

    def test_no_query_even_with_garbage(self):
        r = reason("INVALID SYNTAX {{{{")
        assert r.error is not None
        assert "No query" in r.error

    def test_proof_tree_structure(self):
        r = reason("human(socrates)\nmortal($x) IF human($x)\n? mortal($who)")
        assert r.error is None
        proof = r.solutions[0].proof
        assert proof.goal is not None
        assert "mortal" in proof.goal


# =============================================================================
# diagnose
# =============================================================================


class TestDiagnose:
    def test_why_holds(self):
        r = diagnose(
            "human(socrates)\nmortal($x) IF human($x)",
            query="mortal(socrates)",
            mode="why",
        )
        assert r.error is None
        assert r.holds is True
        assert "HOLDS" in r.conclusion

    def test_why_fails(self):
        r = diagnose(
            "human(socrates)\nmortal($x) IF human($x)",
            query="mortal(plato)",
            mode="why",
        )
        assert r.error is None
        assert r.holds is False
        assert "NOT" in r.conclusion or "does not" in r.conclusion.lower()

    def test_why_not_fails(self):
        r = diagnose(
            "human(socrates)\nmortal($x) IF human($x)",
            query="mortal(plato)",
            mode="why_not",
        )
        assert r.error is None
        assert r.holds is False
        assert len(r.conclusion) > 0

    def test_why_not_holds(self):
        r = diagnose(
            "human(socrates)\nmortal($x) IF human($x)",
            query="mortal(socrates)",
            mode="why_not",
        )
        assert r.error is None
        assert r.holds is True
        assert "holds" in r.conclusion.lower()

    def test_what_needs(self):
        r = diagnose(
            "human(socrates)\nmortal($x) IF human($x)",
            query="mortal(plato)",
            mode="what_needs",
        )
        assert r.error is None
        assert r.holds is False
        assert len(r.conclusion) > 0

    def test_invalid_mode(self):
        r = diagnose(
            "human(socrates)",
            query="human(socrates)",
            mode="bogus",
        )
        assert r.error is not None
        assert "Invalid mode" in r.error

    def test_missing_predicate(self):
        r = diagnose(
            "human(socrates)",
            query="ghost($x)",
            mode="why",
        )
        assert r.error is None
        assert r.holds is False
        assert len(r.findings) > 0
        assert any(f.type == "missing_fact" for f in r.findings)

    def test_populates_solutions(self):
        r = diagnose(
            "human(socrates)\nmortal($x) IF human($x)",
            query="mortal(socrates)",
            mode="why",
        )
        assert r.error is None
        assert len(r.solutions) >= 1
        assert r.proof is not None


# =============================================================================
# what_if
# =============================================================================


class TestWhatIf:
    def test_add_fact(self):
        base = "human(socrates)\nmortal($x) IF human($x)"
        r = what_if(base_knowledge=base, modifications="+ human(plato)",
                 query="mortal($who)")
        assert r.error is None
        assert r.after_count > r.before_count
        assert r.delta == "more"
        assert "ENABLES" in r.conclusion or "increased" in r.conclusion.lower()

    def test_remove_fact(self):
        base = "human(socrates)\nhuman(plato)\nmortal($x) IF human($x)"
        r = what_if(base_knowledge=base, modifications="- human(socrates)",
                 query="mortal($who)")
        assert r.error is None
        assert r.after_count < r.before_count
        assert r.delta == "less"

    def test_add_and_remove(self):
        base = "human(socrates)\nhuman(plato)\nmortal($x) IF human($x)"
        r = what_if(
            base_knowledge=base,
            modifications="- human(socrates)\n+ human(alcibiades)",
            query="mortal($who)",
        )
        assert r.error is None
        assert r.after_count == r.before_count
        assert r.delta == "same"

    def test_and_separated_facts(self):
        base = "human(socrates)\nmortal($x) IF human($x)"
        r = what_if(base_knowledge=base,
                 modifications="+ human(plato) AND human(alcibiades)",
                 query="mortal($who)")
        assert r.error is None
        assert r.after_count == 3

    def test_and_separated_facts_lowercase(self):
        base = "human(socrates)\nmortal($x) IF human($x)"
        r = what_if(base_knowledge=base,
                 modifications="+ human(plato) and human(alcibiades)",
                 query="mortal($who)")
        assert r.error is None
        assert r.after_count == 3

    def test_no_modifications(self):
        r = what_if(base_knowledge="human(socrates)",
                 modifications="", query="human(socrates)")
        assert r.error is not None
        assert "No modifications" in r.error

    def test_add_then_remove_same_fact(self):
        base = "human(socrates)\nmortal($x) IF human($x)"
        r = what_if(base_knowledge=base,
                 modifications="+ human(plato)\n- human(plato)",
                 query="mortal($who)")
        assert r.error is None
        assert r.after_count >= r.before_count

    def test_modifications_label(self):
        base = "human(socrates)\nmortal($x) IF human($x)"
        r = what_if(base_knowledge=base, modifications="+ human(plato)",
                 query="mortal($who)")
        assert r.error is None
        assert "+ human(plato)" in r.modifications

    def test_solutions_before_and_after(self):
        base = "human(socrates)\nmortal($x) IF human($x)"
        r = what_if(base_knowledge=base, modifications="+ human(plato)",
                    query="mortal($who)")
        assert r.error is None
        assert len(r.solutions_before) >= 1
        assert len(r.solutions_after) >= 2


# =============================================================================
# check_kb
# =============================================================================


class TestCheckKB:
    def test_valid_kb(self):
        r = check_kb("human(socrates)\nmortal($x) IF human($x)\n? mortal($who)")
        assert r.valid is True
        assert len(r.errors) == 0
        assert r.facts_count == 1
        assert r.rules_count == 1

    def test_duplicates(self):
        r = check_kb("human(socrates)\nhuman(socrates)")
        assert r.valid is True
        assert len(r.warnings) >= 1
        assert any(w.type == "duplicate_fact" for w in r.warnings)

    def test_undefined_predicate(self):
        r = check_kb("mortal($x) IF ghost($x)")
        assert r.valid is False
        assert any(e.type == "undefined_predicate" for e in r.errors)

    def test_circular_rule(self):
        r = check_kb("ancestor($x, $y) IF ancestor($x, $z) AND ancestor($z, $y)")
        assert r.valid is False
        assert any(e.type == "circular_rule" for e in r.errors)

    def test_garbage_input_no_errors(self):
        r = check_kb("??? INVALID @#$%")
        assert r.valid is True
        assert r.facts_count == 0
        assert r.rules_count == 0

    def test_counts(self):
        r = check_kb(
            "a(1)\nb(2)\nc(3)\nr($x) IF a($x)\ns($x) IF b($x)\n? r($who)"
        )
        assert r.facts_count == 3
        assert r.rules_count == 2
        assert r.predicates_count == 5  # a, b, c, r, s

    def test_undefined_query_predicate(self):
        r = check_kb("human(socrates)\n? ghost($who)")
        assert r.valid is False
        assert any(
            e.type == "undefined_predicate" and "ghost" in e.message for e in r.errors
        )

    def test_valid_complex_kb(self):
        kb = """
parent(tom, bob)
parent(bob, ann)
parent(tom, liz)
ancestor($x, $y) IF parent($x, $y)
ancestor($x, $y) IF parent($x, $z) AND ancestor($z, $y)
? ancestor(tom, $who)
"""
        r = check_kb(kb)
        assert r.valid is True
        assert len(r.errors) == 0
        assert r.facts_count == 3
        assert r.rules_count == 2

    def test_predicate_inventory(self):
        r = check_kb(
            "can_access(a)\n"
            "can_access(b)\n"
            "user(u1)\n"
            "user(u2)\n"
            "allowed($x) IF can_access($x)\n"
            "? allowed($who)"
        )
        assert r.predicates_count == 3  # can_access, user, allowed
        by_name = {p.name: p for p in r.predicates}
        assert set(by_name) == {"can_access", "user", "allowed"}
        assert by_name["can_access"].arities == [1]
        assert by_name["can_access"].facts == 2
        assert by_name["can_access"].rules == 0
        assert by_name["user"].arities == [1]
        assert by_name["user"].facts == 2
        assert by_name["user"].rules == 0
        assert by_name["allowed"].arities == [1]
        assert by_name["allowed"].facts == 0
        assert by_name["allowed"].rules == 1

    def test_predicate_inventory_zero_arity_and_mixed(self):
        r = check_kb(
            "rainy\n"
            "snowy\n"
            "weather($x) IF rainy\n"
            "weather($x) IF snowy\n"
            "can_access(a, secret)\n"
            "? weather($w)"
        )
        by_name = {p.name: p for p in r.predicates}
        assert by_name["rainy"].arities == [0]
        assert by_name["rainy"].facts == 1
        assert by_name["snowy"].facts == 1
        assert by_name["weather"].rules == 2
        assert by_name["can_access"].arities == [2]

    def test_inconsistent_arity_warning(self):
        r = check_kb(
            "can_access(a)\n"
            "can_access(a, secret)\n"
            "? can_access($x)"
        )
        assert r.valid is True
        assert any(
            w.type == "inconsistent_arity"
            and "can_access" in w.message
            and "1, 2" in w.message
            for w in r.warnings
        )
        by_name = {p.name: p for p in r.predicates}
        assert by_name["can_access"].arities == [1, 2]

    def test_inconsistent_arity_absent_on_consistent_kb(self):
        r = check_kb("can_access(a)\ncan_access(b)\n? can_access($x)")
        assert not any(w.type == "inconsistent_arity" for w in r.warnings)


# =============================================================================
# Named KBs (C3): kb_id + delta_knowledge
# =============================================================================


class TestNamedKBs:
    def test_register_and_reason_by_kb_id(self):
        register_kb("rbac", "human(socrates)\nmortal($x) IF human($x)\n? mortal($who)")
        try:
            r = reason(kb_id="rbac")
            assert r.error is None
            assert r.solutions[0].substitutions["who"] == "socrates"
            assert r.content_hash == _sha256(
                "human(socrates)\nmortal($x) IF human($x)\n? mortal($who)"
            )
        finally:
            unregister_kb("rbac")

    def test_reason_with_delta_knowledge(self):
        base = "human(socrates)\nmortal($x) IF human($x)\n? mortal($who)"
        register_kb("rbac", base)
        try:
            r = reason(kb_id="rbac", delta_knowledge="human(plato)")
            assert r.error is None
            assert {s.substitutions["who"] for s in r.solutions} == {"socrates", "plato"}
            merged = base + "\n" + "human(plato)"
            assert r.content_hash == _sha256(merged)
        finally:
            unregister_kb("rbac")

    def test_delta_applies_to_all_tools(self):
        register_kb("rbac", "human(socrates)\nmortal($x) IF human($x)")
        try:
            assert explain(
                kb_id="rbac", delta_knowledge="human(plato)", query="mortal(plato)"
            ).error is None
            d = diagnose(
                kb_id="rbac", delta_knowledge="human(plato)", query="mortal(plato)"
            )
            assert d.holds is True
            c = check_kb(kb_id="rbac", delta_knowledge="human(plato)")
            assert c.valid is True
            assert c.facts_count == 2
            w = what_if(
                kb_id="rbac",
                delta_knowledge="human(plato)",
                modifications="+ human(aristotle)",
                query="mortal($who)",
            )
            assert w.error is None
            assert w.after_count == 3
        finally:
            unregister_kb("rbac")

    def test_precedence_explicit_knowledge_wins_over_kb_id(self):
        register_kb("rbac", "human(socrates)\n? human($who)")
        try:
            r = reason(
                "human(aristotle)",
                kb_id="rbac",
                query="human($who)",
            )
            assert r.error is None
            assert r.solutions[0].substitutions["who"] == "aristotle"
        finally:
            unregister_kb("rbac")

    def test_unknown_kb_id(self):
        r = reason(kb_id="does-not-exist", query="p($x)")
        assert r.error is not None
        assert "Unknown kb_id: does-not-exist" in r.error

    def test_kb_id_beats_preload_fallback(self):
        # no preload configured here; kb_id must resolve instead of
        # "No knowledge provided"
        register_kb("only_kb", "p(a)\n? p($x)")
        try:
            r = reason(kb_id="only_kb")
            assert r.error is None
            assert len(r.solutions) == 1
        finally:
            unregister_kb("only_kb")

    def test_unregister_makes_kb_id_unknown(self):
        register_kb("rbac", "p(a)\n? p($x)")
        assert unregister_kb("rbac")["removed"] is True
        assert reason(kb_id="rbac").error is not None

    def test_unregister_absent_returns_false(self):
        assert unregister_kb("never-registered")["removed"] is False

    def test_register_kb_overwrite(self):
        register_kb("rbac", "p(a)\n? p($x)")
        try:
            overwrite = register_kb("rbac", "q(b)\n? q($x)")
            assert overwrite["registered"] is True
            assert overwrite["facts"] == 1
            r = reason(kb_id="rbac")
            assert r.error is None
            assert len(r.solutions) == 1
        finally:
            unregister_kb("rbac")

    def test_register_kb_error_path(self):
        result = register_kb("broken", "mortal($x) IF ghost($x)")
        assert result["registered"] is False
        assert "not valid" in result["error"]

    def test_list_kbs_returns_metadata(self):
        register_kb("rbac", "p(a)\n? p($x)")
        try:
            listing = list_kbs()
            assert listing["count"] == 1
            entry = listing["kbs"][0]
            assert entry["kb_id"] == "rbac"
            assert entry["content_hash"] == _sha256("p(a)\n? p($x)")
            assert "source" not in entry
            assert entry["version"] is None
        finally:
            unregister_kb("rbac")

    def test_register_kb_returns_version_and_counts(self):
        result = register_kb(
            "vkb", "@version 3.0\np(a)\nq($x) IF p($x)\n? q($x)"
        )
        try:
            assert result["registered"] is True
            assert result["version"] == "3.0"
            assert result["facts"] == 1
            assert result["rules"] == 1
            assert result["predicates"] == 2
        finally:
            unregister_kb("vkb")

    def test_register_kb_respects_capacity(self, monkeypatch):
        from euclid_mcp.server import _kb_store

        monkeypatch.setattr(_kb_store, "max_kbs", 2)
        ids = ["cap_a", "cap_b"]
        try:
            for kb_id in ids:
                assert register_kb(kb_id, "p(a)\n? p($x)")["registered"] is True
            over = register_kb("cap_c", "p(a)\n? p($x)")
            assert over["registered"] is False
            assert "registry is full" in over["error"]
        finally:
            for kb_id in ids + ["cap_c"]:
                unregister_kb(kb_id)


# =============================================================================
# KB identity (C4): content_hash + version on every result
# =============================================================================


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class TestKBIdentity:
    def test_reason_returns_content_hash(self):
        kb = "human(socrates)\nmortal($x) IF human($x)\n? mortal($who)"
        r = reason(kb)
        assert r.error is None
        assert r.content_hash == _sha256(kb)

    def test_reason_version_from_directive(self):
        kb = "@version 2.5\nhuman(socrates)\n? human(socrates)"
        r = reason(kb)
        assert r.error is None
        assert r.version == "2.5"

    def test_reason_version_none_without_directive(self):
        r = reason("human(socrates)\n? human(socrates)")
        assert r.error is None
        assert r.version is None

    def test_identity_present_on_error_branch(self):
        kb = "human(socrates)"
        r = reason(kb)  # no query -> error branch
        assert r.error is not None
        assert r.content_hash == _sha256(kb)
        assert r.version is None

    def test_explain_identity(self):
        kb = "@version 1.3\nhuman(socrates)\n? human(socrates)"
        r = explain(kb)
        assert r.error is None
        assert r.content_hash == _sha256(kb)
        assert r.version == "1.3"

    def test_diagnose_identity(self):
        kb = "human(socrates)\nmortal($x) IF human($x)"
        r = diagnose(kb, query="mortal(socrates)")
        assert r.error is None
        assert r.content_hash == _sha256(kb)

    def test_what_if_identity_of_base_knowledge(self):
        base = "human(socrates)\nmortal($x) IF human($x)"
        r = what_if(base_knowledge=base, modifications="+ human(plato)",
                    query="mortal($who)")
        assert r.error is None
        assert r.content_hash == _sha256(base)

    def test_check_kb_identity(self):
        kb = "@version 4.2\nhuman(socrates)"
        r = check_kb(kb)
        assert r.valid is True
        assert r.content_hash == _sha256(kb)
        assert r.version == "4.2"

    def test_check_kb_identity_on_invalid(self):
        kb = "mortal($x) IF ghost($x)"
        r = check_kb(kb)
        assert r.valid is False
        assert r.content_hash == _sha256(kb)


# =============================================================================
# MCP in-memory protocol (MCP SDK v2 Client against the live MCPServer)
# =============================================================================


def _call_tool(name: str, arguments: dict) -> tuple[dict, bool]:
    """Call a tool over the in-memory MCP protocol and return parsed JSON."""
    async def run() -> tuple[dict, bool]:
        async with Client(mcp) as client:
            result = await client.call_tool(name, arguments)
        text = result.content[0].text if result.content else "{}"
        return json.loads(text), result.is_error

    return asyncio.run(run())


class TestMCPInMemory:
    def test_lists_all_tools(self):
        async def run():
            async with Client(mcp) as client:
                tools = await client.list_tools()
                return [t.name for t in tools.tools]

        names = asyncio.run(run())
        assert set(names) == {
            "reason", "explain", "diagnose", "what_if", "check_kb",
            "register_kb", "unregister_kb", "list_kbs",
        }

    def test_server_name(self):
        async def run():
            async with Client(mcp) as client:
                return client.server_info

        info = asyncio.run(run())
        assert info.name == "Euclid-MCP"

    def test_reason_tool_over_protocol(self):
        data, is_error = _call_tool(
            "reason",
            {
                "knowledge": (
                    "human(socrates)\nmortal($x) IF human($x)\n? mortal($who)"
                )
            },
        )
        assert is_error is False
        assert data["query"] == "mortal($who)"
        assert data["solutions"][0]["substitutions"]["who"] == "socrates"

    def test_explain_tool_over_protocol(self):
        data, is_error = _call_tool(
            "explain",
            {
                "knowledge": (
                    "human(socrates)\nmortal($x) IF human($x)\n? mortal($who)"
                )
            },
        )
        assert is_error is False
        assert data["query"] == "mortal($who)"
        assert data["explanations"][0]["substitutions"]["who"] == "socrates"
        assert len(data["explanations"][0]["steps"]) == 2

    def test_check_kb_tool_over_protocol(self):
        data, is_error = _call_tool(
            "check_kb", {"knowledge": "human(socrates)\nhuman(socrates)"}
        )
        assert is_error is False
        assert data["valid"] is True
        assert any(w["type"] == "duplicate_fact" for w in data["warnings"])

    def test_reason_error_over_protocol(self):
        data, is_error = _call_tool("reason", {"knowledge": "human(socrates)"})
        assert is_error is False
        assert data["error"] is not None
        assert "No query" in data["error"]

    def test_tools_expose_structured_output_schema(self):
        async def run():
            async with Client(mcp) as client:
                tools = await client.list_tools()
                return {t.name: t.output_schema for t in tools.tools}

        schemas = asyncio.run(run())
        for name in ("reason", "explain", "diagnose", "what_if", "check_kb"):
            assert schemas[name] is not None


# =============================================================================
# Rule IDs — end-to-end proof attribution
# =============================================================================


class TestRuleIDs:
    def test_reason_proof_carries_rule_id(self):
        r = reason(
            "human(socrates)\n"
            "mortal($x) IF human($x)  # rule: RBAC-0043\n"
            "? mortal($who)"
        )
        assert r.error is None
        assert r.solutions[0].proof.type == "rule"
        assert r.solutions[0].proof.rule_id == "RBAC-0043"

    def test_reason_no_id_keeps_rule_id_none(self):
        r = reason("human(socrates)\nmortal($x) IF human($x)\n? mortal($who)")
        assert r.error is None
        assert r.solutions[0].proof.type == "rule"
        assert r.solutions[0].proof.rule_id is None

    def test_reason_multi_hop_ids(self):
        kb = (
            "parent(tom, bob)\n"
            "parent(bob, ann)\n"
            "ancestor($x, $y) IF parent($x, $y)  # rule: BASE-1\n"
            "ancestor($x, $y) IF parent($x, $z) AND ancestor($z, $y)  # rule: REC-2\n"
            "? ancestor(tom, ann)"
        )
        r = reason(kb)
        assert r.error is None
        assert len(r.solutions) == 1
        proof = r.solutions[0].proof
        assert proof.type == "rule"
        assert proof.rule_id in ("BASE-1", "REC-2")
        nested = proof.subproof
        assert nested.type == "and"
        assert nested.right.type == "rule"
        assert nested.right.rule_id == "BASE-1"

    def test_reason_rule_id_on_fact_error(self):
        r = reason("p(a)  # rule: X\n? p(a)")
        assert r.error is not None
        assert "not allowed on a fact" in r.error

    def test_check_kb_duplicate_rule_id_warning(self):
        c = check_kb(
            "p(a)\n"
            "q($x) IF p($x)  # rule: R1\n"
            "s($x) IF p($x)  # rule: R1"
        )
        assert c.valid is True
        assert any(
            w.type == "duplicate_rule_id" and "R1" in w.message for w in c.warnings
        )

    def test_check_kb_unique_rule_ids_no_warning(self):
        c = check_kb(
            "p(a)\n"
            "q($x) IF p($x)  # rule: R1\n"
            "s($x) IF p($x)  # rule: R2"
        )
        assert c.valid is True
        assert not any(w.type == "duplicate_rule_id" for w in c.warnings)

    def test_hostile_rule_id_rejected(self):
        hostile = (
            "p(a)\n"
            "q($x) IF p($x)  # rule: '); halt.\n"
            "? q($who)"
        )
        r = reason(hostile)
        assert r.error is not None

    def test_hostile_rule_id_escaped_not_executed(self):
        kb = "p(a)\nq($x) IF p($x)  # rule: a'b\\c\n? q($who)"
        r = reason(kb)
        assert r.error is None
        assert r.solutions[0].proof.rule_id == "a'b\\c"

    def test_reason_rule_id_body_is_clean(self):
        kb = (
            "p(a)\n"
            "q($x) IF p($x)  # rule: R1\n"
            "? q($who)"
        )
        r = reason(kb)
        assert r.error is None
        proof = r.solutions[0].proof
        assert proof.rule_id == "R1"
        assert "euclid_rule_id" not in (proof.body or "")

    def test_reason_multi_hop_body_is_clean(self):
        kb = (
            "parent(tom, bob)\n"
            "parent(bob, ann)\n"
            "ancestor($x, $y) IF parent($x, $y)  # rule: BASE-1\n"
            "ancestor($x, $y) IF parent($x, $z) AND ancestor($z, $y)  # rule: REC-2\n"
            "? ancestor(tom, ann)"
        )
        r = reason(kb)
        assert r.error is None
        proof = r.solutions[0].proof
        assert proof.rule_id == "REC-2"
        assert "euclid_rule_id" not in (proof.body or "")
        assert proof.subproof.right.body == "parent(bob,ann)"
