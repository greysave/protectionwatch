from __future__ import annotations

from collections.abc import Sequence

from protectionwatch.model import Health, JobResult, JobState, TargetSnapshot


class FakeClock:
    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


class ScriptedClient:
    """Returns queued fleets; an Exception in the queue is raised instead."""

    def __init__(self, *steps: Sequence[TargetSnapshot] | Exception) -> None:
        self.steps = list(steps)
        self.calls = 0

    def fetch_fleet(self) -> Sequence[TargetSnapshot]:
        self.calls += 1
        step = self.steps.pop(0) if len(self.steps) > 1 else self.steps[0]
        if isinstance(step, Exception):
            raise step
        return step


def snap(
    target_id: str = "node-001",
    group: str = "alpha",
    health: Health = Health.HEALTHY,
    rpo: float = 600.0,
    objective: float = 3600.0,
    jobs: tuple[JobResult, ...] = (),
) -> TargetSnapshot:
    return TargetSnapshot(target_id, group, health, rpo, objective, jobs)


def job(
    job_class: str = "snapshot", state: JobState = JobState.SUCCEEDED, d: float = 10.0
) -> JobResult:
    return JobResult(job_class, state, d)
