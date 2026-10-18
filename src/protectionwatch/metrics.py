"""Minimal Prometheus text exposition (format 0.0.4) and label hygiene."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

_INVALID = re.compile(r"[^A-Za-z0-9_.-]")
MAX_LABEL_LENGTH = 48
OVERFLOW = "other"


def sanitize_label(value: str) -> str:
    """Reduce an arbitrary string to a short, safe label value."""
    cleaned = _INVALID.sub("_", value.strip())[:MAX_LABEL_LENGTH]
    return cleaned or "unknown"


class LabelLimiter:
    """Caps how many distinct values a label may take.

    The first ``max_values`` distinct (sanitized) values are admitted for the
    lifetime of the limiter; everything after maps to ``OVERFLOW``.
    """

    def __init__(self, max_values: int) -> None:
        if max_values < 1:
            raise ValueError("max_values must be >= 1")
        self._max = max_values
        self._seen: set[str] = set()
        self.overflowed = 0

    def map(self, raw: str) -> str:
        value = sanitize_label(raw)
        if value in self._seen:
            return value
        if len(self._seen) < self._max:
            self._seen.add(value)
            return value
        self.overflowed += 1
        return OVERFLOW


def escape_label_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def escape_help(text: str) -> str:
    return text.replace("\\", "\\\\").replace("\n", "\\n")


def format_value(value: float) -> str:
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "+Inf" if value > 0 else "-Inf"
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return repr(float(value))


@dataclass(frozen=True)
class Sample:
    name: str
    labels: Mapping[str, str]
    value: float


@dataclass
class MetricFamily:
    name: str
    help: str
    type: str
    samples: list[Sample] = field(default_factory=list)

    def add(self, value: float, *, name: str | None = None, **labels: str) -> None:
        self.samples.append(Sample(name or self.name, labels, value))


def _render_sample(sample: Sample) -> str:
    if sample.labels:
        body = ",".join(f'{k}="{escape_label_value(v)}"' for k, v in sample.labels.items())
        return f"{sample.name}{{{body}}} {format_value(sample.value)}"
    return f"{sample.name} {format_value(sample.value)}"


def render(families: Iterable[MetricFamily]) -> str:
    """Render families to exposition text; empty families are omitted."""
    lines: list[str] = []
    for family in families:
        if not family.samples:
            continue
        lines.append(f"# HELP {family.name} {escape_help(family.help)}")
        lines.append(f"# TYPE {family.name} {family.type}")
        lines.extend(_render_sample(s) for s in family.samples)
    return "\n".join(lines) + "\n" if lines else ""
