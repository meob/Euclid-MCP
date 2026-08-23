"""Package identity: version consistency across the tree."""

import re
from pathlib import Path

import euclid_mcp

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_package_version_matches_pyproject():
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    assert match, "pyproject.toml has no static version"
    assert euclid_mcp.__version__ == match.group(1)
