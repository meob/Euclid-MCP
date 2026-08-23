"""The ``--backend`` flag must not clobber an exported EUCLID_BACKEND.

``main()`` used to write the flag default ("auto") into the environment on
every run, silently discarding ``EUCLID_BACKEND=native`` exported by the
user — so the CLI always fell back to auto-detection. The flag is now only
applied when explicitly given: env var wins by default, explicit flag wins
over env.
"""

import os

import pytest

from euclid_mcp import cli as cli_mod


@pytest.mark.parametrize("exported", ["native", "prolog", "auto"])
def test_env_survives_run_without_flag(exported, monkeypatch):
    monkeypatch.setenv("EUCLID_BACKEND", exported)
    cli_mod.main(["check", "--json", "--knowledge", "a\n? a"])
    assert os.environ["EUCLID_BACKEND"] == exported


def test_explicit_flag_overrides_env(monkeypatch):
    monkeypatch.setenv("EUCLID_BACKEND", "native")
    cli_mod.main(["--backend", "prolog", "check", "--json", "--knowledge", "a\n? a"])
    assert os.environ["EUCLID_BACKEND"] == "prolog"
