"""Tests for Unicode atoms (\\p{L}) and ASCII-only case folding.

Unicode predicate/atom names are supported by **both** backends: SWI-Prolog
natively, and the native engine through its Unicode-aware lexer (see
docs/NATIVE_ENGINE.md). Tool-level tests below run unmarked so the suite
exercises parity on whichever backend is active; native-engine-specific
behaviour lives in ``tests/test_native_engine.py``.
"""

from euclid_mcp.language import _fold_ascii, parse
from euclid_mcp.models import KB
from euclid_mcp.prolog_bridge import execute
from euclid_mcp.server import check_kb, reason, what_if
from euclid_mcp.translator import build_query_snippet, kb_to_decls_clauses

# ── case folding ────────────────────────────────────────────────────────────


def test_fold_ascii_only():
    assert _fold_ascii("ABCБОГ父あxyz") == "abcБОГ父あxyz"
    assert _fold_ascii("Parent(TOM)") == "parent(tom)"


def test_facts_preserve_non_ascii_case():
    kb = parse("Бог(Иван)\n父(张三)\n? 父($c)")
    assert kb.facts == ["Бог(Иван)", "父(张三)"]


def test_ascii_fold_still_applies():
    kb = parse("Parent(TOM, Bob)\n? parent($who, $child)")
    assert kb.facts == ["parent(tom, bob)"]


def test_non_ascii_case_sensitive():
    kb = parse("БОГ(иван)\nбог(петр)")
    names = [f.split("(")[0] for f in kb.facts]
    assert names == ["БОГ", "бог"]  # distinct predicates, not folded


# ── translation to Prolog ───────────────────────────────────────────────────


def test_decls_and_clauses_quoted():
    kb = KB(facts=["Бог(Иван)", "父(张三)"], query="父($c)")
    decls, clauses = kb_to_decls_clauses(kb)
    assert "'Бог'/1" in decls
    assert "'父'/1" in decls
    joined = "\n".join(clauses)
    assert "'Бог'('Иван')." in joined
    assert "'父'('张三')." in joined


def test_rule_unicode():
    kb = KB(
        facts=["human(Сократ)", "父(张三)"],
        rules=["смертный($x) IF human($x)", "祖孙($x, $y) IF 父($x, $y)"],
        query="смертный($who)",
    )
    decls, clauses = kb_to_decls_clauses(kb)
    assert "'смертный'/1" in decls
    assert "'祖孙'/2" in decls
    joined = "\n".join(clauses)
    assert "'смертный'(X) :- human(X)." in joined
    assert "'祖孙'(X, Y) :- '父'(X, Y)." in joined


def test_rule_id_unicode():
    kb = parse("human(Сократ)\nсмертный($x) IF human($x) # RULE: Т-001")
    assert kb.rule_ids == {0: "Т-001"}
    decls, clauses = kb_to_decls_clauses(kb)
    sols = execute(decls, clauses, "смертный($w)")
    assert sols[0].proof.type == "rule"
    assert sols[0].proof.rule_id == "Т-001"


def test_query_snippet_unicode():
    sn = build_query_snippet("父($c)")
    assert "Query = '父'(C)" in sn
    sn2 = build_query_snippet("родитель($x, $y) AND human($x)")
    assert "Query = ('родитель'(X, Y), human(X))" in sn2


# ── end-to-end through the engine ───────────────────────────────────────────


def test_unicode_predicate_end_to_end():
    kb = KB(facts=["父(张三)", "父(李四)"], query="父($c)")
    decls, clauses = kb_to_decls_clauses(kb)
    sols = execute(decls, clauses, "父($c)")
    assert len(sols) == 2
    assert {s.substitutions["c"] for s in sols} == {"张三", "李四"}


def test_unicode_arg_end_to_end():
    kb = KB(facts=["Бог(Иван)"], query="Бог($who)")
    decls, clauses = kb_to_decls_clauses(kb)
    sols = execute(decls, clauses, "Бог($who)")
    assert [s.substitutions["who"] for s in sols] == ["Иван"]


def test_multi_predicate_unicode_kb():
    kb = parse(
        "父(张三)\nБог(Иван)\nсмертный($x) IF human($x) # RULE: Т-001\n"
        "human(Сократ)\n? 父($c)"
    )
    decls, clauses = kb_to_decls_clauses(kb)
    sols = execute(decls, clauses, "父($c)")
    assert [s.substitutions for s in sols] == [{"c": "张三"}]


# ── server-level tools ──────────────────────────────────────────────────────


def test_check_kb_unicode():
    res = check_kb(knowledge="父(张三)\n父(李四)\n? 父($c)")
    assert res.valid is True
    assert res.facts_count == 2
    assert res.predicates_count == 1


def test_reason_tool_unicode():
    res = reason(knowledge="父(张三)\n父(李四)\n? 父($c)")
    assert len(res.solutions) == 2
    assert {s.substitutions["c"] for s in res.solutions} == {"张三", "李四"}


def test_what_if_unicode():
    res = what_if(
        base_knowledge="human(Сократ)",
        modifications="+ human(Платон)",
        query="human($w)",
    )
    assert res.after_count == 2
    assert res.before_count == 1


def test_yaml_unicode():
    kb = parse("facts:\n  - 父(张三)\n  - 父(李四)\nquery: 父($c)")
    assert kb.facts == ["父(张三)", "父(李四)"]
