"""Native Euclid-IR term parser (pure Python, no SWI-Prolog).

Parses the normalized strings produced by ``language.parse`` into a small
term tree that the native engine (:mod:`euclid_mcp.ir_engine`) can reason
over. Grammar:

    term    ::= NUMBER | STRING | VAR | '_' | ATOM | ATOM '(' term,... ')'
                 | '(' expr ')'
    expr    ::= term (('+'|'-'|'*'|'/') term)*          (left-assoc, */ binds tighter)
    goal    ::= ['not'] expr [op expr]
    op      ::= '>' | '>=' | '<' | '<=' | '==' | '!=' | 'is' | '='

Examples::

    parent(tom, bob)                compound parent [atom tom, atom bob]
    $days > 90                      compound > [var days, number 90]
    $level = $parent_level + 1      compound = [var level, compound + [...]]
    not active($u)                  compound not [compound active [...]]

Operators map to ``Compound`` functors with the same symbol, so the engine
can evaluate ``+ - * /`` lazily inside ``is`` and comparisons.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import NamedTuple, Union

Term = Union["Var", "Atom", "Number", "Compound"]


class Token(NamedTuple):
    kind: str
    value: str


class VarCounter:
    """Fresh-variable id generator, scoped to a single solve() call.

    The same ``$name`` always resolves to the same :class:`Var` (so a rule's
    head and body share variables, and repeated ``$x`` in one goal is one
    variable). Anonymous ``_`` occurrences get a fresh Var each time.
    """

    def __init__(self) -> None:
        self._next = 0
        self._by_name: dict[str, Var] = {}

    def var(self, name: str, anon: bool = False) -> Var:
        if anon:
            return self.fresh("_", anon=True)
        existing = self._by_name.get(name)
        if existing is None:
            existing = self.fresh(name)
            self._by_name[name] = existing
        return existing

    def fresh(self, name: str, anon: bool = False) -> Var:
        n = self._next
        self._next += 1
        return Var(n, name, anon=anon)


@dataclass(frozen=True)
class Var:
    id: int
    name: str
    anon: bool = False


@dataclass(frozen=True)
class Atom:
    name: str
    quoted: bool = False


@dataclass(frozen=True)
class Number:
    value: int | float


@dataclass(frozen=True)
class Compound:
    functor: str
    args: tuple[Term, ...]


# ── Lexer ───────────────────────────────────────────────────────────────────

# Characters allowed inside an unquoted atom (beyond [A-Za-z0-9_]).
_ATOM_EXTRA = "@._+-"

# Infix operators expressed as punctuation.
_MULTI_CHAR_OPS = (">=", "<=", "==", "!=")
_SINGLE_CHAR_OPS = {">", "<", "=", "*", "/"}

# Words that act as infix operators (Euclid-IR keywords).
_WORD_OPS = {"is", "+", "-"}

_QUERY_CONJUNCTION = re.compile(r"\s+and\s+", re.IGNORECASE)

# Lowercase var pattern:  $name  (name = [a-z][a-zA-Z0-9_]*)
_VAR_RE = re.compile(r"\$([a-z][a-zA-Z0-9_]*)")

_ATOM_RE = re.compile(r"[A-Za-z0-9@._+\-]+")


def _read_string(text: str, i: int) -> tuple[str, int]:
    """Read a quoted string starting at ``text[i]``; return (content, next index)."""
    quote = text[i]
    j = i + 1
    out: list[str] = []
    while j < len(text):
        ch = text[j]
        if ch == "\\":
            if j + 1 < len(text):
                out.append(text[j + 1])
                j += 2
                continue
            out.append(ch)
            j += 1
        elif ch == quote:
            return "".join(out), j + 1
        else:
            out.append(ch)
            j += 1
    raise ValueError("Unterminated string literal")


def _read_number(text: str, i: int) -> tuple[int | float, int]:
    """Read an (optionally signed) int or float literal; return (value, next index)."""
    j = i
    if text[j] in "+-":
        j += 1
    while j < len(text) and text[j].isdigit():
        j += 1
    is_float = False
    if j < len(text) and text[j] == "." and j + 1 < len(text) and text[j + 1].isdigit():
        is_float = True
        j += 1
        while j < len(text) and text[j].isdigit():
            j += 1
    s = text[i:j]
    return (float(s) if is_float else int(s)), j


def _lex(text: str) -> list[Token]:
    """Tokenize a single goal or term into ``(kind, value)`` tokens."""
    tokens: list[Token] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in " \t":
            i += 1
        elif ch == "(":
            tokens.append(Token("lparen", ""))
            i += 1
        elif ch == ")":
            tokens.append(Token("rparen", ""))
            i += 1
        elif ch == ",":
            tokens.append(Token("comma", ""))
            i += 1
        elif ch in "\"'":
            content, i = _read_string(text, i)
            tokens.append(Token("str", content))
        elif ch == "$":
            m = _VAR_RE.match(text, i)
            if not m:
                raise ValueError(f"Invalid variable token near {text[i:i + 10]!r}")
            tokens.append(Token("var", m.group(1)))
            i = m.end()
        elif ch == "_" and (
            i + 1 >= n or not (text[i + 1].isalnum() or text[i + 1] in _ATOM_EXTRA)
        ):
            tokens.append(Token("anon", ""))
            i += 1
        elif ch.isdigit() or (
            ch in "+-"
            and i + 1 < n
            and text[i + 1].isdigit()
        ):
            value, i = _read_number(text, i)
            tokens.append(Token("num", str(value)))
        else:
            two = text[i : i + 2]
            if two in _MULTI_CHAR_OPS:
                tokens.append(Token("op", two))
                i += 2
            elif ch in ">":
                tokens.append(Token("op", ch))
                i += 1
            elif ch == "=":
                tokens.append(Token("op", ch))
                i += 1
            elif ch == "<":
                tokens.append(Token("op", ch))
                i += 1
            elif ch == "!":
                raise ValueError(
                    "Cut '!' is not supported by Euclid-IR"
                )
            elif ch in _SINGLE_CHAR_OPS:
                tokens.append(Token("op", ch))
                i += 1
            else:
                m = _ATOM_RE.match(text, i)
                if not m:
                    raise ValueError(f"Unexpected character {ch!r} in {text[i:i + 10]!r}")
                tokens.append(Token("word", m.group(0)))
                i = m.end()
    return tokens


# ── Parser ──────────────────────────────────────────────────────────────────


class _Parser:
    def __init__(self, tokens: list[Token], counter: VarCounter) -> None:
        self.toks = tokens
        self.i = 0
        self.counter = counter

    def peek(self) -> Token | None:
        return self.toks[self.i] if self.i < len(self.toks) else None

    def next(self) -> Token:
        tok = self.peek()
        if tok is None:
            raise ValueError("Unexpected end of input")
        self.i += 1
        return tok

    def parse(self) -> Term:
        tok = self.peek()
        if tok is not None and tok.kind == "word" and tok.value.lower() == "not":
            self.i += 1
            inner = self.parse()
            return Compound("not", (inner,))
        lhs = self.parse_expr()
        tok = self.peek()
        if tok is not None and tok.kind == "op":
            self.i += 1
            rhs = self.parse_expr()
            return Compound(tok.value, (lhs, rhs))
        if (
            tok is not None
            and tok.kind == "word"
            and tok.value.lower() in _WORD_OPS
        ):
            self.i += 1
            rhs = self.parse_expr()
            return Compound(tok.value.lower(), (lhs, rhs))
        return lhs

    def parse_expr(self) -> Term:
        node = self.parse_mul()
        while True:
            tok = self.peek()
            if tok is not None and tok.kind == "word" and tok.value in "+-":
                self.i += 1
                right = self.parse_mul()
                node = Compound(tok.value, (node, right))
            else:
                return node

    def parse_mul(self) -> Term:
        node = self.parse_atom()
        while True:
            tok = self.peek()
            if tok is not None and tok.kind == "op" and tok.value in "*/":
                self.i += 1
                right = self.parse_atom()
                node = Compound(tok.value, (node, right))
            else:
                return node

    def parse_atom(self) -> Term:
        tok = self.next()
        kind, value = tok.kind, tok.value
        if kind == "num":
            return Number(float(value) if "." in value else int(value))
        if kind == "str":
            return Atom(value, quoted=True)
        if kind == "var":
            return self.counter.var(value)
        if kind == "anon":
            return self.counter.var("_", anon=True)
        if kind == "word":
            nxt = self.peek()
            if nxt is not None and nxt.kind == "lparen":
                self.i += 1
                args = self.parse_args()
                return Compound(value, args)
            return Atom(value)
        if kind == "lparen":
            inner = self.parse_expr()
            end = self.next()
            if end.kind != "rparen":
                raise ValueError("Expected ')'")
            return inner
        raise ValueError(f"Unexpected token in term: ({kind}, {value!r})")

    def parse_args(self) -> tuple[Term, ...]:
        args: list[Term] = []
        while True:
            tok = self.peek()
            if tok is None:
                raise ValueError("Expected ')'")
            if tok[0] == "rparen":
                self.i += 1
                return tuple(args)
            if tok[0] == "comma":
                self.i += 1
                continue
            args.append(self.parse_expr())


def parse_goal(text: str, counter: VarCounter) -> Term:
    """Parse a single Euclid-IR goal (or negated / infix-expression goal)."""
    toks = _lex(text)
    if not toks:
        raise ValueError("Empty goal")
    p = _Parser(toks, counter)
    goal = p.parse()
    if p.i != len(toks):
        raise ValueError(f"Unexpected token(s) in goal {text!r}")
    return goal


def parse_term(text: str, counter: VarCounter) -> Term:
    """Parse a single term (fact or rule head), not an infix expression."""
    toks = _lex(text.strip())
    if not toks:
        raise ValueError("Empty term")
    p = _Parser(toks, counter)
    term = p.parse_atom()
    if p.i != len(toks):
        raise ValueError(f"Unexpected token(s) in term {text!r}")
    return term


def split_goals(text: str) -> list[str]:
    """Split a conjunction into goal strings at top level.

    Handles ``AND``/``and`` separators and commas as conjunction separators,
    while keeping commas inside parentheses and quoted strings intact.
    """
    text = _QUERY_CONJUNCTION.sub(", ", text)
    parts: list[str] = []
    depth = 0
    in_str: str | None = None
    cur: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if in_str is not None:
            if ch == "\\" and i + 1 < n:
                cur.append(ch)
                cur.append(text[i + 1])
                i += 1
            elif ch == in_str:
                in_str = None
            cur.append(ch)
        elif ch in "\"'":
            in_str = ch
            cur.append(ch)
        elif ch == "(":
            depth += 1
            cur.append(ch)
        elif ch == ")":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
        i += 1
    parts.append("".join(cur).strip())
    return [p for p in parts if p]


def parse_goals(text: str, counter: VarCounter) -> list[Term]:
    """Parse a conjunction string (rule body or query) into goal terms."""
    return [parse_goal(p, counter) for p in split_goals(text)]


def query_var_names(query: str) -> list[str]:
    """Ordered, de-duplicated names of the ``$vars`` appearing in a query."""
    seen: set[str] = set()
    names: list[str] = []
    for vn in re.findall(r"\$([a-z][a-zA-Z0-9_]*)", query):
        if vn not in seen:
            seen.add(vn)
            names.append(vn)
    return names
