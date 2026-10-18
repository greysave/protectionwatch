"""Polling, bounded state and stale-data tracking."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace

from protectionwatch.client import FleetClient
from protectionwatch.config import Config
from protectionwatch.metrics import LabelLimiter, sanitize_label
from protectionwatch.model import JobResult, TargetSnapshot

log = logging.getLogger("protectionwatch.collector")

Clock = Callable[[], float]


@dataclass(frozen=True)
class TargetView:
    """A stored target with its age; ``stale`` targets must not be shown as current."""

    snapshot: TargetSnapshot
    age_seconds: float
    stale: bool


@dataclass(frozen=True)
class FleetView:
    """Immutable picture of collector state at one instant."""

    targets: tuple[TargetView, ...]
    polls_ok: int
    polls_failed: int
    consecutive_failures: int
    last_success_ts: float | None
    last_poll_seconds: float
    dropped_by_cap: int
    dropped_duplicates: int
    overflowed_labels: int

    @property
    def dropped_targets(self) -> int:
        """All target observations dropped, for any reason (cumulative, counted per poll)."""
        return self.dropped_by_cap + self.dropped_duplicates


class Poller:
    """Polls a ``FleetClient`` and keeps a bounded, label-safe copy of the result."""

    def __init__(self, client: FleetClient, config: Config, clock: Clock = time.time) -> None:
        self._client = client
        self._config = config
        self._clock = clock
        self._lock = threading.Lock()
        self._groups = LabelLimiter(config.max_groups)
        self._job_classes = LabelLimiter(config.max_job_classes)
        self._entries: dict[str, tuple[TargetSnapshot, float]] = {}
        self._ok = 0
        self._failed = 0
        self._consecutive = 0
        self._last_success: float | None = None
        self._last_duration = 0.0
        self._dropped_cap = 0
        self._dropped_duplicate = 0

    def poll_once(self) -> bool:
        """Poll once. On failure keep previous data (it will age into staleness)."""
        started = self._clock()
        try:
            fetched = list(self._client.fetch_fleet())
        except Exception as exc:
            with self._lock:
                self._failed += 1
                self._consecutive += 1
                self._last_duration = max(0.0, self._clock() - started)
            log.warning("poll failed: %s: %s", type(exc).__name__, exc)
            return False
        now = self._clock()
        with self._lock:
            self._ingest(fetched, now)
            self._ok += 1
            self._consecutive = 0
            self._last_success = now
            self._last_duration = max(0.0, now - started)
        return True

    def _ingest(self, fetched: list[TargetSnapshot], now: float) -> None:
        seen: set[str] = set()
        dropped_cap = 0
        dropped_duplicate = 0
        for snap in fetched:
            clean = self._clean(snap)
            if clean.target_id in seen:
                dropped_duplicate += 1
                continue
            if (
                clean.target_id not in self._entries
                and len(self._entries) >= self._config.max_targets
            ):
                dropped_cap += 1
                continue
            seen.add(clean.target_id)
            self._entries[clean.target_id] = (clean, now)
        self._dropped_cap += dropped_cap
        self._dropped_duplicate += dropped_duplicate
        cutoff = now - self._config.retention
        for key in [k for k, (_, ts) in self._entries.items() if ts < cutoff]:
            del self._entries[key]

    def _clean(self, snap: TargetSnapshot) -> TargetSnapshot:
        jobs = tuple(
            JobResult(self._job_classes.map(j.job_class), j.state, max(0.0, j.duration_seconds))
            for j in snap.jobs
        )
        return replace(
            snap,
            target_id=sanitize_label(snap.target_id),
            group=self._groups.map(snap.group),
            jobs=jobs,
        )

    def view(self) -> FleetView:
        now = self._clock()
        with self._lock:
            targets = tuple(
                TargetView(s, max(0.0, now - ts), now - ts > self._config.stale_after)
                for s, ts in sorted(self._entries.values(), key=lambda e: e[0].target_id)
            )
            return FleetView(
                targets=targets,
                polls_ok=self._ok,
                polls_failed=self._failed,
                consecutive_failures=self._consecutive,
                last_success_ts=self._last_success,
                last_poll_seconds=self._last_duration,
                dropped_by_cap=self._dropped_cap,
                dropped_duplicates=self._dropped_duplicate,
                overflowed_labels=self._groups.overflowed + self._job_classes.overflowed,
            )

    def next_delay(self) -> float:
        """Seconds to wait before the next poll: exponential backoff while failing."""
        with self._lock:
            fails = self._consecutive
        delay = self._config.poll_interval * float(2 ** min(fails, 10))
        return min(delay, self._config.max_backoff)

    def run(self, stop: threading.Event) -> None:
        """Poll until ``stop`` is set; returns promptly once it is."""
        while not stop.is_set():
            self.poll_once()
            stop.wait(self.next_delay())
