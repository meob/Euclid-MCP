import os
import sys

__version__ = "0.1.5"
__all__ = ["main"]


def _apply_kb_path_arg() -> None:
    """Funnel a `--kb-path` CLI flag into EUCLID_KB_PATH.

    Runs before the server module is imported because KB preload happens at
    import time (the MCPServer instructions are computed then). The package is
    imported before `__main__` executes, so this must live in `__init__`.
    """
    if "--kb-path" in sys.argv:
        idx = sys.argv.index("--kb-path")
        if idx + 1 < len(sys.argv):
            os.environ["EUCLID_KB_PATH"] = sys.argv[idx + 1]


_apply_kb_path_arg()

from .server import main  # noqa: E402
