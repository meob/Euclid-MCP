"""Tests for the named-KB registry (euclid_mcp/kb_store.py)."""

from euclid_mcp.kb_store import KB_ID_PATTERN, KBRecord, KbStore, is_valid_kb_id


def _record(kb_id: str, **kw) -> KBRecord:
    defaults = dict(source="p(a)\n? p(a)", content_hash=f"hash-{kb_id}")
    defaults.update(kw)
    return KBRecord(kb_id=kb_id, **defaults)


class TestKbIdPattern:
    def test_accepts_simple(self):
        assert is_valid_kb_id("rbac")
        assert is_valid_kb_id("prod-2026")
        assert is_valid_kb_id("a_b_c")
        assert is_valid_kb_id("0")
        assert is_valid_kb_id("x" * 64)

    def test_rejects_invalid(self):
        for kb_id in (
            "",
            "Admin",
            "UPPER",
            "with space",
            "../admin",
            "admin/",
            "admin/evil",
            "a.b",
            "x" * 65,
            "é",
        ):
            assert not is_valid_kb_id(kb_id), kb_id
            assert KB_ID_PATTERN.match(kb_id) is None


class TestKbStore:
    def test_register_get(self):
        store = KbStore()
        rec = _record("rbac")
        assert store.register(rec) is True
        assert store.get("rbac") is rec

    def test_get_unknown_returns_none(self):
        store = KbStore()
        assert store.get("missing") is None

    def test_unregister(self):
        store = KbStore()
        store.register(_record("rbac"))
        assert store.unregister("rbac") is True
        assert store.unregister("rbac") is False
        assert store.get("rbac") is None

    def test_overwrite_updates_record(self):
        store = KbStore()
        store.register(_record("rbac", source="v1"))
        assert store.register(_record("rbac", source="v2")) is True
        assert store.get("rbac").source == "v2"

    def test_max_kbs_bound(self):
        store = KbStore(max_kbs=2)
        assert store.register(_record("a")) is True
        assert store.register(_record("b")) is True
        assert store.register(_record("c")) is False
        # overwriting an existing id still works at capacity
        assert store.register(_record("a", source="new")) is True

    def test_list_sorted_and_isolated(self):
        store = KbStore()
        store.register(_record("b"))
        store.register(_record("a"))
        assert [r.kb_id for r in store.list()] == ["a", "b"]
        # the returned list is a snapshot
        store.register(_record("c"))
        assert [r.kb_id for r in store.list()] == ["a", "b", "c"]

    def test_metadata_excludes_source(self):
        rec = _record("rbac", version="2.0", facts=1, rules=2, predicates=3)
        meta = rec.metadata()
        assert meta == {
            "kb_id": "rbac",
            "content_hash": "hash-rbac",
            "version": "2.0",
            "facts": 1,
            "rules": 2,
            "predicates": 3,
        }
        assert "source" not in meta
