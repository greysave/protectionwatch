from __future__ import annotations

import pytest

from protectionwatch.cli import main
from protectionwatch.client import SyntheticClient
from protectionwatch.collector import Poller
from protectionwatch.config import Config
from protectionwatch.tui import render_dashboard

from .helpers import FakeClock, ScriptedClient, snap


def test_synthetic_client_is_deterministic_and_seeded() -> None:
    a = SyntheticClient(seed=7, targets=5).fetch_fleet()
    b = SyntheticClient(seed=7, targets=5).fetch_fleet()
    c = SyntheticClient(seed=8, targets=5).fetch_fleet()
    assert a == b
    assert a != c
    assert len(a) == 5


def test_synthetic_client_rejects_negative() -> None:
    with pytest.raises(ValueError):
        SyntheticClient(targets=-1)


def test_dashboard_shows_stale_and_failures() -> None:
    clock = FakeClock()
    client = ScriptedClient([snap("a"), snap("b")], RuntimeError("x"))
    poller = Poller(client, Config(stale_after=10), clock)
    poller.poll_once()
    clock.now += 30
    poller.poll_once()
    text = render_dashboard(poller.view())
    assert "STALE" in text
    assert "1 consecutive poll failures" in text
    assert "\x1b[" not in text


def test_dashboard_limit_and_color() -> None:
    poller = Poller(ScriptedClient([snap(f"n{i}") for i in range(5)]), Config(), FakeClock())
    poller.poll_once()
    text = render_dashboard(poller.view(), color=True, limit=2)
    assert "3 more not shown" in text
    assert "\x1b[32m" in text


def test_cli_once_and_dashboard_once(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["once", "--targets", "2"]) == 0
    assert "protectionwatch_target_health" in capsys.readouterr().out
    assert main(["dashboard", "--once", "--targets", "2"]) == 0
    assert "node-001" in capsys.readouterr().out


def test_cli_rejects_bad_config(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["once", "--interval", "0"]) == 2
    assert "poll_interval" in capsys.readouterr().err
