"""In-memory registry of named knowledge bases (C3).

``register_kb`` stores a validated KB under a caller-chosen ``kb_id``; the
reasoning tools then accept ``kb_id`` (plus an optional ``delta_knowledge``
overlay) instead of resending the whole KB text on every call.

The registry is a dumb in-memory ``dict`` guarded by a lock — **no KB
validation happens here** (that would create a circular import with
``server.py``). The ``register_kb`` tool validates first, then stores the
``KBRecord``.
"""

import re
from dataclasses import dataclass
from threading import RLock

KB_ID_PATTERN = re.compile(r"^[a-z0-9_-]{1,64}$")


def is_valid_kb_id(kb_id: str) -> bool:
    """True when ``kb_id`` matches the allowlist (1-64 [a-z0-9_-])."""
    return KB_ID_PATTERN.match(kb_id) is not None


@dataclass
class KBRecord:
    """A named knowledge base, with identity and structure counts.

    ``source`` is the exact KB text that was validated and registered;
    ``content_hash`` is its sha256 (see ``engine.kb_fingerprint``).
    """

    kb_id: str
    source: str
    content_hash: str
    version: str | None = None
    facts: int = 0
    rules: int = 0
    predicates: int = 0

    def metadata(self) -> dict:
        """The record without the (potentially large) KB source text."""
        return {
            "kb_id": self.kb_id,
            "content_hash": self.content_hash,
            "version": self.version,
            "facts": self.facts,
            "rules": self.rules,
            "predicates": self.predicates,
        }


class KbStore:
    """Per-instance registry of named KBs, bounded by ``max_kbs``.

    All operations are lock-protected and return plain values (no raising):
    callers decide how to surface failures.
    """

    def __init__(self, max_kbs: int = 32) -> None:
        self.max_kbs = max_kbs
        self._kbs: dict[str, KBRecord] = {}
        self._lock = RLock()

    def register(self, record: KBRecord) -> bool:
        """Store ``record`` (overwrite allowed). False when at capacity."""
        with self._lock:
            if record.kb_id in self._kbs:
                self._kbs[record.kb_id] = record
                return True
            if len(self._kbs) >= self.max_kbs:
                return False
            self._kbs[record.kb_id] = record
            return True

    def get(self, kb_id: str) -> KBRecord | None:
        with self._lock:
            return self._kbs.get(kb_id)

    def unregister(self, kb_id: str) -> bool:
        """Remove ``kb_id``; True when it was present."""
        with self._lock:
            return self._kbs.pop(kb_id, None) is not None

    def list(self) -> list[KBRecord]:
        with self._lock:
            return sorted(self._kbs.values(), key=lambda r: r.kb_id)
