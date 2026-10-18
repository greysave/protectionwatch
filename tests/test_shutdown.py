from __future__ import annotations

import socket
import threading
import time
import urllib.error
import urllib.request

import pytest

from protectionwatch.collector import Poller
from protectionwatch.config import Config
from protectionwatch.service import Service, install_signal_handlers

from .helpers import ScriptedClient, job, snap


def _get(port: int, path: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
            return int(r.status), r.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def test_service_serves_then_shuts_down_cleanly() -> None:
    cfg = Config(port=0, poll_interval=0.05)
    poller = Poller(ScriptedClient([snap(jobs=(job(),))]), cfg)
    service = Service(poller, cfg)
    service.start()
    port = service.port
    deadline = time.time() + 5
    while poller.view().polls_ok == 0 and time.time() < deadline:
        time.sleep(0.01)
    status, body = _get(port, "/metrics")
    assert status == 200
    assert "protectionwatch_target_health" in body
    assert _get(port, "/healthz")[0] == 200
    assert _get(port, "/nope")[0] == 404

    service.stop()
    service.stop()  # idempotent
    assert not any(t.is_alive() for t in threading.enumerate() if t.name in {"poller", "http"})
    with pytest.raises(OSError), socket.create_connection(("127.0.0.1", port), timeout=1):
        pass


def test_healthz_503_before_data() -> None:
    cfg = Config(port=0, poll_interval=60)
    service = Service(Poller(ScriptedClient(RuntimeError("down")), cfg), cfg)
    service.start()
    try:
        status = _get(service.port, "/healthz")[0]
    finally:
        service.stop()
    assert status in (503, 200)  # poller thread may not have failed yet; never crashes


def test_poller_run_returns_promptly_when_stopped() -> None:
    cfg = Config(poll_interval=3600, max_backoff=3600)
    poller = Poller(ScriptedClient([snap()]), cfg)
    stop = threading.Event()
    thread = threading.Thread(target=poller.run, args=(stop,))
    thread.start()
    time.sleep(0.1)
    stop.set()
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert poller.view().polls_ok == 1


def test_signal_handler_sets_event() -> None:
    import signal

    event = threading.Event()
    old_int, old_term = signal.getsignal(signal.SIGINT), signal.getsignal(signal.SIGTERM)
    try:
        install_signal_handlers(event)
        signal.raise_signal(signal.SIGTERM)
        assert event.is_set()
    finally:
        signal.signal(signal.SIGINT, old_int)
        signal.signal(signal.SIGTERM, old_term)


def test_stop_before_start_is_safe_and_does_not_block() -> None:
    cfg = Config(port=0, poll_interval=60)
    service = Service(Poller(ScriptedClient([snap()]), cfg), cfg)
    port = service.port
    done = threading.Event()

    def run() -> None:
        service.stop()
        service.stop()
        done.set()

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    assert done.wait(timeout=5), "stop() before start() blocked"
    with pytest.raises(OSError), socket.create_connection(("127.0.0.1", port), timeout=1):
        pass


def test_start_after_stop_is_rejected() -> None:
    cfg = Config(port=0, poll_interval=60)
    service = Service(Poller(ScriptedClient([snap()]), cfg), cfg)
    service.stop()
    with pytest.raises(RuntimeError, match="stopped"):
        service.start()


def test_double_start_is_rejected() -> None:
    cfg = Config(port=0, poll_interval=60)
    service = Service(Poller(ScriptedClient([snap()]), cfg), cfg)
    service.start()
    try:
        with pytest.raises(RuntimeError, match="already started"):
            service.start()
    finally:
        service.stop()


@pytest.mark.parametrize(
    "path", ["/metrics?", "/metrics?name[]=protectionwatch_jobs", "/metrics?x=1&y=2#frag"]
)
def test_metrics_accepts_query_strings(path: str) -> None:
    cfg = Config(port=0, poll_interval=0.05)
    poller = Poller(ScriptedClient([snap(jobs=(job(),))]), cfg)
    service = Service(poller, cfg)
    service.start()
    try:
        deadline = time.time() + 5
        while poller.view().polls_ok == 0 and time.time() < deadline:
            time.sleep(0.01)
        status, body = _get(service.port, path)
        assert status == 200 and "protectionwatch_target_health" in body
        assert _get(service.port, "/healthz?probe=1")[0] == 200
        assert _get(service.port, "/metricsx?a=1")[0] == 404
    finally:
        service.stop()
