"""Optional terminal dashboard using only ANSI escapes (no extra dependencies)."""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from typing import TextIO

from protectionwatch.collector import FleetView
from protectionwatch.model import Health

_COLORS = {Health.HEALTHY: "32", Health.WARNING: "33", Health.CRITICAL: "31"}


def _fmt_duration(seconds: float) -> str:
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    return f"{minutes}m{secs:02d}s" if minutes else f"{secs}s"


def render_dashboard(view: FleetView, *, color: bool = False, limit: int = 40) -> str:
    """Render the fleet as a fixed-width text table."""

    def paint(text: str, code: str) -> str:
        return f"\x1b[{code}m{text}\x1b[0m" if color else text

    fresh = [t for t in view.targets if not t.stale]
    stale = len(view.targets) - len(fresh)
    lines = [
        f"protectionwatch  targets={len(view.targets)} fresh={len(fresh)} stale={stale} "
        f"polls ok={view.polls_ok} failed={view.polls_failed}",
        "",
        f"{'TARGET':<20} {'GROUP':<10} {'HEALTH':<9} {'RPO':>8} {'OBJECTIVE':>10} {'AGE':>7}",
    ]
    for tv in view.targets[:limit]:
        s = tv.snapshot
        if tv.stale:
            health = paint(f"{'STALE':<9}", "90")
            rpo, obj = "-", "-"
        else:
            health = paint(f"{s.health.value:<9}", _COLORS[s.health])
            rpo, obj = _fmt_duration(s.rpo_seconds), _fmt_duration(s.rpo_target_seconds)
        lines.append(
            f"{s.target_id:<20} {s.group:<10} {health} {rpo:>8} {obj:>10} "
            f"{_fmt_duration(tv.age_seconds):>7}"
        )
    hidden = len(view.targets) - limit
    if hidden > 0:
        lines.append(f"... {hidden} more not shown")
    if view.consecutive_failures:
        lines.append("")
        lines.append(paint(f"WARNING: {view.consecutive_failures} consecutive poll failures", "31"))
    return "\n".join(lines) + "\n"


def run_dashboard(
    get_view: Callable[[], FleetView],
    stop: threading.Event,
    refresh: float = 2.0,
    out: TextIO = sys.stdout,
) -> None:
    """Redraw the dashboard until ``stop`` is set."""
    color = out.isatty()
    while not stop.is_set():
        out.write("\x1b[2J\x1b[H" + render_dashboard(get_view(), color=color))
        out.flush()
        stop.wait(refresh)
