"""Tests for example 13 (policy compiler): committed KBs + extraction pipeline.

Covers:
  - both committed KBs pass check_kb with no errors/warnings
  - reason over the committed KBs returns the expected bindings
  - rule ids are captured as trailing `# RULE:` comments
  - stage 1 parser (document_model) splits sections and normalizes slugs
  - stage 2 output parsing (llm_extractor.parse_model_output)
  - stage 3 assembly (extract.assemble_kb) keeps fragments and section markers
"""

import sys
from pathlib import Path

import pytest

from euclid_mcp.language import parse
from euclid_mcp.server import _run_check_kb, reason

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "13_policy_compiler"
sys.path.insert(0, str(EXAMPLES / "extract"))

from document_model import parse_source  # noqa: E402
from extract import assemble_kb  # noqa: E402
from llm_extractor import parse_model_output  # noqa: E402


def _kb(name: str) -> str:
    return (EXAMPLES / "kb" / f"{name}.euclid").read_text(encoding="utf-8")


class TestCommittedKbs:
    @pytest.mark.parametrize("name", ["access_control_policy", "ai_act_art6_3"])
    def test_valid(self, name):
        res = _run_check_kb(_kb(name))
        assert res.valid
        assert res.errors == []
        assert res.warnings == []

    def test_policy_rule_ids(self):
        kb = parse(_kb("access_control_policy"))
        assert set(kb.rule_ids.values()) == {
            "SEC-1-1", "SEC-1-2", "SEC-4-1", "SEC-5-1", "SEC-6-1", "SEC-7-1",
        }

    def test_ai_act_rule_ids(self):
        kb = parse(_kb("ai_act_art6_3"))
        assert set(kb.rule_ids.values()) == {
            f"AIACT-6-3-{i}" for i in range(1, 9)
        }


class TestPolicyReasoning:
    def _bindings(self, query: str) -> set[str]:
        res = reason(knowledge=_kb("access_control_policy"), query=query, max_solutions=20)
        assert res.error is None
        return {s.substitutions["who"] for s in res.solutions}

    def test_can_deploy_production(self):
        assert self._bindings("can_deploy($who, production)") == {"alice"}

    def test_can_deploy_staging(self):
        assert self._bindings("can_deploy($who, staging)") == {"alice", "bob", "carol"}

    def test_can_access_customer_db(self):
        assert self._bindings("can_access_data($who, customer_db)") == {"alice", "bob", "dave"}

    def test_can_access_pii_db(self):
        assert self._bindings("can_access_data($who, pii_db)") == {"alice", "dave"}

    def test_emergency_access_excludes_self_approved(self):
        assert self._bindings("emergency_access($who)") == {"bob"}

    def test_deroga_access(self):
        assert self._bindings("deroga_access_data($who, pii_db)") == {"alice"}

    def test_no_access_only_inactive(self):
        assert self._bindings("no_access($who)") == {"eve"}


class TestAiActReasoning:
    def _bindings(self, query: str) -> set[str]:
        res = reason(knowledge=_kb("ai_act_art6_3"), query=query, max_solutions=20)
        assert res.error is None
        return {s.substitutions["s"] for s in res.solutions}

    def test_high_risk(self):
        expected = {"hr_screening_01", "loan_score_04", "auto_review_05"}
        assert self._bindings("high_risk($s)") == expected

    def test_deroga_applicabile(self):
        assert self._bindings("deroga_applicabile($s)") == {"resume_rank_02"}

    def test_always_high_risk_profiling(self):
        assert self._bindings("always_high_risk($s)") == {"hr_screening_01", "loan_score_04"}

    def test_spam_filter_out_of_scope(self):
        assert self._bindings("high_risk(spam_filter_03)") == set()


class TestDocumentModel:
    def test_section_count_and_title(self):
        doc = parse_source(EXAMPLES / "source" / "access_control_policy.md")
        assert doc.title.startswith("POL-SEC-042")
        assert len(doc.sections) == 8

    def test_slug_normalizes_diacritics(self):
        doc = parse_source(EXAMPLES / "source" / "access_control_policy.md")
        ids = [s.id for s in doc.sections]
        assert "4_facolta_di_rilascio" in ids
        assert "1_oggetto_e_ambito_di_applicazione" in ids

    def test_blockquotes_are_skipped(self):
        doc = parse_source(EXAMPLES / "source" / "ai_act_art6_3.md")
        assert len(doc.sections) == 7
        assert all("EUR-Lex" not in s.text for s in doc.sections)

    def test_unsupported_format(self):
        from document_model import parse_source as ps

        with pytest.raises(NotImplementedError):
            ps(EXAMPLES / "source" / "missing.xml")


class TestLlmOutputParsing:
    def test_euclid_block_and_unsafe(self):
        output = (
            "SECTIONS-MODELED: yes\n"
            "```euclid\n"
            "can_deploy($u, $env) IF $level >= $min  # RULE: SEC-4-1\n"
            "```\n"
            "UNSAFE: procedure not formalizable\n"
        )
        res = parse_model_output("4_facolta_di_rilascio", output)
        assert res.modeled is True
        assert len(res.fragments) == 1
        assert "# RULE: SEC-4-1" in res.fragments[0]
        assert res.unsafe_reason == "procedure not formalizable"

    def test_no_output_is_not_modeled(self):
        res = parse_model_output("8_validita_e_revisione", "UNSAFE: review cadence\n")
        assert res.modeled is False
        assert res.unsafe_reason == "review cadence"


class TestAssembly:
    def test_assemble_kb_groups_sections(self):
        from llm_extractor import ExtractionResult

        doc = parse_source(EXAMPLES / "source" / "access_control_policy.md")
        results = [
            ExtractionResult(
                section_id=s.id,
                modeled=False,
                fragments=["can_access_system($u) IF user($u)  # RULE: SEC-1-1"]
                if s.id == "1_oggetto_e_ambito_di_applicazione"
                else [],
            )
            for s in doc.sections
        ]
        kb_text = assemble_kb(doc, results)
        assert "# RULE: SEC-1-1" in kb_text
        assert "# --- Sezione: 1_oggetto_e_ambito_di_applicazione ---" in kb_text
        assert "can_access_system" in kb_text
