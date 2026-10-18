"""Domain model for the invented, generic data-protection API contract."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Health(StrEnum):
    """Overall protection health of one target."""

    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"


class JobState(StrEnum):
    """Outcome of the most recent run of a protection job."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RUNNING = "running"


@dataclass(frozen=True)
class JobResult:
    """Latest run of one protection job."""

    job_class: str
    state: JobState
    duration_seconds: float


@dataclass(frozen=True)
class TargetSnapshot:
    """What a client reports for one protected target at one moment.

    ``rpo_seconds`` is the age of the newest recovery point;
    ``rpo_target_seconds`` is the objective it is measured against.
    """

    target_id: str
    group: str
    health: Health
    rpo_seconds: float
    rpo_target_seconds: float
    jobs: tuple[JobResult, ...] = ()
