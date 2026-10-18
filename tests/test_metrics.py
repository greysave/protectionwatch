from __future__ import annotations

import math

from protectionwatch.collector import Poller
from protectionwatch.config import Config
from protectionwatch.exposition import render_metrics
from protectionwatch.metrics import (
    MetricFamily,
    escape_label_value,
    format_value,
    render,
    sanitize_label,
)
from protectionwatch.model import Health, JobState

from .helpers import FakeClock, ScriptedClient, job, snap


def test_format_value() -> None:
    assert format_value(3.0) == "3"
    assert format_value(0.5) == "0.5"
    assert format_value(math.inf) == "+Inf"
    assert format_value(-math.inf) == "-Inf"
    assert format_value(math.nan) == "NaN"


def test_label_escaping() -> None:
    assert escape_label_value('a"b\\c\nd') == 'a\\"b\\\\c\\nd'


def test_render_family_layout_and_empty_omitted() -> None:
    fam = MetricFamily("x_total", "Help\nline", "counter")
    fam.add(2, kind="a")
    empty = MetricFamily("y", "unused", "gauge")
    text = render([fam, empty])
    assert text == '# HELP x_total Help\\nline\n# TYPE x_total counter\nx_total{kind="a"} 2\n'


def test_render_unlabelled_sample() -> None:
    fam = MetricFamily("z", "h", "gauge")
    fam.add(1.5)
    assert render([fam]).endswith("z 1.5\n")


def test_sanitize_label_bounds_and_charset() -> None:
    assert sanitize_label('we"ird host\n') == "we_ird_host"
    assert len(sanitize_label("a" * 500)) == 48
    assert sanitize_label("   ") == "unknown"


def _text(*steps: object, config: Config | None = None) -> str:
    poller = Poller(ScriptedClient(*steps), config or Config(), FakeClock())  # type: ignore[arg-type]
    poller.poll_once()
    return render_metrics(poller.view())


def test_fleet_exposition_contents() -> None:
    fleet = [
        snap(
            "node-001", health=Health.HEALTHY, jobs=(job(d=3.0), job("verify", JobState.FAILED, 50))
        ),
        snap("node-002", health=Health.CRITICAL, rpo=9000, objective=3600),
    ]
    text = _text(fleet)
    assert (
        'protectionwatch_target_health{target="node-001",group="alpha",state="healthy"} 1' in text
    )
    assert (
        'protectionwatch_target_health{target="node-002",group="alpha",state="critical"} 1' in text
    )
    assert 'protectionwatch_target_rpo_breached{target="node-002",group="alpha"} 1' in text
    assert 'protectionwatch_target_rpo_breached{target="node-001",group="alpha"} 0' in text
    assert 'protectionwatch_jobs{group="alpha",state="failed"} 1' in text
    assert 'protectionwatch_job_duration_seconds_bucket{job_class="snapshot",le="5.0"} 1' in text
    assert 'protectionwatch_job_duration_seconds_bucket{job_class="verify",le="+Inf"} 1' in text
    assert 'protectionwatch_job_duration_seconds_sum{job_class="verify"} 50' in text
    assert 'protectionwatch_polls_total{result="ok"} 1' in text
    assert text.endswith("\n")


def test_every_line_is_valid_exposition() -> None:
    import re

    sample = re.compile(r'^[a-zA-Z_:][a-zA-Z0-9_:]*(\{([a-z_]+="[^"\n]*",?)+\})? \S+$')
    text = _text([snap(jobs=(job(),))])
    for line in text.splitlines():
        assert line.startswith("#") or sample.match(line), line
