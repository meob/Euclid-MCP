"""Tests for the pure-Python native engine (``euclid_mcp.ir_engine``).

These run without SWI-Prolog. They exercise the semantics that the native
engine must share with the Prolog backend: facts/rules, recursion,
conjunctions, negation as failure, arithmetic, rule ids, strings, wildcards,
depth/time limits and the ``EUCLID_BACKEND`` dispatcher.

See ``docs/NATIVE_ENGINE.md`` for the documented limitations (Unicode
tool-level tests are ``prolog_only`` and live in the main suite; the native
rejection behaviour is asserted there too).
"""

import shutil

import pytest

from euclid_mcp.engine import (
    BACKEND_NATIVE,
    BACKEND_PROLOG,
    execute,
    resolve_backend,
)
from euclid_mcp.ir_engine import solve_kb
from euclid_mcp.language import parse
from euclid_mcp.models import KB
from euclid_mcp.server import explain, reason

# ── Core deduction ───────────────────────────────────────────────────────────


def test_socrates_rule_and_rule_id():
    kb = parse(
        "human(socrates)\nhuman(plato)\n"
        "mortal($x) if human($x)  # RULE: BIO-001\n"
        "? mortal($who)"
    )
    sols = solve_kb(kb, max_solutions=5)
    assert [s.substitutions["who"] for s in sols] == ["plato", "socrates"]
    assert sols[0].proof.type == "rule"
    assert sols[0].proof.rule_id == "BIO-001"


def test_recursive_ancestor_order_and_multi_solution():
    kb = parse(
        "parent(tom, bob)\n"
        "parent(bob, ann)\n"
        "parent(ann, lisa)\n"
        "ancestor($x, $y) if parent($x, $y)\n"
        "ancestor($x, $y) if parent($x, $z) AND ancestor($z, $y)\n"
        "? ancestor($a, $b)"
    )
    sols = solve_kb(kb, max_solutions=10)
    pairs = [(s.substitutions["a"], s.substitutions["b"]) for s in sols]
    assert pairs == [
        ("ann", "lisa"),
        ("bob", "ann"),
        ("tom", "bob"),
        ("bob", "lisa"),
        ("tom", "ann"),
        ("tom", "lisa"),
    ]


def test_multi_hop_conjunction_shared_variable():
    kb = parse(
        "user_role(bob, admin)\n"
        "role_level(admin, 3)\n"
        "deploy_requires_level(prod, 2)\n"
        "can_deploy($user, $env) IF\n"
        "    user_role($user, $role) AND\n"
        "    role_level($role, $lvl) AND\n"
        "    deploy_requires_level($env, $min) AND\n"
        "    $lvl >= $min\n"
        "? can_deploy(bob, $env)"
    )
    sols = solve_kb(kb, max_solutions=5)
    assert [s.substitutions["env"] for s in sols] == ["prod"]


def test_arithmetic_comparison_all_operators():
    kb = parse(
        "threshold(10)\n"
        "value(12)\n"
        "value(5)\n"
        "ok($x) if value($x) AND threshold($t) AND $x > $t - 1\n"
        "? ok($v)"
    )
    assert [s.substitutions["v"] for s in solve_kb(kb, max_solutions=5)] == [12]

    kb = parse(
        "score(50)\n"
        "value(49)\n"
        "value(50)\n"
        "pass($x) if value($x) AND score($s) AND $x >= $s\n"
        "fail($x) if value($x) AND score($s) AND $x < $s\n"
        "? pass($v) AND fail($w)"
    )
    sols = solve_kb(kb, max_solutions=5)
    assert len(sols) == 1
    assert sols[0].substitutions == {"v": 50, "w": 49}


def test_is_binds_lhs():
    kb = parse(
        "threshold(10)\n"
        "doubled($x) if threshold($t) AND $x is $t * 2\n"
        "? doubled($v)"
    )
    assert [s.substitutions["v"] for s in solve_kb(kb, max_solutions=5)] == [20]


def test_unification_equality_keeps_term():
    kb = parse(
        "parent_level(role_level, 2)\n"
        "level($r, $v) IF parent_level($r, $base) AND $v = $base + 1\n"
        "? level(role_level, $who)"
    )
    sols = solve_kb(kb, max_solutions=5)
    assert [s.substitutions["who"] for s in sols] == ["2+1"]


def test_equals_unification_binds_variables():
    kb = parse(
        "person(alice)\n"
        "same_as($x, $y) if person($x) AND $y = $x\n"
        "? same_as(alice, $who)"
    )
    sols = solve_kb(kb, max_solutions=5)
    assert [s.substitutions["who"] for s in sols] == ["alice"]


def test_syntactic_equality_on_atoms():
    kb = parse(
        "mode(ready)\n"
        "deployable if mode($x) AND $x == ready\n"
        "? deployable"
    )
    assert [s.substitutions for s in solve_kb(kb, max_solutions=5)] == [{}]


# ── Negation ─────────────────────────────────────────────────────────────────


def test_negation_as_failure_success_case():
    kb = parse(
        "user(bob)\n"
        "user(alice)\n"
        "active(user_42)\n"
        "inactive($u) if user($u) AND NOT active($u)\n"
        "? inactive($who)"
    )
    assert [s.substitutions["who"] for s in solve_kb(kb, max_solutions=5)] == [
        "alice",
        "bob",
    ]


def test_negation_as_failure_failure_case():
    kb = parse(
        "active(user_42)\n"
        "blocked($u) if NOT active($u)\n"
        "? blocked($who)"
    )
    assert solve_kb(kb, max_solutions=5) == []


# ── Strings and wildcards ────────────────────────────────────────────────────


def test_string_literals_survive():
    kb = parse(
        'user(alice, "alice@example.com")\n'
        "user(bob, 'bob@corp.it')\n"
        "address(alice, 'Via Roma, 15')\n"
        "? user($who, $email) AND address($who, $addr)"
    )
    sols = solve_kb(kb, max_solutions=5)
    assert sols[0].substitutions == {
        "who": "alice",
        "email": "alice@example.com",
        "addr": "Via Roma, 15",
    }


def test_wildcard_anonymous_variable():
    kb = parse(
        "resource(db_prod, 5, secret, 2024, active, production)\n"
        "resource(db_staging, 5, public, 2024, active, staging)\n"
        "can_access($user, $res) IF "
        "user_role($user, admin) AND resource($res, _, secret, _, _, _)\n"
        "user_role(admin_user, admin)\n"
        "? can_access($who, $res)"
    )
    sols = solve_kb(kb, max_solutions=5)
    assert sols[0].substitutions == {"who": "admin_user", "res": "db_prod"}


def test_hyphenated_atom():
    kb = parse(
        "process(security-ops)\n"
        "? process($p)"
    )
    assert [s.substitutions["p"] for s in solve_kb(kb, max_solutions=5)] == [
        "security-ops"
    ]


# ── Limits ───────────────────────────────────────────────────────────────────


def test_max_solutions():
    kb = parse(
        "p(a)\np(b)\np(c)\np(d)\n? p($x)"
    )
    assert len(solve_kb(kb, max_solutions=2)) == 2


def test_depth_limit_blocks_recursion():
    kb = parse(
        "parent(tom, bob)\n"
        "parent(bob, ann)\n"
        "ancestor($x, $y) if parent($x, $y)\n"
        "ancestor($x, $y) if parent($x, $z) AND ancestor($z, $y)\n"
        "? ancestor(tom, $who)"
    )
    assert [s.substitutions["who"] for s in solve_kb(kb, max_depth=1)] == ["bob"]


def test_timeout_raises_matching_message():
    kb = parse(
        "p(a)\np(b)\nq($x) if p($x)\n? q($x)"
    )
    with pytest.raises(RuntimeError, match="Euclid engine timed out after 0s"):
        solve_kb(kb, max_solutions=5, timeout=0)


def test_query_parse_error_message():
    kb = KB(facts=["p(a)"], rules=[], query="p(a) extra")
    with pytest.raises(RuntimeError, match="Query parsing error"):
        solve_kb(kb, max_solutions=5)


# ── Integration through the tool layer ───────────────────────────────────────


def test_reason_and_explain_on_native(monkeypatch):
    monkeypatch.setenv("EUCLID_BACKEND", "native")
    res = reason(
        knowledge=(
            "user(alice)\n"
            "active(alice)\n"
            "blocked($u) if user($u) AND NOT active($u)\n"
            "? blocked($who)"
        ),
        max_solutions=5,
    )
    assert len(res.solutions) == 0
    assert res.error is None

    res = reason(
        knowledge=(
            "parent(tom, bob)\n"
            "parent(bob, ann)\n"
            "ancestor($x, $y) if parent($x, $y)\n"
            "ancestor($x, $y) if parent($x, $z) AND ancestor($z, $y)  # RULE: ANC-2\n"
            "? ancestor(tom, $who)"
        ),
        max_solutions=5,
    )
    assert len(res.solutions) == 2
    assert "ANC-2" in [s.proof.rule_id for s in res.solutions]

    exp = explain(
        knowledge=(
            "parent(tom, bob)\n"
            "parent(bob, ann)\n"
            "ancestor($x, $y) if parent($x, $y)\n"
            "ancestor($x, $y) if parent($x, $z) AND ancestor($z, $y)  # RULE: ANC-2\n"
            "? ancestor(tom, $who)"
        ),
        max_solutions=2,
    )
    steps = [s for e in exp.explanations for s in e.steps]
    assert any("ANC-2" in s for s in steps)


# ── Backend dispatcher ───────────────────────────────────────────────────────


def test_resolve_backend_defaults(monkeypatch):
    monkeypatch.delenv("EUCLID_BACKEND", raising=False)
    expected = BACKEND_PROLOG if shutil.which("swipl") else BACKEND_NATIVE
    assert resolve_backend() == expected


def test_resolve_backend_forced(monkeypatch):
    monkeypatch.setenv("EUCLID_BACKEND", "native")
    assert resolve_backend() == BACKEND_NATIVE
    monkeypatch.setenv("EUCLID_BACKEND", "prolog")
    assert resolve_backend() == BACKEND_PROLOG


def test_resolve_backend_auto_falls_back_without_swipl(monkeypatch):
    monkeypatch.setenv("EUCLID_BACKEND", "auto")
    monkeypatch.setattr("euclid_mcp.engine.shutil.which", lambda _: None)
    assert resolve_backend() == BACKEND_NATIVE


def test_resolve_backend_invalid_value(monkeypatch):
    monkeypatch.setenv("EUCLID_BACKEND", "bogus")
    with pytest.raises(ValueError, match="EUCLID_BACKEND"):
        resolve_backend()


def test_execute_native_via_env(monkeypatch):
    monkeypatch.setenv("EUCLID_BACKEND", "native")
    kb = parse("p(a)\n? p($x)")
    sols = execute("p(a)\n? p($x)", kb, max_solutions=5, timeout=30)
    assert [s.substitutions["x"] for s in sols] == ["a"]
