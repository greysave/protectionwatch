"""Turn a ``FleetView`` into Prometheus metric families.

Every per-target family carries the same ``target`` and ``group`` labels. Stale targets
expose only age and a stale flag; their old health, RPO and job
values are withheld so dashboards and alerts never mistake them for current data.
"""

from __future__ import annotations

from protectionwatch import __version__
from protectionwatch.collector import FleetView
from protectionwatch.metrics import MetricFamily, render
from protectionwatch.model import Health

DURATION_BUCKETS = (1.0, 5.0, 30.0, 120.0, 600.0)


def build_families(view: FleetView) -> list[MetricFamily]:
    info = MetricFamily("protectionwatch_build_info", "Build information.", "gauge")
    info.add(1, version=__version__)

    up = MetricFamily("protectionwatch_target_stale", "1 if target data is stale.", "gauge")
    age = MetricFamily(
        "protectionwatch_target_data_age_seconds",
        "Seconds since target data was refreshed.",
        "gauge",
    )
    health = MetricFamily("protectionwatch_target_health", "One-hot target health state.", "gauge")
    rpo = MetricFamily(
        "protectionwatch_target_rpo_seconds", "Age of newest recovery point.", "gauge"
    )
    rpo_target = MetricFamily(
        "protectionwatch_target_rpo_objective_seconds", "Recovery point objective.", "gauge"
    )
    breach = MetricFamily(
        "protectionwatch_target_rpo_breached", "1 if RPO exceeds its objective.", "gauge"
    )
    jobs = MetricFamily(
        "protectionwatch_jobs", "Latest job runs by group and state (fresh targets only).", "gauge"
    )
    hist = MetricFamily(
        "protectionwatch_job_duration_seconds",
        "Duration of latest job runs by class (fresh targets only).",
        "histogram",
    )

    job_counts: dict[tuple[str, str], int] = {}
    durations: dict[str, list[float]] = {}
    for tv in view.targets:
        snap = tv.snapshot
        t = snap.target_id
        up.add(1 if tv.stale else 0, target=t, group=snap.group)
        age.add(tv.age_seconds, target=t, group=snap.group)
        if tv.stale:
            continue
        for level in Health:
            health.add(
                1 if snap.health is level else 0, target=t, group=snap.group, state=level.value
            )
        rpo.add(snap.rpo_seconds, target=t, group=snap.group)
        rpo_target.add(snap.rpo_target_seconds, target=t, group=snap.group)
        breach.add(
            1 if snap.rpo_seconds > snap.rpo_target_seconds else 0, target=t, group=snap.group
        )
        for job in snap.jobs:
            key = (snap.group, job.state.value)
            job_counts[key] = job_counts.get(key, 0) + 1
            durations.setdefault(job.job_class, []).append(job.duration_seconds)

    for (group, state), count in sorted(job_counts.items()):
        jobs.add(count, group=group, state=state)
    for job_class in sorted(durations):
        values = durations[job_class]
        for bound in DURATION_BUCKETS:
            hist.add(
                sum(1 for v in values if v <= bound),
                name=f"{hist.name}_bucket",
                job_class=job_class,
                le=repr(bound),
            )
        hist.add(len(values), name=f"{hist.name}_bucket", job_class=job_class, le="+Inf")
        hist.add(sum(values), name=f"{hist.name}_sum", job_class=job_class)
        hist.add(len(values), name=f"{hist.name}_count", job_class=job_class)

    polls = MetricFamily("protectionwatch_polls_total", "Polls by result.", "counter")
    polls.add(view.polls_ok, result="ok")
    polls.add(view.polls_failed, result="error")
    last = MetricFamily(
        "protectionwatch_last_successful_poll_timestamp_seconds",
        "Unix time of the last successful poll.",
        "gauge",
    )
    if view.last_success_ts is not None:
        last.add(view.last_success_ts)
    dur = MetricFamily("protectionwatch_last_poll_duration_seconds", "Last poll duration.", "gauge")
    dur.add(view.last_poll_seconds)
    consec = MetricFamily(
        "protectionwatch_consecutive_poll_failures", "Failed polls since last success.", "gauge"
    )
    consec.add(view.consecutive_failures)
    dropped = MetricFamily(
        "protectionwatch_dropped_targets_total",
        "Target observations dropped, by reason; counted once per poll in which they recur.",
        "counter",
    )
    dropped.add(view.dropped_by_cap, reason="cap")
    dropped.add(view.dropped_duplicates, reason="duplicate")
    overflow = MetricFamily(
        "protectionwatch_label_overflow_total",
        "Label values folded into 'other' by cardinality limits.",
        "counter",
    )
    overflow.add(view.overflowed_labels)

    return [
        info, up, age, health, rpo, rpo_target, breach, jobs, hist,
        polls, last, dur, consec, dropped, overflow,
    ]  # fmt: skip


def render_metrics(view: FleetView) -> str:
    return render(build_families(view))
