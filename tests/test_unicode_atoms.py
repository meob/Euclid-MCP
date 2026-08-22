"""Tests for Unicode atoms (\\p{L}) and ASCII-only case folding.

Unicode predicate/atom names are supported by **both** backends: SWI-Prolog
natively, and the native engine through its Unicode-aware lexer (see
docs/NATIVE_ENGINE.md). Tool-level tests below run unmarked so the suite
exercises parity on whichever backend is active; native-engine-specific
behaviour lives in ``tests/test_native_engine.py``.

Covers three historically divergent areas (fixed together, see
NEXT_STEPS.md / CHANGELOG):

* **non-ASCII variables** (``$città``, ``$кто``) — must survive parsing,
  translation (never quoted into atoms) and end-to-end unification;
* **NFC normalization** — decomposed (NFD) spellings must behave exactly
  like composed ones on every entry point;
* **string literals** — IR quoted values bind their *bare* content, never
  SWI string terms with quotes.
"""

import unicodedata

from euclid_mcp.ir_parser import query_var_names
from euclid_mcp.language import (
    VAR_NAME_RE,
    _fold_ascii,
    parse,
    strip_query_prefix,
)
from euclid_mcp.models import KB
from euclid_mcp.prolog_bridge import execute
from euclid_mcp.server import check_kb, reason, what_if
from euclid_mcp.translator import (
    _literal_to_prolog,
    _quote_goal,
    _translate_vars,
    _unmask_vars,
    build_query_snippet,
    kb_to_decls_clauses,
)

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


# ── non-ASCII variables ($città, $кто) ─────────────────────────────────────


def test_var_name_regex_accepts_non_ascii():
    assert VAR_NAME_RE.findall("$città + $кто + $x9") == ["città", "кто", "x9"]
    assert VAR_NAME_RE.findall("$9x $_x") == []  # digits/underscore can't lead


def test_non_ascii_variable_parses():
    kb = parse("city(roma)\ngrande($città) IF city($città)\n? grande($città)")
    assert kb.rules == ["grande($città) if city($città)"]
    assert kb.query == "grande($città)"


def test_query_var_names_unicode():
    assert query_var_names("父($chi) AND city($città)") == ["chi", "città"]


def test_translate_vars_masks_instead_of_translating():
    # Masking keeps the atom-quoter from ever seeing variables.
    assert _translate_vars("grande($città)") == "grande(__VAR_città__)"
    assert _unmask_vars("grande(__VAR_кто__)") == "grande(Кто)"


def test_quote_goal_never_quotes_variables():
    # A quoted 'Кто' would be an *atom*: it could never unify. Regression
    # for the SWI backend returning [] on Cyrillic variables. Note how the
    # unsafe-looking Cyrillic *predicate* still gets quoted, while the
    # masked variable never does.
    assert _quote_goal("grande(__VAR_città__)") == "grande(Città)"
    assert _quote_goal("родитель(__VAR_кто__)") == "'родитель'(Кто)"


def test_non_ascii_variable_end_to_end_prolog_bridge():
    decls, clauses = kb_to_decls_clauses(
        parse("city(roma)\ngrande($città) IF city($città)")
    )
    sols = execute(decls, clauses, "grande($città)")
    assert [s.substitutions["città"] for s in sols] == ["roma"]


def test_cyrillic_variable_end_to_end_prolog_bridge():
    decls, clauses = kb_to_decls_clauses(parse("родитель(толстой)"))
    sols = execute(decls, clauses, "родитель($кто)")
    assert [s.substitutions["кто"] for s in sols] == ["толстой"]


def test_query_snippet_binds_non_ascii_variables():
    sn = build_query_snippet("родитель($кто)")
    assert "Query = 'родитель'(Кто)" in sn
    assert "'кто': JКто" in sn


# ── NFC normalization (NFD input behaves exactly like NFC) ────────────────


def test_parse_normalizes_nfd_facts_and_queries():
    nfd = unicodedata.normalize("NFD", "città")
    kb = parse(f"{nfd}(roma)\n? {nfd}($quale)")
    assert kb.facts == ["città(roma)"]  # composed spelling
    assert kb.query == "città($quale)"


def test_strip_query_prefix_normalizes_nfc():
    nfd_q = unicodedata.normalize("NFD", "città") + "($x)"
    assert strip_query_prefix(nfd_q) == "città($x)"
    assert strip_query_prefix("? " + nfd_q) == "città($x)"


def test_nfc_fact_unifies_with_nfd_query():
    nfd = unicodedata.normalize("NFD", "città")
    decls, clauses = kb_to_decls_clauses(parse("città(roma)"))
    sols = execute(decls, clauses, f"{nfd}($quale)")
    assert [s.substitutions["quale"] for s in sols] == ["roma"]


def test_nfd_fact_unifies_with_nfc_query():
    nfd = unicodedata.normalize("NFD", "città")
    decls, clauses = kb_to_decls_clauses(parse(f"{nfd}(roma)"))
    sols = execute(decls, clauses, "città($quale)")
    assert [s.substitutions["quale"] for s in sols] == ["roma"]


# ── string literals bind bare values (never SWI string terms with quotes) ──


def test_literal_to_prolog_strips_quotes_and_escapes():
    assert _literal_to_prolog('"müller"') == "'müller'"
    assert _literal_to_prolog("'Via Roma, 15'") == "'Via Roma, 15'"
    # IR unescape (\x -> x) then Prolog single-quote escaping ('' for ').
    assert _literal_to_prolog('"a\\"b"') == "'a\"b'"
    assert _literal_to_prolog("'It\\'s'") == "'It''s'"


def test_string_literals_translate_to_single_quoted_atoms():
    decls, clauses = kb_to_decls_clauses(KB(facts=['user("müller", "münchen")']))
    assert "user('müller', 'münchen')." in "\n".join(clauses)


def test_string_literal_binds_bare_value_end_to_end():
    decls, clauses = kb_to_decls_clauses(parse('user("müller")\n? user($name)'))
    sols = execute(decls, clauses, "user($name)")
    assert [s.substitutions["name"] for s in sols] == ["müller"]


# ── server-level parity (runs on whichever backend is active) ──────────────


def test_reason_tool_non_ascii_variable():
    res = reason(
        knowledge="city(roma)\ngrande($città) IF city($città)\n? grande($città)"
    )
    assert res.error is None
    assert [s.substitutions["città"] for s in res.solutions] == ["roma"]


def test_reason_tool_nfd_spelling():
    nfd = unicodedata.normalize("NFD", "città")
    res = reason(knowledge=f"città(roma)\n? {nfd}($quale)")
    assert res.error is None
    assert [s.substitutions["quale"] for s in res.solutions] == ["roma"]
