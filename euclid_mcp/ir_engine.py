"""Native Euclid-IR inference engine (pure Python, no SWI-Prolog).

Implements the same semantics as the Prolog meta-interpreter in
``translator.META_INTERPRETER`` for small knowledge bases:

* facts, rules (with optional ``rule_id``), conjunctions,
* negation as failure (``not``),
* arithmetic ``> >= < <= == != is =`` with ``+ - * /`` expressions.

It produces the same ``ProofNode`` structure as the Prolog backend, so
``explain`` / ``diagnose`` / ``what_if`` work unchanged on top of ``reason``.

Limitations (by design): no cut / lists / findall / assert, depth-limited
recursion, and evaluation tuned for small KBs only. See
``docs/NATIVE_ENGINE.md``.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

from .ir_parser import (
    Atom,
    Compound,
    Number,
    Term,
    Var,
    VarCounter,
    parse_goals,
    parse_term,
    query_var_names,
)
from .models import KB, ProofNode, Solution

_COMPARISON_OPS = {">", ">=", "<", "<=", "==", "!="}
_ARITH_FUNCTORS = {"+", "-", "*", "/"}
_INFIX_FUNCTORS = _COMPARISON_OPS | _ARITH_FUNCTORS | {"=", "is"}


class _NotNumeric(RuntimeError):
    """Raised when an arithmetic operand is not a number (and cannot become one)."""


def _deref(t: Term, subst: dict[int, Term]) -> Term:
    while isinstance(t, Var) and t.id in subst:
        t = subst[t.id]
    return t


def _occurs(var: Var, t: Term, subst: dict[int, Term]) -> bool:
    t = _deref(t, subst)
    if isinstance(t, Var):
        return t.id == var.id
    if isinstance(t, Compound):
        return any(_occurs(var, a, subst) for a in t.args)
    return False


def _unify(a: Term, b: Term, subst: dict[int, Term]) -> dict[int, Term] | None:
    a = _deref(a, subst)
    b = _deref(b, subst)
    if isinstance(a, Var):
        if isinstance(b, Var) and a.id == b.id:
            return subst
        if _occurs(a, b, subst):
            return None
        s = dict(subst)
        s[a.id] = b
        return s
    if isinstance(b, Var):
        return _unify(b, a, subst)
    if isinstance(a, Number) and isinstance(b, Number):
        return subst if a.value == b.value else None
    if isinstance(a, Atom) and isinstance(b, Atom):
        return subst if a.name == b.name else None
    if isinstance(a, Compound) and isinstance(b, Compound):
        if a.functor != b.functor or len(a.args) != len(b.args):
            return None
        res: dict[int, Term] | None = subst
        for x, y in zip(a.args, b.args):
            if res is None:
                return None
            res = _unify(x, y, res)
        return res
    return None


def _eval_arith(t, subst) -> int | float:
    t = _deref(t, subst)
    if isinstance(t, Number):
        return t.value
    if isinstance(t, Var):
        raise RuntimeError("Arithmetic error: unbound variable in expression")
    if isinstance(t, Compound) and t.functor in _ARITH_FUNCTORS:
        if len(t.args) != 2:
            raise RuntimeError(f"Arithmetic operator '{t.functor}' takes two operands")
        left = _eval_arith(t.args[0], subst)
        right = _eval_arith(t.args[1], subst)
        op = t.functor
        if op == "+":
            return left + right
        if op == "-":
            return left - right
        if op == "*":
            return left * right
        return left / right  # '/' is float division, like Prolog
    raise _NotNumeric(
        f"Arithmetic error: {render(t, subst)} is not a numeric expression"
    )


def _term_eq(a, b) -> bool:
    if isinstance(a, Number) and isinstance(b, Number):
        return a.value == b.value
    if isinstance(a, Atom) and isinstance(b, Atom):
        return a.name == b.name
    if isinstance(a, Compound) and isinstance(b, Compound):
        return a.functor == b.functor and len(a.args) == len(b.args) and all(
            _term_eq(x, y) for x, y in zip(a.args, b.args)
        )
    return False


def _syntactic_equal(a, b, subst) -> bool:
    x = _deref(a, subst)
    y = _deref(b, subst)
    if isinstance(x, Var) or isinstance(y, Var):
        raise RuntimeError(
            "Cannot compare unbound variables with '=='/'!='"
        )
    return _term_eq(x, y)


def render(t, subst) -> str:
    """Render a term under a substitution, Prolog ``term_string``-style."""
    t = _deref(t, subst)
    if isinstance(t, Number):
        return str(t.value)
    if isinstance(t, Atom):
        if t.quoted:
            content = t.name.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{content}"'
        return t.name
    if isinstance(t, Var):
        return f"_G{t.id}"
    if isinstance(t, Compound):
        if t.functor == "not":
            inner = ",".join(render(a, subst) for a in t.args)
            return f"\\+{inner}"
        if t.functor in _INFIX_FUNCTORS and len(t.args) == 2:
            left = render(t.args[0], subst)
            right = render(t.args[1], subst)
            sep = " " if t.functor == "is" else ""
            return f"{left}{sep}{t.functor}{sep}{right}"
        inner = ",".join(render(a, subst) for a in t.args)
        return f"{t.functor}({inner})"
    raise RuntimeError(f"Cannot render term: {t!r}")


def _json_value(t, subst):
    t = _deref(t, subst)
    if isinstance(t, Number):
        return t.value
    if isinstance(t, Atom):
        return t.name
    if isinstance(t, Compound):
        return render(t, subst)
    raise RuntimeError(f"Cannot serialize term: {t!r}")


def _fresh(t: Term, mapping: dict[int, Var], counter: VarCounter) -> Term:
    if isinstance(t, Var):
        if t.anon:
            return counter.fresh("_", anon=True)
        if t.id not in mapping:
            mapping[t.id] = counter.fresh(t.name)
        return mapping[t.id]
    if isinstance(t, Compound):
        return Compound(t.functor, tuple(_fresh(a, mapping, counter) for a in t.args))
    return t


def _pred_of_text(statement: str) -> str:
    return statement.split("(")[0].split(" ")[0]


_IF_RE = re.compile(r"\s+if\s+", re.IGNORECASE)


@dataclass
class _Clause:
    pred: str
    head: Term
    body: tuple[Term, ...]
    rule_id: str | None = None


class Program:
    """Parsed facts and rules, ordered like the Prolog backend.

    Statements are sorted by ``(predicate_name, statement_text)`` — the same
    key used by ``translator.kb_to_decls_clauses`` — so candidate order (and
    therefore solution order) mirrors the SWI-Prolog backend for typical KBs.
    """

    def __init__(self, kb: KB, counter: VarCounter) -> None:
        entries: list[tuple[str, str, bool, str, int | None]] = []
        for fact in kb.facts:
            entries.append((_pred_of_text(fact), fact, False, fact, None))
        for idx, rule in enumerate(kb.rules):
            head = _IF_RE.split(rule, maxsplit=1)[0].strip()
            entries.append((_pred_of_text(head), rule, True, rule, idx))
        entries.sort(key=lambda e: (e[0], e[1]))

        self._clauses: dict[str, list[_Clause]] = {}
        for pred, _, is_rule, text, ridx in entries:
            if is_rule:
                head_s, body_s = _IF_RE.split(text, maxsplit=1)
                head = parse_term(head_s, counter)
                body = tuple(parse_goals(body_s, counter))
                rule_id = (
                    kb.rule_ids.get(ridx) if ridx is not None else None
                )
                clause = _Clause(pred, head, body, rule_id)
            else:
                clause = _Clause(pred, parse_term(text, counter), ())
            self._clauses.setdefault(pred, []).append(clause)

    def clauses_for(self, pred: str) -> list[_Clause]:
        return self._clauses.get(pred, [])


class _Solver:
    def __init__(
        self,
        program: Program,
        goals: list,
        var_map: dict[str, Var],
        max_depth: int,
        max_solutions: int,
        timeout: int,
        counter: VarCounter,
    ) -> None:
        self.program = program
        self.goals = goals
        self.var_map = var_map
        self.max_depth = max_depth
        self.max_solutions = max_solutions
        self.timeout = timeout
        self.counter = counter
        self._deadline = time.monotonic() + timeout
        self._steps = 0

    def _check_deadline(self) -> None:
        self._steps += 1
        if time.monotonic() > self._deadline:
            raise RuntimeError(f"Euclid engine timed out after {self.timeout}s")

    def solve(self) -> list[Solution]:
        results: list[Solution] = []
        for subst, proof in self._prove_goals(self.goals, self.max_depth, {}):
            subs = self._build_substitutions(subst)
            if subs is None:
                continue
            results.append(Solution(substitutions=subs, proof=proof))
            if len(results) >= self.max_solutions:
                break
            self._check_deadline()
        return results

    def _build_substitutions(self, subst: dict[int, Term]) -> dict[str, object] | None:
        out: dict[str, object] = {}
        for name, var in self.var_map.items():
            t = _deref(var, subst)
            if isinstance(t, Var):
                return None  # unbound variable: dropped, like json_write groundness
            out[name] = _json_value(t, subst)
        return out

    def _prove_goals(self, goals, depth: int, subst: dict[int, Term]):
        self._check_deadline()
        if not goals:
            yield subst, ProofNode(type="true")
            return
        first, rest = goals[0], goals[1:]
        for s1, p1 in self._prove(first, depth, subst):
            if not rest:
                yield s1, p1
            else:
                for s2, p2 in self._prove_goals(rest, depth, s1):
                    yield s2, ProofNode(type="and", left=p1, right=p2)

    def _has_solution(self, goal: Term, depth: int, subst: dict[int, Term]) -> bool:
        for _ in self._prove(goal, depth, subst):
            return True
        return False

    def _prove(self, goal: Term, depth: int, subst: dict[int, Term]):
        goal_t = _deref(goal, subst)
        if isinstance(goal_t, Compound):
            f = goal_t.functor
            args = goal_t.args
            if f == "not":
                if len(args) != 1:
                    raise RuntimeError("'not' must take exactly one argument")
                inner = args[0]
                if not self._has_solution(inner, depth, subst):
                    yield subst, ProofNode(type="neg", goal=render(inner, subst))
                return
            if f in _COMPARISON_OPS:
                if self._compare(f, args, subst):
                    yield subst, ProofNode(type="true")
                return
            if f == "is":
                value = _eval_arith(args[1], subst)
                s = _unify(args[0], Number(value), subst)
                if s is not None:
                    yield s, ProofNode(type="true")
                return
            if f == "=":
                s = _unify(args[0], args[1], subst)
                if s is not None:
                    yield s, ProofNode(type="true")
                return
            if f in _ARITH_FUNCTORS:
                raise RuntimeError(
                    f"'{f}' is not a valid goal (use it inside 'is' or a comparison)"
                )
            yield from self._prove_predicate(goal_t, f, depth, subst)
        elif isinstance(goal_t, Atom):
            yield from self._prove_predicate(goal_t, goal_t.name, depth, subst)
        elif isinstance(goal_t, Var):
            return  # an unbound variable cannot be proven
        else:
            raise RuntimeError(f"Cannot prove goal {render(goal, subst)!r}")

    def _prove_predicate(self, goal_t: Term, pred: str, depth: int, subst: dict[int, Term]):
        for clause in self.program.clauses_for(pred):
            mapping: dict[int, Var] = {}
            head = _fresh(clause.head, mapping, self.counter)
            s = _unify(goal_t, head, subst)
            if s is None:
                continue
            if not clause.body:
                yield s, ProofNode(type="fact", goal=render(goal_t, s))
                continue
            if depth <= 0:
                continue
            body = tuple(_fresh(g, mapping, self.counter) for g in clause.body)
            for s2, body_proof in self._prove_goals(body, depth - 1, s):
                body_str = ",".join(render(g, s2) for g in body)
                yield s2, ProofNode(
                    type="rule",
                    goal=render(goal_t, s2),
                    body=body_str,
                    subproof=body_proof,
                    rule_id=clause.rule_id,
                )

    def _compare(self, op: str, args, subst) -> bool:
        if len(args) != 2:
            raise RuntimeError(f"'{op}' requires two operands")
        a, b = args
        if op in ("==", "!="):
            # Numeric when both sides are numeric; otherwise syntactic equality
            # of ground terms (native extension: Prolog's '=:=' errors here).
            try:
                av = _eval_arith(a, subst)
                bv = _eval_arith(b, subst)
            except _NotNumeric:
                eq = _syntactic_equal(a, b, subst)
                return not eq if op == "!=" else eq
            return av == bv if op == "==" else av != bv
        av = _eval_arith(a, subst)
        bv = _eval_arith(b, subst)
        try:
            if op == ">":
                return av > bv
            if op == ">=":
                return av >= bv
            if op == "<":
                return av < bv
            if op == "<=":
                return av <= bv
        except TypeError:
            raise RuntimeError(
                f"Arithmetic comparison error: {render(a, subst)} {op} {render(b, subst)}"
            )
        raise RuntimeError(f"Unknown comparison operator '{op}'")


def solve_kb(
    kb: KB,
    max_depth: int = 30,
    max_solutions: int = 1000,
    timeout: int = 30,
) -> list[Solution]:
    """Run a KB's query with the native engine; return ``Solution`` list."""
    if not kb.query:
        return []
    try:
        counter = VarCounter()
        program = Program(kb, counter)
        goals = parse_goals(kb.query, counter)
        var_map = {name: counter.var(name) for name in query_var_names(kb.query)}
        solver = _Solver(
            program, goals, var_map, max_depth, max_solutions, timeout, counter
        )
        return solver.solve()
    except ValueError as exc:
        raise RuntimeError(f"Query parsing error: {exc}") from exc
