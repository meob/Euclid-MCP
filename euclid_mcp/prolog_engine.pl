% prolog_engine.pl — persistent SWI-Prolog inference engine.
%
% JSON-lines protocol on stdin/stdout (one request per line, one response
% line per request). Commands:
%   {"command":"ping"}                              -> {"status":"ok"}
%   {"command":"load","decls":["p/1",...],
%    "clauses":"p(a).\nq(b,c).","kb_hash":"<sha256>"}
%                                                   -> {"status":"ok","facts":N,"rules":M,"skipped":B}
%       Clears every dynamic predicate from the previous workspace, declares
%       the given signatures dynamic and asserts the clauses. Clauses may
%       include the meta-interpreter (prove/3) and proof_to_json/2 rules,
%       which are provided by the Python side on every load.
%       When kb_hash matches the fingerprint of the currently-loaded
%       workspace the load is skipped (skipped:1) and the stored stats are
%       returned. assert/retract invalidate the fingerprint so the next load
%       rebuilds the workspace.
%   {"command":"query","snippet":"<prolog>","timeout":30}
%       The snippet must write a JSON array of result dicts to
%       current_output (one compact object per solution, commas between),
%       e.g. via forall/2 + json_write/3. The engine captures the array and
%       replies with {"status":"ok","solutions":"<json array string>"}.
%       This streams instead of collecting all solutions in one term, so
%       large result sets stay fast and low-memory.
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
    ( get_dict(kb_hash, Request, Hash) -> true ; Hash = none ),
    catch(
        ( ( Hash \= none, current_kb_hash(Hash)
          -> current_kb_stats(Facts, Rules),
             emit(_{status:ok, facts:Facts, rules:Rules, skipped:1})
          ; clear_workspace,
            maplist(declare_dynamic, Decls),
            load_clauses(Clauses),
            stats(Facts, Rules),
            record_workspace(Hash, Facts, Rules),
            emit(_{status:ok, facts:Facts, rules:Rules, skipped:0})
          ) ),
        Error,
        emit_error(Error)
    ).

command_handler(query, Request) :-
    get_dict(snippet, Request, SnippetAtom),
    ( get_dict(timeout, Request, Timeout) -> true ; Timeout = 30 ),
    catch(
        ( atom_string(SnippetAtom, SnippetStr),
          read_term_from_atom(SnippetStr, Snippet, []),
          call_with_time_limit(Timeout,
              with_output_to(string(Json), call(Snippet))),
          emit(_{status:ok, solutions:Json}) ),
        time_limit_exceeded,
        emit(_{status:timeout})
    ).

command_handler(assert, Request) :-
    get_dict(clause, Request, ClauseAtom),
    catch(
        ( read_term_from_atom(ClauseAtom, Clause, []),
          assert_clause(Clause),
          retractall(current_kb_hash(_)),
          emit(_{status:ok}) ),
        Error,
        emit_error(Error)
    ).

command_handler(retract, Request) :-
    get_dict(clause, Request, ClauseAtom),
    catch(
        ( read_term_from_atom(ClauseAtom, Clause, []),
          count_retract(Clause, Count),
          retractall(current_kb_hash(_)),
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

% Streaming JSON-array separator for query snippets. The snippet asserts
% euclid_array_first/0 before writing '[', then calls array_separator/0
% before every element: the first call writes nothing, subsequent calls
% write ','. Clear-on-load keeps the flag consistent after timeouts.
:- dynamic euclid_array_first/0.

% Registry of predicates that belong to the loaded workspace (declared dynamic
% via declare_dynamic/1, plus the engine-internal euclid_array_first flag).
% clear_workspace/0 retracts ONLY these. A broad sweep of every dynamic
% predicate is unsafe: on SWI-Prolog 9.x several internal bookkeeping
% predicates (e.g. $search_path_file_cache/3, prolog_file_type/2,
% $autoload_nesting/1) are dynamic too, and retracting them corrupts the
% autoloader — the next library autoload (e.g. maplist/2) dies with
% domain_error(file_type, prolog).
:- dynamic workspace_predicate/1.
:- assertz(workspace_predicate(euclid_array_first/0)).

% Fingerprint of the currently-loaded workspace. record_workspace/3 stores it
% on load; assert/retract retract it so the next load rebuilds the workspace.
% current_kb_stats/2 keeps the facts/rules counts so a skipped load can reply
% without recomputing them.
:- dynamic current_kb_hash/1, current_kb_stats/2.

array_separator :-
    ( euclid_array_first
    -> retractall(euclid_array_first)
    ;  write(',')
    ).

% ── load helpers ──────────────────────────────────────────────────────────

clear_workspace :-
    ( retract(workspace_predicate(Name/Arity))
    -> functor(Probe, Name, Arity),
       catch(retractall(Probe), _, true),
       clear_workspace
    ;  true ),
    ( workspace_predicate(euclid_array_first/0)
    -> true
    ;  assertz(workspace_predicate(euclid_array_first/0))
    ).

declare_dynamic(Sig) :-
    term_string(SigTerm, Sig),
    ( SigTerm = Name/Arity
    -> ( catch(dynamic(Name/Arity), _, true) -> true ; true ),
       ( workspace_predicate(Name/Arity)
       -> true
       ;  assertz(workspace_predicate(Name/Arity))
       )
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

% Remember the fingerprint (and stats) of the workspace just loaded so an
% identical load can skip the rebuild. Hash = none means the caller did not
% opt into the fingerprint check, so nothing is stored.
record_workspace(none, _Facts, _Rules) :-
    retractall(current_kb_hash(_)),
    retractall(current_kb_stats(_,_)).
record_workspace(Hash, Facts, Rules) :-
    retractall(current_kb_hash(_)),
    retractall(current_kb_stats(_,_)),
    assertz(current_kb_hash(Hash)),
    assertz(current_kb_stats(Facts, Rules)).

% ── assert/retract helpers ────────────────────────────────────────────────

assert_clause(Term) :-
    ( Term = (Head :- _Body) -> true ; Head = Term ),
    functor(Head, Name, Arity),
    ( catch(dynamic(Name/Arity), _, true) -> true ; true ),
    ( workspace_predicate(Name/Arity) -> true ; assertz(workspace_predicate(Name/Arity)) ),
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

% Stats count the loaded workspace only: enumerate the registered
% workspace predicates (never a broad sweep of every dynamic predicate —
% SWI-Prolog 9.x keeps internal bookkeeping dynamic with clauses), then
% exclude the engine-internal meta-interpreter predicates.
dynamic_fact(Term) :-
    workspace_predicate(Name/Arity),
    user_predicate(Name/Arity),
    functor(Probe, Name, Arity),
    clause(Probe, true),
    ground(Probe),
    Term = Probe.

dynamic_rule(Term) :-
    workspace_predicate(Name/Arity),
    user_predicate(Name/Arity),
    functor(Probe, Name, Arity),
    clause(Probe, Body),
    Body \= true,
    Term = (Probe :- Body).

% Engine-internal predicates (meta-interpreter, proof serializer, array
% streaming flag, workspace fingerprint): excluded from the user stats.
user_predicate(Name/Arity) :-
    \+ member(Name/Arity, [
        prove/3, is_arith_goal/1, decompose_rule_id/3,
        proof_to_json/2, euclid_rule_id/1,
        euclid_array_first/0, current_kb_hash/1, current_kb_stats/2
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
