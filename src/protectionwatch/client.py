"""Abstract fleet client and a deterministic synthetic implementation."""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import Protocol

from protectionwatch.model import Health, JobResult, JobState, TargetSnapshot

GROUPS = ("alpha", "bravo", "charlie", "delta")
JOB_CLASSES = ("snapshot", "replication", "archive", "verify")


class FleetClient(Protocol):
    """Anything that can report the current state of the fleet.

    Implementations may raise any exception to signal a failed poll.
    """

    def fetch_fleet(self) -> Sequence[TargetSnapshot]: ...


class SyntheticClient:
    """Seeded generator of plausible fleet states; no network, no real data.

    The same ``seed`` and call count always yield the same fleet.
    """

    def __init__(self, seed: int = 1, targets: int = 12) -> None:
        if targets < 0:
            raise ValueError("targets must be >= 0")
        self._seed = seed
        self._targets = targets
        self._tick = 0

    def fetch_fleet(self) -> Sequence[TargetSnapshot]:
        self._tick += 1
        return [self._make(i) for i in range(self._targets)]

    def _make(self, index: int) -> TargetSnapshot:
        rng = random.Random(f"{self._seed}:{self._tick}:{index}")
        rpo_target = 3600.0 * (1 + index % 3)
        rpo = rpo_target * rng.choice((0.2, 0.5, 0.9, 1.4, 2.5))
        ratio = rpo / rpo_target
        health = Health.HEALTHY if ratio <= 1 else Health.WARNING if ratio <= 2 else Health.CRITICAL
        jobs = tuple(
            JobResult(
                job_class=JOB_CLASSES[(index + j) % len(JOB_CLASSES)],
                state=rng.choices(
                    (JobState.SUCCEEDED, JobState.FAILED, JobState.RUNNING), (8, 1, 2)
                )[0],
                duration_seconds=round(rng.uniform(1, 900), 1),
            )
            for j in range(rng.randint(2, 4))
        )
        return TargetSnapshot(
            target_id=f"node-{index + 1:03d}",
            group=GROUPS[index % len(GROUPS)],
            health=health,
            rpo_seconds=round(rpo, 1),
            rpo_target_seconds=rpo_target,
            jobs=jobs,
        )
