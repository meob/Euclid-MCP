"""Parity tests for non-range-restricted rules and unbound query variables.

A rule whose head variable does not occur in the body (e.g.
``report($user) IF system_compromised``) proves with that variable still
free. Both backends must keep the solution and expose unbound query
variables as explicit ``null`` bindings:

* SWI-Prolog used to serialize such solutions as strings of fresh
  ``_28498``-style tokens (or drop them entirely before the ``@null``
  fix), while the native engine dropped them outright;

* SWI's nondeterministic fresh-variable names made proof trees differ
  run-to-run; they are normalized to the Euclid-IR wildcard ``_`` so
  proof trees are byte-identical across backends and across runs.
"""

import shutil

import pytest

from euclid_mcp.language import parse
from euclid_mcp.prolog_bridge import (
    _normalize_fresh_vars,
)
from euclid_mcp.prolog_bridge import (
    execute as prolog_execute,
)
from euclid_mcp.server import explain, reason
from euclid_mcp.translator import kb_to_decls_clauses

NEGATION_KB = (
    "unflagged($m) IF NOT merchant($m)\n"
    "merchant(m1) IF false\n"
    "? unflagged($any)\n"
)


def _backends() -> list[str]:
    backends = ["native"]
    if shutil.which("swipl"):
        backends.append("prolog")
    return backends


# ── solutions are kept with explicit None bindings ──────────────────────────


@pytest.mark.parametrize("backend", _backends())
def test_unbound_query_variable_yields_null_binding(backend, monkeypatch):
    # Negation over an empty declared predicate succeeds with the rule
    # variable still free.
    monkeypatch.setenv("EUCLID_BACKEND", backend)
    res = reason(knowledge=NEGATION_KB)
    assert res.error is None, f"{backend}: {res.error}"
    assert len(res.solutions) == 1
    assert res.solutions[0].substitutions == {"any": None}


@pytest.mark.parametrize("backend", _backends())
def test_non_range_restricted_rule_keeps_solution(backend, monkeypatch):
    monkeypatch.setenv("EUCLID_BACKEND", backend)
    res = reason(
        knowledge=(
            "report($user) IF system_compromised\n"
            "system_compromised\n"
            "? report($user)"
        )
    )
    assert res.error is None, f"{backend}: {res.error}"
    assert len(res.solutions) == 1
    assert res.solutions[0].substitutions == {"user": None}


@pytest.mark.parametrize("backend", _backends())
def test_partially_bound_solution_mixes_value_and_null(backend, monkeypatch):
    monkeypatch.setenv("EUCLID_BACKEND", backend)
    res = reason(knowledge="p($a, $b) IF q($a)\nq(a)\n? p($x, $y)")
    assert res.error is None, f"{backend}: {res.error}"
    assert len(res.solutions) == 1
    assert res.solutions[0].substitutions == {"x": "a", "y": None}


@pytest.mark.parametrize("backend", _backends())
def test_bound_variables_still_bind_normally(backend, monkeypatch):
    monkeypatch.setenv("EUCLID_BACKEND", backend)
    res = reason(knowledge="edge(a, b)\n? edge($from, $to)")
    assert res.error is None
    assert res.solutions[0].substitutions == {"from": "a", "to": "b"}


# ── proof trees agree across backends and runs ──────────────────────────────


@pytest.mark.skipif(shutil.which("swipl") is None, reason="requires swipl")
def test_proof_trees_identical_across_backends(monkeypatch):
    def run(backend: str):
        monkeypatch.setenv("EUCLID_BACKEND", backend)
        return reason(knowledge=NEGATION_KB)

    native = run("native")
    prolog = run("prolog")
    assert native.error is None and prolog.error is None
    assert [
        s.proof.model_dump() for s in native.solutions
    ] == [s.proof.model_dump() for s in prolog.solutions]
    top = native.solutions[0].proof
    assert top.type == "rule"
    assert top.goal == "unflagged(_)"


@pytest.mark.skipif(shutil.which("swipl") is None, reason="requires swipl")
def test_prolog_output_deterministic_across_runs():
    decls, clauses = kb_to_decls_clauses(parse(NEGATION_KB))
    first = [s.model_dump() for s in prolog_execute(decls, clauses, "unflagged($any)")]
    second = [s.model_dump() for s in prolog_execute(decls, clauses, "unflagged($any)")]
    assert first == second
    assert first[0]["proof"]["goal"] == "unflagged(_)"


@pytest.mark.parametrize("backend", _backends())
def test_explain_works_with_unbound_bindings(backend, monkeypatch):
    monkeypatch.setenv("EUCLID_BACKEND", backend)
    res = explain(knowledge=NEGATION_KB)
    assert res.error is None, f"{backend}: {res.error}"
    assert len(res.explanations) == 1
    assert res.explanations[0].steps


# ── user data is never rewritten by the wildcard normalization ──────────────


def test_normalize_fresh_vars_rewrites_only_internal_tokens():
    assert _normalize_fresh_vars("unflagged(_28498)") == "unflagged(_)"
    assert _normalize_fresh_vars("p(_12,q(_34))") == "p(_,q(_))"
    # Identifiers embedding underscores/digits have no token boundary.
    assert _normalize_fresh_vars("user_42(a_123)") == "user_42(a_123)"


def test_normalize_fresh_vars_leaves_quoted_data_intact():
    assert _normalize_fresh_vars("code('_999')") == "code('_999')"
    assert _normalize_fresh_vars('label("_777")') == 'label("_777")'


@pytest.mark.parametrize("backend", _backends())
def test_quoted_string_binding_survives_roundtrip(backend, monkeypatch):
    monkeypatch.setenv("EUCLID_BACKEND", backend)
    res = reason(knowledge='code("_123")\n? code($c)')
    assert res.error is None, f"{backend}: {res.error}"
    assert res.solutions[0].substitutions["c"] == "_123"
