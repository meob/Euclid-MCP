"""Input sanitizer for Euclid-IR.

Rejects Prolog directives and dangerous built-ins that could lead to
arbitrary code execution or system compromise.
"""

import re

# Patterns that indicate Prolog directives or dangerous built-ins.
# Applied to the raw text BEFORE translation to Prolog.
_DANGEROUS_PATTERNS = re.compile(
    r"""
    ^\s*:-                         # Prolog directive (e.g. :- shell('...'))
    | :-\s                         # Prolog rule syntax (e.g. evil(X) :- shell(X))
    | \bshell\s*\(                 # shell/1 - OS command execution
    | \bhalt\s*\(                  # halt/0,1 - process termination
    | \bhalt\s*[.?!]               # bare halt (query: ? halt.)
    | \bconsult\s*\(               # consult/1 - load Prolog file
    | \bassert\s*\(                # assert/1,2 - dynamic rule injection
    | \bretract\s*\(               # retract/1,2 - dynamic rule removal
    | \bretractall\s*\(            # retractall/1 - bulk rule removal
    | \bprocess_create\s*\(        # process_create/2 - spawn OS process
    | \bopen_process\s*\(          # open_process/2 - pipe to OS process
    | \bset_prolog_flag\s*\(       # modify Prolog runtime flags
    | \bload_files\s*\(            # load_files/1,2 - load Prolog source
    | \buse_module\s*\(            # use_module/1,2 (only dangerous in user input)
    """,
    re.IGNORECASE | re.VERBOSE,
)


def sanitize(text: str) -> None:
    """Validate Euclid-IR input for dangerous Prolog patterns.

    Raises ValueError if the input contains Prolog directives or
    dangerous built-ins that could lead to command injection.

    This function is intentionally permissive for valid Euclid-IR
    while being strict against Prolog-specific attack vectors.
    """
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        # Skip comments
        if stripped.startswith("#") or stripped.startswith("//"):
            continue
        # Skip @version directive
        if stripped.startswith("@version"):
            continue
        # Check for dangerous patterns
        if _DANGEROUS_PATTERNS.search(stripped):
            raise ValueError(
                f"Rejected dangerous pattern in input: {stripped!r}. "
                "Euclid-IR does not support Prolog directives (:- ...) "
                "or built-in predicates like shell(), halt(), consult()."
            )
