"""Unit tests for the stdlib-only Prometheus metrics module (metrics.py)."""

from itertools import count

import pytest

from euclid_mcp.metrics import (
    Counter,
    Gauge,
    Histogram,
    register,
    render,
)

_UNIQUE = count()


def _name(base: str) -> str:
    """Unique metric name per test so runs never share state."""
    return f"tst_{next(_UNIQUE)}_{base}"


def _lines(text: str) -> list[str]:
    return text.splitlines()


class TestCounter:
    def test_inc_and_value(self):
        c = Counter(_name("c"), "test counter")
        assert c.value() == 0
        c.inc()
        c.inc(2)
        assert c.value() == 3

    def test_labelled_counter(self):
        c = Counter(_name("c"), "test counter", labels=("tool",))
        c.inc(tool="reason")
        c.inc(4, tool="diagnose")
        assert c.value(tool="reason") == 1
        assert c.value(tool="diagnose") == 4
        assert c.value(tool="explain") == 0

    def test_negative_inc_rejected(self):
        c = Counter(_name("c"), "test counter")
        with pytest.raises(ValueError):
            c.inc(-1)

    def test_missing_label_rejected(self):
        c = Counter(_name("c"), "test counter", labels=("tool",))
        with pytest.raises(ValueError):
            c.inc()

    def test_unexpected_label_rejected(self):
        c = Counter(_name("c"), "test counter", labels=("tool",))
        with pytest.raises(ValueError):
            c.inc(tool="x", nope="y")

    def test_render_help_and_type(self):
        c = Counter(_name("c"), "test counter")
        c.inc()
        text = render()
        assert f"# HELP {c.name} test counter" in text
        assert f"# TYPE {c.name} counter" in text
        assert f"{c.name} 1" in text

    def test_render_sorted_labels_and_escaping(self):
        name = _name("c")
        c = Counter(name, "test counter", labels=("a", "b"))
        c.inc(b="x", a="y")
        c.inc(b='qu"ote', a="line\nbreak")
        text = render()
        assert f'{name}{{a="y",b="x"}} 1' in text
        assert f'{name}{{a="line\\nbreak",b="qu\\"ote"}} 1' in text


class TestGauge:
    def test_set_inc_value(self):
        g = Gauge(_name("g"), "test gauge")
        g.set(5)
        assert g.value() == 5
        g.inc(3)
        assert g.value() == 8
        g.set(2)
        assert g.value() == 2

    def test_labelled_gauge(self):
        g = Gauge(_name("g"), "test gauge", labels=("kind",))
        g.set(7, kind="facts")
        assert g.value(kind="facts") == 7
        assert g.value(kind="rules") == 0
        assert f'{g.name}{{kind="facts"}} 7' in render()


class TestHistogram:
    def test_buckets_sum_count(self):
        name = _name("h")
        h = Histogram(name, "test histogram", buckets=(1.0, 2.0))
        h.observe(0.5)
        h.observe(1.5)
        h.observe(3.0)
        text = render()
        assert f'{name}_bucket{{le="1.0"}} 1' in text
        assert f'{name}_bucket{{le="2.0"}} 2' in text
        assert f'{name}_bucket{{le="+Inf"}} 3' in text
        assert f"{name}_sum 5" in text
        assert f"{name}_count 3" in text

    def test_labelled_histogram(self):
        name = _name("h")
        h = Histogram(name, "test histogram", labels=("path",), buckets=(1.0,))
        h.observe(0.1, path="/reason")
        text = render()
        assert f'{name}_bucket{{path="/reason",le="1.0"}} 1' in text
        assert f'{name}_sum{{path="/reason"}} 0.1' in text

    def test_invalid_buckets_rejected(self):
        for buckets in ((), (0.0,), (2.0, 1.0)):
            with pytest.raises(ValueError):
                Histogram(_name("h"), "test histogram", buckets=buckets)

    def test_default_buckets_positive_ascending(self):
        h = Histogram(_name("h"), "test histogram")
        assert list(h.buckets) == sorted(h.buckets)
        assert all(b > 0 for b in h.buckets)


class TestRegister:
    def test_register_idempotent(self):
        name = _name("c")
        first = register(Counter(name, "test counter"))
        second = register(Counter(name, "test counter"))
        assert first is second
        first.inc()
        assert second.value() == 1

    def test_render_includes_registered_families(self):
        c = register(Counter(_name("c"), "test counter"))
        c.inc()
        text = render()
        assert f"# TYPE {c.name} counter" in text
        assert f"{c.name} 1" in text


def test_format_integer_without_trailing_dot():
    c = Counter(_name("c"), "test counter")
    c.inc()
    c.inc()
    assert f"{c.name} 2" in render()
