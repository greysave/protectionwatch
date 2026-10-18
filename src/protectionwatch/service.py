"""HTTP exposition endpoint plus background poller with graceful shutdown."""

from __future__ import annotations

import logging
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import FrameType
from urllib.parse import urlsplit

from protectionwatch.collector import Poller
from protectionwatch.config import Config
from protectionwatch.exposition import render_metrics

log = logging.getLogger("protectionwatch.service")

CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


def _make_handler(poller: Poller, config: Config) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = urlsplit(self.path).path  # ignore ?query and #fragment
            if path == "/metrics":
                self._send(200, render_metrics(poller.view()), CONTENT_TYPE)
            elif path == "/healthz":
                view = poller.view()
                fresh = any(not t.stale for t in view.targets)
                ok = view.last_success_ts is not None and fresh
                self._send(200 if ok else 503, "ok\n" if ok else "no fresh data\n", "text/plain")
            else:
                self._send(404, "not found\n", "text/plain")

        def _send(self, code: int, body: str, content_type: str) -> None:
            data = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: object) -> None:
            log.debug("http: " + format, *args)

    return Handler


class Service:
    """Runs the poller and HTTP server on background threads.

    ``stop`` is idempotent and safe to call before ``start`` (it then only releases the
    listening socket); a stopped service cannot be started again.
    """

    def __init__(self, poller: Poller, config: Config) -> None:
        self._poller = poller
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._server = ThreadingHTTPServer(
            (config.host, config.port), _make_handler(poller, config)
        )
        self._server.daemon_threads = True
        self._threads = [
            threading.Thread(target=poller.run, args=(self._stop,), name="poller"),
            threading.Thread(target=self._server.serve_forever, name="http"),
        ]
        self._started = False
        self._stopped = False

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    def start(self) -> None:
        with self._lock:
            if self._stopped:
                raise RuntimeError("service was stopped and cannot be restarted")
            if self._started:
                raise RuntimeError("service already started")
            self._started = True
            for thread in self._threads:
                thread.start()
        log.info("serving metrics on port %d", self.port)

    def stop(self) -> None:
        with self._lock:
            if self._stopped:
                return
            self._stopped = True
            started = self._started
        self._stop.set()
        if started:
            # shutdown() blocks until serve_forever() exits, so only call it once that loop
            # was actually launched.
            self._server.shutdown()
        self._server.server_close()
        if started:
            for thread in self._threads:
                thread.join(timeout=10)
        log.info("stopped")

    def wait(self, event: threading.Event) -> None:
        """Block until ``event`` is set (e.g. by a signal handler)."""
        event.wait()


def install_signal_handlers(event: threading.Event) -> None:
    """Set ``event`` on SIGINT/SIGTERM so the main thread can shut down cleanly."""

    def handler(signum: int, _frame: FrameType | None) -> None:
        log.info("received signal %d, shutting down", signum)
        event.set()

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)
