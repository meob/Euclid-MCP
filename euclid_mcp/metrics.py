"""Minimal Prometheus-compatible metrics (stdlib only, zero dependencies).

Implements the three metric families Euclid-MCP's observability needs —
``Counter``, ``Gauge`` and ``Histogram`` (fixed buckets) — plus ``render()``
in the Prometheus text exposition format (``Content-Type:
text/plain; version=0.0.4``). Every metric is thread-safe and label-keyed,
so the same family can track per-tool, per-command or per-path series.

Typical use (module-level singletons, imported by the instrumented code):

    from euclid_mcp.metrics import Counter, Gauge, Histogram, render

    tool_calls = Counter(
        "euclid_tool_calls_total", "Tool invocations by tool.", labels=("tool",)
    )
    tool_calls.inc(tool="reason")

    http_latency = Histogram(
        "euclid_http_request_duration_seconds",
        "HTTP request latency in seconds.",
        labels=("path",),
        buckets=(0.005, 0.01, 0.05, 0.1, 0.5, 1, 5),
    )
    http_latency.observe(0.042, path="/reason")

    print(render())
"""

from __future__ import annotations

import threading
from typing import Iterator, Sequence, TypeVar, cast

_DEFAULT_HISTOGRAM_BUCKETS: tuple[float, ...] = (
    0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10,
)


def _quote(value: str) -> str:
    """Escape a label value for the text exposition format."""
    return '"' + value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"') + '"'


def _escape_name(name: str) -> str:
    """Prometheus metric names allow ``[a-zA-Z_:][a-zA-Z0-9_:]*``."""
    return "".join(ch if ch.isalnum() or ch in ":_" else "_" for ch in name)


class _Metric:
    """Base class: a labelled family with a stable, sorted render order."""

    _type = "untyped"

    def __init__(self, name: str, help_text: str, labels: Sequence[str] = ()):
        if not name:
            raise ValueError("metric name is required")
        self.name = _escape_name(name)
        self.help_text = help_text
        self.labels = tuple(labels)
        self._lock = threading.Lock()

    def _check_labels(self, label_values: dict[str, object]) -> tuple[tuple[str, str], ...]:
        unexpected = set(label_values) - set(self.labels)
        if unexpected:
            raise ValueError(
                f"unexpected label(s) for {self.name}: {sorted(unexpected)}; "
                f"expected {sorted(self.labels)}"
            )
        missing = set(self.labels) - set(label_values)
        if missing:
            raise ValueError(
                f"missing label(s) for {self.name}: {sorted(missing)}"
            )
        return tuple(
            (label, str(label_values[label])) for label in sorted(self.labels)
        )

    def _family_headers(self) -> list[str]:
        return [
            f"# HELP {self.name} {self.help_text}",
            f"# TYPE {self.name} {self._type}",
        ]

    def render(self) -> Iterator[str]:
        raise NotImplementedError


class Counter(_Metric):
    """A monotonic counter, incremented via :meth:`inc`."""

    _type = "counter"

    def __init__(self, name: str, help_text: str, labels: Sequence[str] = ()):
        super().__init__(name, help_text, labels)
        self._values: dict[tuple[tuple[str, str], ...], float] = {}
        register(self)

    def inc(self, amount: float = 1, **label_values: object) -> None:
        if amount < 0:
            raise ValueError("counter increments must be non-negative")
        key = self._check_labels(label_values)
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def value(self, **label_values: object) -> float:
        key = self._check_labels(label_values)
        with self._lock:
            return self._values.get(key, 0.0)

    def render(self) -> Iterator[str]:
        with self._lock:
            samples = sorted(self._values.items())
        yield from self._family_headers()
        for key, value in samples:
            labels = ",".join(f'{k}={_quote(v)}' for k, v in key)
            if labels:
                labels = "{" + labels + "}"
            yield f"{self.name}{labels} {_format_number(value)}"


class Gauge(_Metric):
    """A value that can go up and down, set via :meth:`set`."""

    _type = "gauge"

    def __init__(self, name: str, help_text: str, labels: Sequence[str] = ()):
        super().__init__(name, help_text, labels)
        self._values: dict[tuple[tuple[str, str], ...], float] = {}
        register(self)

    def set(self, value: float, **label_values: object) -> None:
        key = self._check_labels(label_values)
        with self._lock:
            self._values[key] = float(value)

    def inc(self, amount: float = 1, **label_values: object) -> None:
        key = self._check_labels(label_values)
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def value(self, **label_values: object) -> float:
        key = self._check_labels(label_values)
        with self._lock:
            return self._values.get(key, 0.0)

    def render(self) -> Iterator[str]:
        with self._lock:
            samples = sorted(self._values.items())
        yield from self._family_headers()
        for key, value in samples:
            labels = ",".join(f'{k}={_quote(v)}' for k, v in key)
            if labels:
                labels = "{" + labels + "}"
            yield f"{self.name}{labels} {_format_number(value)}"


class Histogram(_Metric):
    """An observation distribution with fixed buckets and sum/count."""

    _type = "histogram"

    def __init__(
        self,
        name: str,
        help_text: str,
        labels: Sequence[str] = (),
        buckets: Sequence[float] = _DEFAULT_HISTOGRAM_BUCKETS,
    ):
        super().__init__(name, help_text, labels)
        if not buckets or any(b <= 0 for b in buckets) or sorted(buckets) != list(buckets):
            raise ValueError("histogram buckets must be positive and ascending")
        self.buckets = tuple(buckets)
        # key -> (buckets list aligned to self.buckets, sum, count)
        self._data: dict[
            tuple[tuple[str, str], ...], tuple[list[float], float, float]
        ] = {}
        register(self)

    def observe(self, value: float, **label_values: object) -> None:
        key = self._check_labels(label_values)
        with self._lock:
            counts, total, count = self._data.setdefault(
                key, ([0.0] * len(self.buckets), 0.0, 0.0)
            )
            total += value
            count += 1.0
            for index, upper in enumerate(self.buckets):
                if value <= upper:
                    counts[index] += 1.0
                    break
            self._data[key] = (counts, total, count)

    def _cumulative(self, counts: list[float]) -> list[float]:
        cumulative: list[float] = []
        running = 0.0
        for c in counts:
            running += c
            cumulative.append(running)
        return cumulative

    def render(self) -> Iterator[str]:
        with self._lock:
            samples = sorted(self._data.items())
        yield from self._family_headers()
        for key, (counts, total, count) in samples:
            base = self.name
            if key:
                user_labels = ",".join(f'{k}={_quote(v)}' for k, v in key)
            else:
                user_labels = ""
            cumulative = self._cumulative(counts)
            for upper, cum in zip(self.buckets, cumulative):
                labels = _join_labels(user_labels, f'le={_quote(str(upper))}')
                yield f"{base}_bucket{labels} {_format_number(cum)}"
            labels = _join_labels(user_labels, 'le="+Inf"')
            yield f"{base}_bucket{labels} {_format_number(count)}"
            yield f"{base}_sum{_labels(user_labels)} {_format_number(total)}"
            yield f"{base}_count{_labels(user_labels)} {_format_number(count)}"


def _join_labels(user_labels: str, extra: str) -> str:
    return "{" + (user_labels + "," if user_labels else "") + extra + "}"


def _labels(user_labels: str) -> str:
    return "{" + user_labels + "}" if user_labels else ""


def _format_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return repr(value)


# ── registry ───────────────────────────────────────────────────────────────

_registry: list[_Metric] = []
_registry_lock = threading.Lock()

_MetricT = TypeVar("_MetricT", bound=_Metric)


def register(metric: _MetricT) -> _MetricT:
    """Register a metric so ``render()`` includes it (idempotent by name)."""
    with _registry_lock:
        for existing in _registry:
            if existing.name == metric.name:
                return cast(_MetricT, existing)
        _registry.append(metric)
    return metric


def render() -> str:
    """Render every registered metric in the Prometheus text exposition format."""
    with _registry_lock:
        families = list(_registry)
    lines: list[str] = []
    for family in sorted(families, key=lambda m: m.name):
        lines.extend(family.render())
    return "\n".join(lines) + "\n"


def _reset_for_tests() -> None:
    """Drop all registered metrics (test-only hook)."""
    with _registry_lock:
        _registry.clear()
