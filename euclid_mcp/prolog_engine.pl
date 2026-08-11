% prolog_engine.pl — persistent SWI-Prolog inference engine.
%
% JSON-lines protocol on stdin/stdout (one request per line, one response
% line per request). Commands:
%   {"command":"ping"}                              -> {"status":"ok"}
%   {"command":"load","decls":["p/1",...],
%    "clauses":"p(a).\nq(b,c)."}                    -> {"status":"ok","facts":N,"rules":M}
%       Clears every dynamic predicate from the previous workspace, declares
%       the given signatures dynamic and asserts the clauses. Clauses may
%       include the meta-interpreter (prove/3) and proof_to_json/2 rules,
%       which are provided by the Python side on every load.
%   {"command":"query","snippet":"<prolog>","timeout":30}
%       The snippet must bind the variable `Solutions` to a list of result
%       dicts (e.g. via findall/3). The engine replies with
%       {"status":"ok","solutions":[...]} or {"status":"timeout"}.
%   {"command":"assert","clause":"p(a)."}           -> {"status":"ok"}
%   {"command":"retract","clause":"p(a)."}          -> {"status":"ok","count":N}
%   {"command":"stats"}                             -> {"status":"ok","facts":N,"rules":M}
%   {"command":"halt"}                              -> {"status":"ok"} then exit
%
% The engine never builds knowledge itself: it executes Prolog snippets
% provided by the Python side. Euclid-IR translation stays in Python.

:- use_module(library(http/json)).
:- use_module(library(lists)).
:- use_module(library(readutil)).
:- use_module(library(time)).

main :-
    prompt(_, ''),
    loop.

loop :-
    read_line_to_string(user_input, Line),
    ( Line == end_of_file
    -> halt
    ; catch(handle_line(Line), _Error, emit(_{status:error, error:'engine_error'})),
      loop
    ).

handle_line(Line) :-
    ( catch(parse_line(Line, Request), Error, emit_error(Error))
    ; emit(_{status:error, error:'invalid_json'}),
      fail
    ),
    !,
    ( handle(Request)
    ; emit(_{status:error, error:'command_failed'})
    ).

handle_line(_) :- emit(_{status:error, error:'invalid_json'}).

parse_line(Line, Request) :-
    open_string(Line, Stream),
    json_read_dict(Stream, Request,
        [null(undefined), default_tag(euclid), value_string_as(atom)]),
    close(Stream).

% ── dispatch ──────────────────────────────────────────────────────────────

handle(Request) :-
    get_dict(command, Request, Command0),
    atom_string(Command0, CommandStr),
    atom_string(Command, CommandStr),
    command_handler(Command, Request).

command_handler(ping, _Request) :-
    emit(_{status:ok, engine:prolog}).

command_handler(load, Request) :-
    get_dict(decls, Request, Decls),
    get_dict(clauses, Request, Clauses),
    catch(
        ( clear_workspace,
          maplist(declare_dynamic, Decls),
          load_clauses(Clauses),
          stats(Facts, Rules),
          emit(_{status:ok, facts:Facts, rules:Rules}) ),
        Error,
        emit_error(Error)
    ).

command_handler(query, Request) :-
    get_dict(snippet, Request, SnippetAtom),
    ( get_dict(timeout, Request, Timeout) -> true ; Timeout = 30 ),
    catch(
        ( atom_string(SnippetAtom, SnippetStr),
          read_term_from_atom(SnippetStr, Snippet, [variable_names(Vars)]),
          call_with_time_limit(Timeout,
              ( call(Snippet),
                get_solutions(Vars, Solutions),
                emit(_{status:ok, solutions:Solutions}) ) ) ),
        time_limit_exceeded,
        emit(_{status:timeout})
    ).

command_handler(assert, Request) :-
    get_dict(clause, Request, ClauseAtom),
    catch(
        ( read_term_from_atom(ClauseAtom, Clause, []),
          assert_clause(Clause),
          emit(_{status:ok}) ),
        Error,
        emit_error(Error)
    ).

command_handler(retract, Request) :-
    get_dict(clause, Request, ClauseAtom),
    catch(
        ( read_term_from_atom(ClauseAtom, Clause, []),
          count_retract(Clause, Count),
          emit(_{status:ok, count:Count}) ),
        Error,
        emit_error(Error)
    ).

command_handler(stats, _Request) :-
    catch(
        ( stats(Facts, Rules),
          emit(_{status:ok, facts:Facts, rules:Rules}) ),
        Error,
        emit_error(Error)
    ).

command_handler(halt, _Request) :-
    emit(_{status:ok}),
    halt.

command_handler(Other, _Request) :-
    emit(_{status:error, error:Other}).

% read_term_from_atom/3 creates fresh variables, so the `Solutions`
% bound inside the snippet is not shared with the handler clause. The
% binding is retrieved by name from the variable_names/2 list.
get_solutions(Vars, Solutions) :-
    ( memberchk('Solutions'=V, Vars), nonvar(V)
    -> Solutions = V
    ;  Solutions = []
    ).

% ── load helpers ──────────────────────────────────────────────────────────

clear_workspace :-
    current_predicate(Name/Arity),
    functor(Probe, Name, Arity),
    predicate_property(Probe, dynamic),
    catch(retractall(Probe), _, true),
    fail.
clear_workspace.

declare_dynamic(Sig) :-
    term_string(SigTerm, Sig),
    ( SigTerm = Name/Arity
    -> ( catch(dynamic(Name/Arity), _, true) -> true ; true )
    ; true ).

load_clauses(Clauses) :-
    open_string(Clauses, Stream),
    load_stream(Stream),
    close(Stream).

load_stream(Stream) :-
    read(Stream, Term),
    ( Term == end_of_file
    -> true
    ; assertz(Term),
      load_stream(Stream)
    ).

% ── assert/retract helpers ────────────────────────────────────────────────

assert_clause(Term) :-
    ( Term = (Head :- _Body) -> true ; Head = Term ),
    functor(Head, Name, Arity),
    ( catch(dynamic(Name/Arity), _, true) -> true ; true ),
    assertz(Term).

count_retract(Term, Count) :-
    findall(1, retract(Term), Ones),
    length(Ones, Count).

% ── stats ─────────────────────────────────────────────────────────────────

stats(Facts, Rules) :-
    findall(T, dynamic_fact(T), FactTerms),
    length(FactTerms, Facts),
    findall(T, dynamic_rule(T), RuleTerms),
    length(RuleTerms, Rules).

dynamic_fact(Term) :-
    current_predicate(Name/Arity),
    functor(Probe, Name, Arity),
    predicate_property(Probe, dynamic),
    user_predicate(Name/Arity),
    clause(Probe, true),
    ground(Probe),
    Term = Probe.

dynamic_rule(Term) :-
    current_predicate(Name/Arity),
    functor(Probe, Name, Arity),
    predicate_property(Probe, dynamic),
    user_predicate(Name/Arity),
    clause(Probe, Body),
    Body \= true,
    Term = (Probe :- Body).

user_predicate(Name/Arity) :-
    \+ member(Name/Arity, [
        prove/3, is_arith_goal/1, decompose_rule_id/3,
        proof_to_json/2, euclid_rule_id/1
    ]).

% ── response helpers ──────────────────────────────────────────────────────

emit(Response) :-
    with_output_to(string(Json), json_write(current_output, Response, [width(0)])),
    write(Json), nl, flush_output.

emit_error(Error) :-
    ( catch(with_output_to(string(Msg), print_message(error, Error)), _,
            Msg = 'engine_error')
    -> true
    ; Msg = 'engine_error'
    ),
    emit(_{status:error, error:Msg}).

% Launch:  swipl -q -s prolog_engine.pl -g main -t halt
% (run main/0 as a -g goal, not as a load directive: directive mode would
%  break call_with_time_limit/2 inside the query handler).
