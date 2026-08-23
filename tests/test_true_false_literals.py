"""Tests for the ``true``/``false`` body literals and backend parity.

The two words are reserved boolean literals usable only inside rule bodies:
``p IF true`` always succeeds, ``p IF false`` never does. This gives
knowledge bases a legitimate vocabulary-declaration idiom — rules-only KBs
declare the predicates whose facts arrive at query time via
``delta_knowledge``:

    merchant($m) IF false  # RULE: VOCAB-MERCHANT

Historically ``IF false`` crashed the SWI-Prolog backend with an opaque
``engine_error`` (``clause/2`` over the built-in ``false``/``fail``) while
the native engine failed cleanly, and ``IF true`` succeeded on Prolog but
failed natively. These tests pin identical behavior on both backends.

They also cover two latent bugs found while probing the idiom:

* zero-arity predicates were never declared dynamic nor registered in the
  engine workspace, so their clauses survived ``clear_workspace`` and
  duplicated across loads;
* any built-in named as a rule-body goal raised an opaque ``engine_error``
  on Prolog instead of failing cleanly like the native engine.
"""

import shutil

import pytest

from euclid_mcp.language import parse
from euclid_mcp.prolog_bridge import execute as prolog_execute
from euclid_mcp.server import (
    check_kb,
    explain,
    reason,
    register_kb,
    unregister_kb,
)
from euclid_mcp.translator import kb_to_decls_clauses

VOCAB_KB = (
    "# External input vocabulary (facts arrive via delta_knowledge)\n"
    "flagged($m) IF merchant($m) AND annual_combined_txn_volume($m, $n)"
    " AND $n > 1000000\n"
    "merchant($m) IF false  # RULE: VOCAB-MERCHANT\n"
    "annual_combined_txn_volume($m, $n) IF false  # RULE: VOCAB-TXN-VOL\n"
    "? flagged($who)\n"
)

VOCAB_DELTA = (
    "merchant(m1)\n"
    "annual_combined_txn_volume(m1, 2000000)\n"
)


def _backends() -> list[str]:
    backends = ["native"]
    if shutil.which("swipl"):
        backends.append("prolog")
    return backends


# ── reserved keywords at parse level ────────────────────────────────────────


def test_bare_boolean_facts_rejected():
    for text in ("false", "true"):
        with pytest.raises(ValueError, match="cannot be used as a fact"):
            parse(text)


def test_boolean_predicate_names_rejected():
    for text in ("false(x)", "true(x)"):
        with pytest.raises(ValueError, match="cannot be used as predicate name"):
            parse(text)


def test_boolean_as_argument_is_inert_data():
    # As an argument the word is plain atom data, not a goal.
    assert parse("parent(false, x)").facts == ["parent(false, x)"]


def test_boolean_rule_heads_rejected():
    for text in ("false IF anything", "true IF anything(x)"):
        with pytest.raises(ValueError):
            parse(text)


def test_body_literals_still_accepted():
    kb = parse("t IF true\nf2 IF false\n? t")
    assert kb.rules == ["t if true", "f2 if false"]


def test_boolean_query_goal_accepted():
    # A bare `false` query simply fails; `true` succeeds trivially.
    assert parse("? false").query == "false"


# ── translation ─────────────────────────────────────────────────────────────


def test_true_literal_translates_to_prolog_true():
    decls, clauses = kb_to_decls_clauses(parse("? t\nt IF true"))
    joined = "\n".join(clauses)
    assert "t :- true." in joined
    assert "t/0" in decls


def test_false_literal_translates_literally():
    _, clauses = kb_to_decls_clauses(parse("? f2\nf2 IF false"))
    assert "f2 :- false." in "\n".join(clauses)


def test_zero_arity_fact_is_declared_dynamic():
    # Regression: bare zero-arity statements used to miss their dynamic
    # declaration entirely, so the clause survived clear_workspace and
    # duplicated on every subsequent load.
    decls, _ = kb_to_decls_clauses(parse("rainy\n? rainy"))
    assert "rainy/0" in decls


# ── check_kb ────────────────────────────────────────────────────────────────


def test_check_kb_vocabulary_only_kb_is_green():
    res = check_kb(knowledge=VOCAB_KB)
    assert res.valid is True
    assert res.errors == []
    assert res.warnings == []
    names = {p.name for p in res.predicates}
    assert {"flagged", "merchant", "annual_combined_txn_volume"} <= names


def test_check_kb_unsatisfiable_guard_idiom_still_valid():
    res = check_kb(knowledge="merchant($m) IF 1 > 2\n? merchant($x)")
    assert res.valid is True
    assert res.warnings == []


# ── native-engine literals ──────────────────────────────────────────────────


def test_native_false_literal_never_proves(monkeypatch):
    monkeypatch.setenv("EUCLID_BACKEND", "native")
    res = reason(knowledge="? f2\nf2 IF false")
    assert res.error is None
    assert res.solutions == []


def test_native_true_literal_proof_nodes(monkeypatch):
    monkeypatch.setenv("EUCLID_BACKEND", "native")
    plain = reason(knowledge="? t\nt IF true")
    identified = reason(knowledge="? t\nt IF true  # RULE: T-001")
    assert [s.proof.type for s in plain.solutions] == ["fact"]
    assert [s.proof.type for s in identified.solutions] == ["rule"]
    assert identified.solutions[0].proof.rule_id == "T-001"


def test_native_negation_over_literals(monkeypatch):
    monkeypatch.setenv("EUCLID_BACKEND", "native")
    yes = reason(knowledge="? q(any)\nq($x) IF NOT false")
    no = reason(knowledge="? r(any)\nr($x) IF NOT true")
    assert len(yes.solutions) == 1
    assert no.solutions == []


# ── tool-level parity (identical results on every backend) ─────────────────


@pytest.mark.parametrize("backend", _backends())
def test_if_false_clean_empty_result(backend, monkeypatch):
    monkeypatch.setenv("EUCLID_BACKEND", backend)
    res = reason(knowledge=VOCAB_KB)
    assert res.error is None, f"{backend}: {res.error}"
    assert res.solutions == []


@pytest.mark.parametrize("backend", _backends())
def test_if_true_solution_shape_matches(backend, monkeypatch):
    monkeypatch.setenv("EUCLID_BACKEND", backend)
    plain = reason(knowledge="? t\nt IF true")
    identified = reason(knowledge="? t\nt IF true  # RULE: T-001")
    assert [s.proof.type for s in plain.solutions] == ["fact"]
    assert [(s.proof.type, s.proof.rule_id) for s in identified.solutions] == [
        ("rule", "T-001")
    ]


@pytest.mark.parametrize("backend", _backends())
def test_negation_over_literals_matches(backend, monkeypatch):
    monkeypatch.setenv("EUCLID_BACKEND", backend)
    yes = reason(knowledge="? q(any)\nq($x) IF NOT false")
    no = reason(knowledge="? r(any)\nr($x) IF NOT true")
    assert len(yes.solutions) == 1
    assert no.solutions == []


@pytest.mark.parametrize("backend", _backends())
def test_vocabulary_with_delta_knowledge(backend, monkeypatch):
    monkeypatch.setenv("EUCLID_BACKEND", backend)
    reg = register_kb(kb_id="tf-vocab-parity", knowledge=VOCAB_KB)
    try:
        assert reg["registered"] is True
        empty = reason(
            kb_id="tf-vocab-parity",
            delta_knowledge="merchant(m9)\nannual_combined_txn_volume(m9, 10)",
        )
        assert empty.error is None
        assert empty.solutions == []  # below threshold

        hit = reason(kb_id="tf-vocab-parity", delta_knowledge=VOCAB_DELTA)
        assert hit.error is None, f"{backend}: {hit.error}"
        assert [s.substitutions["who"] for s in hit.solutions] == ["m1"]
    finally:
        unregister_kb(kb_id="tf-vocab-parity")


@pytest.mark.parametrize("backend", _backends())
def test_negation_over_declared_predicate(backend, monkeypatch):
    # Bound goal (unsafe negation would warn anyway): a declared-but-empty
    # predicate behaves as an empty relation, so NOT holds.
    monkeypatch.setenv("EUCLID_BACKEND", backend)
    res = reason(
        knowledge=(
            "unflagged($m) IF NOT merchant($m)\n"
            "merchant(m1) IF false\n"
            "? unflagged(m9)"
        )
    )
    assert res.error is None
    assert len(res.solutions) == 1


@pytest.mark.parametrize("backend", _backends())
def test_builtin_body_goal_fails_cleanly(backend, monkeypatch):
    # atom_length/2 is a SWI-Prolog built-in: the meta-interpreter used to
    # raise permission_error inside clause/2 -> opaque engine_error.
    monkeypatch.setenv("EUCLID_BACKEND", backend)
    res = reason(knowledge="p($x) IF atom_length($x, $n)\natoms(a)\n? p($x)")
    assert res.error is None, f"{backend}: {res.error}"
    assert res.solutions == []


@pytest.mark.parametrize("backend", _backends())
def test_explain_on_true_literal_rule(backend, monkeypatch):
    monkeypatch.setenv("EUCLID_BACKEND", backend)
    res = explain(knowledge="? t\nt IF true  # RULE: T-001")
    assert res.error is None
    assert len(res.explanations) == 1
    assert res.explanations[0].steps


# ── workspace hygiene (Prolog persistent engine) ───────────────────────────


@pytest.mark.skipif(shutil.which("swipl") is None, reason="requires swipl")
def test_zero_arity_clause_does_not_leak_across_loads():
    # Regression: without its dynamic declaration the zero-arity clause was
    # never retracted by clear_workspace and duplicated on every reload.
    def run(source: str, query: str):
        decls, clauses = kb_to_decls_clauses(parse(source))
        return prolog_execute(decls, clauses, query)

    first = run("rainy\n? rainy", "rainy")
    second = run("rainy\n? rainy", "rainy")
    assert len(first) == 1
    assert len(second) == 1  # not duplicated by the reload

    polluting = run("t IF true\nq(any) IF NOT false\nr(any) IF NOT true", "")
    assert polluting == []
    fresh = run("? t\nt IF true", "t")
    assert len(fresh) == 1  # exactly one clause survived the earlier load
