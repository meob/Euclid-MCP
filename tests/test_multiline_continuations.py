"""Multi-line rule continuations: leading-AND style, REPL buffering, error UX.

Prolog habit writes continuations with the conjunction at the START of each
following line; Euclid-IR only supported the trailing style (each line ENDS
with ``and``). A leading-style rule used to be split at the first complete
body goal while the leftover ``AND ...`` lines became garbage facts —
accepted by ``language.parse``, rejected by both engines.

Covered here:

* the parser absorbs AND-leading continuations (and rejects orphans);
* the REPL holds a completed rule until the next line settles whether a
  continuation follows, and flushes held statements at EOF;
* engine errors are visible on stdout (they used to vanish into stderr).
"""

import pytest

from euclid_mcp.cli import _Repl
from euclid_mcp.language import parse
from euclid_mcp.server import reason

LEADING = (
    "dimmelo IF dimmi(3)\n"
    "dimmi(0)\n"
    "dimmi($x) IF $x > 0\n"
    "          AND $y is $x - 1\n"
    "          AND dimmi($y)\n"
    "? dimmelo\n"
)


# ── parser ──────────────────────────────────────────────────────────────────


def test_leading_and_continuation_parses_whole_rule():
    kb = parse(LEADING)
    assert kb.facts == ["dimmi(0)"]
    assert kb.rules == [
        "dimmelo if dimmi(3)",
        "dimmi($x) if $x > 0, $y is $x - 1, dimmi($y)",
    ]


def test_leading_and_with_rule_id_on_last_line():
    kb = parse("p($x) IF q($x)\n          AND r($x)  # RULE: R-1")
    assert kb.rules == ["p($x) if q($x), r($x)"]
    assert kb.rule_ids == {0: "R-1"}


def test_mixed_trailing_and_leading_styles():
    text = (
        "p($x) IF q($x) AND\n"
        "      r($x)\n"
        "      AND s($x)\n"
        "? p(a)"
    )
    kb = parse(text)
    assert kb.rules == ["p($x) if q($x), r($x), s($x)"]


def test_blank_lines_inside_continuation():
    text = "p IF q\n\n   AND r\n? p"
    assert parse(text).rules == ["p if q, r"]


def test_statement_after_completed_rule_is_not_absorbed():
    text = "p IF q\nr IF s\n? p"
    kb = parse(text)
    assert kb.rules == ["p if q", "r if s"]


def test_orphan_continuation_rejected():
    with pytest.raises(ValueError, match="continuation lines belong"):
        parse("and foo(x)")


def test_trailing_style_unchanged():
    kb = parse("p($x) IF q($x) AND\n          r($x)")
    assert kb.rules == ["p($x) if q($x), r($x)"]


# ── REPL buffering ──────────────────────────────────────────────────────────


def test_repl_holds_rule_until_continuation_settles():
    repl = _Repl()
    for line in LEADING.strip("\n").split("\n"):
        repl._process_line(line)
    # `? dimmelo` flushed and ran the query; every raw line — including the
    # AND-leading continuations — is committed to the session verbatim.
    text = repl._session_text()
    assert "AND $y is $x - 1" in text
    kb = parse(text)
    assert kb.rules == [
        "dimmelo if dimmi(3)",
        "dimmi($x) if $x > 0, $y is $x - 1, dimmi($y)",
    ]


def test_repl_fact_closes_a_held_rule():
    repl = _Repl()
    for line in ("p IF q", "AND r", "fact(a)", ""):
        repl._process_line(line)
    kb = parse(repl._session_text())
    assert kb.rules == ["p if q, r"]
    assert "fact(a)" in kb.facts


def test_repl_consecutive_rules_stay_separate():
    repl = _Repl()
    for line in ("a IF b", "c IF d", "? c"):
        repl._process_line(line)
    kb = parse(repl._session_text())
    assert kb.rules == ["a if b", "c if d"]


def test_repl_trailing_multiline_rule():
    """Continuation lines without IF must not flush as separate statements."""
    repl = _Repl()
    for line in (
        "dimmelo IF dimmi(3)",
        "dimmi(0)",
        "dimmi($x) IF $x > 0 AND",
        "          $y is $x - 1 AND",
        "          dimmi($y)",
        "",
    ):
        repl._process_line(line)
    kb = parse(repl._session_text())
    assert kb.facts == ["dimmi(0)"]
    assert kb.rules == [
        "dimmelo if dimmi(3)",
        "dimmi($x) if $x > 0, $y is $x - 1, dimmi($y)",
    ]


def test_repl_leading_and_mixed_style():
    repl = _Repl()
    for line in (
        "mortal($x) IF",
        "          human($x)",
        "          AND breathing($x)",
        "",
    ):
        repl._process_line(line)
    kb = parse(repl._session_text())
    assert kb.rules == ["mortal($x) if human($x), breathing($x)"]


def test_repl_end_to_end_query_on_held_rule(monkeypatch):
    monkeypatch.setenv("EUCLID_BACKEND", "native")
    repl = _Repl()
    for line in LEADING.strip("\n").split("\n"):
        repl._process_line(line)
    result = reason(knowledge=repl._session_text(), query="dimmelo")
    assert result.error is None
    assert len(result.solutions) == 1


# ── error visibility ────────────────────────────────────────────────────────


def test_repl_flush_error_printed_to_stdout(capsys):
    repl = _Repl()
    repl._process_line("p(a b)")  # lenient-looking, strict-parser reject
    out = capsys.readouterr().out
    assert "Error:" in out


def test_repl_engine_error_printed_to_stdout(monkeypatch, capsys):
    # Unknown predicates fail cleanly; a comparison over an unbound
    # variable is what produces a genuine engine error.
    monkeypatch.setenv("EUCLID_BACKEND", "native")
    repl = _Repl("q IF $x > 1")
    repl._process_line("? q")
    out = capsys.readouterr().out
    assert "Error:" in out
