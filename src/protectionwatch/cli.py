"""Command-line entry point."""

from __future__ import annotations

import argparse
import logging
import sys
import threading
from collections.abc import Sequence

from protectionwatch import __version__
from protectionwatch.client import SyntheticClient
from protectionwatch.collector import Poller
from protectionwatch.config import Config
from protectionwatch.exposition import render_metrics
from protectionwatch.redact import configure_logging
from protectionwatch.service import Service, install_signal_handlers
from protectionwatch.tui import render_dashboard, run_dashboard


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="protectionwatch",
        description="Monitor a synthetic data-protection fleet and expose Prometheus metrics.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--seed", type=int, default=1, help="synthetic fleet seed")
    common.add_argument("--targets", type=int, default=12, help="synthetic fleet size")
    common.add_argument("--interval", type=float, default=15.0, help="poll interval, seconds")
    common.add_argument("--stale-after", type=float, default=60.0, help="staleness threshold")
    common.add_argument("--max-targets", type=int, default=200, help="target label cap")

    serve = sub.add_parser("serve", parents=[common], help="serve /metrics over HTTP")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=9877)

    sub.add_parser("once", parents=[common], help="poll once and print metrics")

    dash = sub.add_parser("dashboard", parents=[common], help="terminal dashboard")
    dash.add_argument("--once", action="store_true", help="render one frame and exit")
    dash.add_argument("--refresh", type=float, default=2.0, help="redraw period, seconds")
    return parser


def _config(args: argparse.Namespace) -> Config:
    return Config(
        host=getattr(args, "host", "127.0.0.1"),
        port=getattr(args, "port", 9877),
        poll_interval=args.interval,
        max_backoff=max(120.0, args.interval),
        stale_after=args.stale_after,
        retention=max(3600.0, args.stale_after),
        max_targets=args.max_targets,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(logging.DEBUG if args.verbose else logging.INFO)
    try:
        config = _config(args)
        client = SyntheticClient(seed=args.seed, targets=args.targets)
    except ValueError as exc:
        print(f"protectionwatch: error: {exc}", file=sys.stderr)
        return 2
    poller = Poller(client, config)

    if args.command == "once":
        poller.poll_once()
        sys.stdout.write(render_metrics(poller.view()))
        return 0

    if args.command == "dashboard":
        poller.poll_once()
        if args.once:
            sys.stdout.write(render_dashboard(poller.view()))
            return 0
        stop = threading.Event()
        install_signal_handlers(stop)
        worker = threading.Thread(target=poller.run, args=(stop,), name="poller")
        worker.start()
        try:
            run_dashboard(poller.view, stop, args.refresh)
        finally:
            stop.set()
            worker.join(timeout=10)
        return 0

    service = Service(poller, config)
    stop = threading.Event()
    install_signal_handlers(stop)
    service.start()
    try:
        service.wait(stop)
    finally:
        service.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
