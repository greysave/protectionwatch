"""Validated runtime configuration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    """Polling and cardinality settings. Invalid values raise ``ValueError``."""

    host: str = "127.0.0.1"
    port: int = 9877
    poll_interval: float = 15.0
    max_backoff: float = 120.0
    stale_after: float = 60.0
    retention: float = 3600.0
    max_targets: int = 200
    max_groups: int = 16
    max_job_classes: int = 8

    def __post_init__(self) -> None:
        if not 0 <= self.port <= 65535:
            raise ValueError("port must be between 0 and 65535")
        if self.poll_interval <= 0:
            raise ValueError("poll_interval must be > 0")
        if self.max_backoff < self.poll_interval:
            raise ValueError("max_backoff must be >= poll_interval")
        if self.stale_after <= 0:
            raise ValueError("stale_after must be > 0")
        if self.retention < self.stale_after:
            raise ValueError("retention must be >= stale_after")
        if min(self.max_targets, self.max_groups, self.max_job_classes) < 1:
            raise ValueError("cardinality limits must be >= 1")
