from __future__ import annotations

from protectionwatch.collector import Poller
from protectionwatch.config import Config
from protectionwatch.exposition import render_metrics
from protectionwatch.metrics import OVERFLOW, LabelLimiter

from .helpers import FakeClock, ScriptedClient, job, snap


def test_limiter_admits_first_n_then_overflows() -> None:
    lim = LabelLimiter(2)
    assert [lim.map(v) for v in ("a", "b", "c", "a", "d")] == ["a", "b", OVERFLOW, "a", OVERFLOW]
    assert lim.overflowed == 2


def test_group_and_job_class_labels_are_bounded() -> None:
    cfg = Config(max_groups=2, max_job_classes=1)
    fleet = [snap(f"n{i}", group=f"g{i}", jobs=(job(f"class{i}"),)) for i in range(5)]
    poller = Poller(ScriptedClient(fleet), cfg, FakeClock())
    poller.poll_once()
    view = poller.view()
    groups = {t.snapshot.group for t in view.targets}
    classes = {j.job_class for t in view.targets for j in t.snapshot.jobs}
    assert groups == {"g0", "g1", OVERFLOW}
    assert classes == {"class0", OVERFLOW}
    assert view.overflowed_labels == 3 + 4


def test_target_cap_drops_new_targets_and_counts() -> None:
    cfg = Config(max_targets=3)
    fleet = [snap(f"n{i}") for i in range(10)]
    poller = Poller(ScriptedClient(fleet), cfg, FakeClock())
    poller.poll_once()
    view = poller.view()
    assert len(view.targets) == 3
    assert view.dropped_targets == 7
    assert view.dropped_by_cap == 7 and view.dropped_duplicates == 0
    text = render_metrics(view)
    assert 'protectionwatch_dropped_targets_total{reason="cap"} 7' in text
    assert 'protectionwatch_dropped_targets_total{reason="duplicate"} 0' in text


def test_hostile_target_ids_are_sanitised_and_deduplicated() -> None:
    fleet = [snap('a"b'), snap("a_b"), snap("x\ny")]
    poller = Poller(ScriptedClient(fleet), Config(), FakeClock())
    poller.poll_once()
    ids = [t.snapshot.target_id for t in poller.view().targets]
    assert ids == ["a_b", "x_y"]
    assert poller.view().dropped_targets == 1
    assert poller.view().dropped_duplicates == 1 and poller.view().dropped_by_cap == 0
    text = render_metrics(poller.view())
    assert 'protectionwatch_dropped_targets_total{reason="duplicate"} 1' in text
    assert 'protectionwatch_dropped_targets_total{reason="cap"} 0' in text
    assert 'a"b' not in text


def test_series_count_does_not_grow_with_repeated_polls() -> None:
    fleet = [snap(f"n{i}", jobs=(job(),)) for i in range(5)]
    poller = Poller(ScriptedClient(fleet), Config(), FakeClock())
    poller.poll_once()
    first = len(render_metrics(poller.view()).splitlines())
    for _ in range(20):
        poller.poll_once()
    assert len(render_metrics(poller.view()).splitlines()) == first


def test_dropped_counter_is_monotonic_across_polls() -> None:
    poller = Poller(
        ScriptedClient([snap(f"n{i}") for i in range(4)]), Config(max_targets=2), FakeClock()
    )
    seen = []
    for _ in range(3):
        poller.poll_once()
        seen.append(poller.view().dropped_by_cap)
    assert seen == [2, 4, 6]  # counts observations per poll, never decreases


def test_cap_and_duplicate_reasons_are_separate() -> None:
    fleet = [snap("a"), snap("a"), snap("b"), snap("c")]
    poller = Poller(ScriptedClient(fleet), Config(max_targets=2), FakeClock())
    poller.poll_once()
    view = poller.view()
    assert (view.dropped_by_cap, view.dropped_duplicates, view.dropped_targets) == (1, 1, 2)


def test_per_target_families_share_label_names() -> None:
    fleet = [snap("n1", group="g", jobs=(job(),)), snap("n2", group="g")]
    clock = FakeClock()
    poller = Poller(ScriptedClient(fleet), Config(stale_after=100), clock)
    poller.poll_once()
    text = render_metrics(poller.view())
    per_target = (
        "target_stale", "target_data_age_seconds", "target_health", "target_rpo_seconds",
        "target_rpo_objective_seconds", "target_rpo_breached",
    )  # fmt: skip
    for family in per_target:
        lines = [ln for ln in text.splitlines() if ln.startswith(f"protectionwatch_{family}{{")]
        assert lines, family
        for ln in lines:
            assert 'target="' in ln and 'group="g"' in ln, ln


def test_stale_target_keeps_group_on_age_and_stale_series() -> None:
    clock = FakeClock()
    poller = Poller(
        ScriptedClient([snap("n1", group="g")], RuntimeError("down")), Config(stale_after=10), clock
    )
    poller.poll_once()
    clock.now += 50
    poller.poll_once()
    text = render_metrics(poller.view())
    assert 'protectionwatch_target_stale{target="n1",group="g"} 1' in text
    assert 'protectionwatch_target_data_age_seconds{target="n1",group="g"} 50' in text
    assert "protectionwatch_target_health" not in text
