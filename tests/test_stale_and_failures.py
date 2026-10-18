from __future__ import annotations

import logging

import pytest

from protectionwatch.collector import Poller
from protectionwatch.config import Config
from protectionwatch.exposition import render_metrics

from .helpers import FakeClock, ScriptedClient, job, snap


def test_target_becomes_stale_and_hides_values() -> None:
    clock = FakeClock()
    poller = Poller(ScriptedClient([snap(jobs=(job(),))]), Config(stale_after=60), clock)
    poller.poll_once()
    clock.now += 61
    text = render_metrics(poller.view())
    assert 'protectionwatch_target_stale{target="node-001",group="alpha"} 1' in text
    assert "protectionwatch_target_data_age_seconds" in text
    assert "protectionwatch_target_rpo_seconds" not in text
    assert "protectionwatch_target_health" not in text
    assert "protectionwatch_jobs" not in text


def test_fresh_just_inside_threshold() -> None:
    clock = FakeClock()
    poller = Poller(ScriptedClient([snap()]), Config(stale_after=60), clock)
    poller.poll_once()
    clock.now += 60
    assert not poller.view().targets[0].stale


def test_target_missing_from_later_poll_goes_stale() -> None:
    clock = FakeClock()
    client = ScriptedClient([snap("a"), snap("b")], [snap("a")])
    poller = Poller(client, Config(stale_after=60), clock)
    poller.poll_once()
    clock.now += 30
    poller.poll_once()
    clock.now += 40
    stale = {t.snapshot.target_id: t.stale for t in poller.view().targets}
    assert stale == {"a": False, "b": True}


def test_stale_targets_evicted_after_retention() -> None:
    clock = FakeClock()
    client = ScriptedClient([snap("a"), snap("b")], [snap("a")])
    poller = Poller(client, Config(stale_after=60, retention=300), clock)
    poller.poll_once()
    clock.now += 400
    poller.poll_once()
    assert [t.snapshot.target_id for t in poller.view().targets] == ["a"]


def test_poll_failure_keeps_data_counts_and_recovers(caplog: pytest.LogCaptureFixture) -> None:
    clock = FakeClock()
    client = ScriptedClient([snap()], RuntimeError("boom"), [snap()])
    poller = Poller(client, Config(), clock)
    assert poller.poll_once() is True
    with caplog.at_level(logging.WARNING, logger="protectionwatch.collector"):
        assert poller.poll_once() is False
    view = poller.view()
    assert (view.polls_ok, view.polls_failed, view.consecutive_failures) == (1, 1, 1)
    assert len(view.targets) == 1
    assert "RuntimeError" in caplog.text
    text = render_metrics(view)
    assert 'protectionwatch_polls_total{result="error"} 1' in text
    assert "protectionwatch_consecutive_poll_failures 1" in text
    client.steps = [[snap()]]
    assert poller.poll_once() is True
    assert poller.view().consecutive_failures == 0


def test_backoff_grows_and_is_capped() -> None:
    cfg = Config(poll_interval=10, max_backoff=60)
    poller = Poller(ScriptedClient(RuntimeError("x")), cfg, FakeClock())
    assert poller.next_delay() == 10
    poller.poll_once()
    assert poller.next_delay() == 20
    poller.poll_once()
    poller.poll_once()
    poller.poll_once()
    assert poller.next_delay() == 60


def test_no_success_yet_omits_last_success_metric() -> None:
    poller = Poller(ScriptedClient(RuntimeError("x")), Config(), FakeClock())
    poller.poll_once()
    assert "last_successful_poll" not in render_metrics(poller.view())


@pytest.mark.parametrize(
    "kwargs",
    [{"port": -1}, {"poll_interval": 0}, {"stale_after": 0}, {"max_targets": 0},
     {"poll_interval": 100, "max_backoff": 10}, {"stale_after": 100, "retention": 10}],
)  # fmt: skip
def test_config_validation(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        Config(**kwargs)  # type: ignore[arg-type]
