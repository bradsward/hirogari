from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path

import pytest

from hirogari.analysis import Classification, compute_lift, lift
from hirogari.store import Event, MetricPoint, Store

EVENT = date(2026, 3, 1)


def _alternating_baseline(
    event: date, days: int, amplitude: float, center: float = 100.0
) -> dict[date, float]:
    """Deterministic oscillating series (not flat, so MAD > 0) for `days`
    days strictly before `event`."""
    series: dict[date, float] = {}
    for i in range(1, days + 1):
        delta = amplitude if i % 2 == 0 else -amplitude
        series[event - timedelta(days=i)] = center + delta
    return series


def _constant_after(
    event: date, days: int, value: float, start_offset: int = 0
) -> dict[date, float]:
    return {event + timedelta(days=start_offset + i): value for i in range(days)}


def _growth_series(
    event: date, growth_per_day: float, start: float, offsets: range
) -> dict[date, float]:
    return {event + timedelta(days=o): start * (growth_per_day**o) for o in offsets}


# ---------------------------------------------------------------------------
# 1. Clean step change: flat baseline, immediate jump that holds -> SUSTAINED
# ---------------------------------------------------------------------------


def test_clean_step_change_is_sustained() -> None:
    series = _alternating_baseline(EVENT, 30, amplitude=3.0)
    series.update(_constant_after(EVENT, 50, value=180.0))

    result = compute_lift(series, EVENT)

    assert result.classification is Classification.SUSTAINED
    assert result.baseline is not None and math.isclose(result.baseline, 100.0, abs_tol=0.01)
    assert result.immediate is not None and math.isclose(result.immediate, 180.0, abs_tol=0.01)
    assert result.sustained is not None and math.isclose(result.sustained, 180.0, abs_tol=0.01)
    assert result.immediate_lift_pct is not None and result.immediate_lift_pct > 0.5
    assert result.sustained_lift_pct is not None and result.sustained_lift_pct > 0.5
    assert result.robust_z is not None and result.robust_z >= 2.0
    assert not result.confounded
    assert result.trend_pct_per_day is not None and abs(result.trend_pct_per_day) < 0.01


# ---------------------------------------------------------------------------
# 2. Decaying spike: big immediate jump that fades back to baseline -> SPIKE
# ---------------------------------------------------------------------------


def test_decaying_spike_is_spike() -> None:
    series = _alternating_baseline(EVENT, 30, amplitude=3.0)
    series.update(_constant_after(EVENT, 14, value=300.0))  # immediate window: big jump
    series.update(_constant_after(EVENT, 36, value=103.0, start_offset=14))  # decays back

    result = compute_lift(series, EVENT)

    assert result.classification is Classification.SPIKE
    assert result.immediate_lift_pct is not None and result.immediate_lift_pct > 0.5
    assert result.sustained_lift_pct is not None and result.sustained_lift_pct < 0.10


# ---------------------------------------------------------------------------
# 3. Pure noise: same oscillation before and after -> FLAT
# ---------------------------------------------------------------------------


def test_pure_noise_is_flat() -> None:
    series = _alternating_baseline(EVENT, 30, amplitude=4.0)
    for i in range(50):
        delta = 4.0 if i % 2 == 0 else -4.0
        series[EVENT + timedelta(days=i)] = 100.0 + delta

    result = compute_lift(series, EVENT)

    assert result.classification is Classification.FLAT
    assert result.immediate is not None and math.isclose(result.immediate, 100.0, abs_tol=0.01)


# ---------------------------------------------------------------------------
# 3b. The bug this session fixed: organic growth alone must NOT read as lift
# ---------------------------------------------------------------------------


def test_organic_growth_with_no_event_effect_is_flat_not_sustained() -> None:
    """A project growing steadily should not show lift after every date
    just because later days are naturally higher than earlier ones.
    Un-trend-adjusted, this reads as a clean SUSTAINED win; trend-adjusted,
    it's FLAT because actual matches the counterfactual (growth just
    continues undisturbed through the "event")."""
    growth_per_day = 1.005  # ~0.5%/day, ~3.6%/week
    series = _growth_series(EVENT, growth_per_day, start=1000.0, offsets=range(-30, 51))

    result = compute_lift(series, EVENT)

    assert result.classification is Classification.FLAT
    assert result.trend_pct_per_day is not None
    assert math.isclose(result.trend_pct_per_day, growth_per_day - 1.0, rel_tol=0.05)
    assert result.immediate_lift_pct is not None and abs(result.immediate_lift_pct) < 0.02


def test_real_lift_on_top_of_growth_trend_is_still_detected() -> None:
    """Trend-adjustment must not wash out a genuine effect layered on top
    of organic growth: a permanent 60% step-up from the event on, riding
    the same underlying growth curve, should still read as SUSTAINED."""
    growth_per_day = 1.003
    series = _growth_series(EVENT, growth_per_day, start=1000.0, offsets=range(-30, 0))
    for offset in range(0, 51):
        series[EVENT + timedelta(days=offset)] = 1.6 * 1000.0 * (growth_per_day**offset)

    result = compute_lift(series, EVENT)

    assert result.classification is Classification.SUSTAINED
    assert result.immediate_lift_pct is not None and result.immediate_lift_pct > 0.4
    assert result.sustained_lift_pct is not None and result.sustained_lift_pct > 0.4


# ---------------------------------------------------------------------------
# 4. Gaps: too few complete weeks present in pre/post windows -> INSUFFICIENT
# ---------------------------------------------------------------------------


def test_sparse_series_is_insufficient() -> None:
    series: dict[date, float] = {}
    # Only 5 scattered pre-event days and 5 scattered post-event days --
    # not enough to complete even one full week on either side.
    for i in [1, 3, 5, 7, 9]:
        series[EVENT - timedelta(days=i)] = 100.0
    for i in [0, 2, 4, 6, 8]:
        series[EVENT + timedelta(days=i)] = 100.0

    result = compute_lift(series, EVENT)

    assert result.classification is Classification.INSUFFICIENT
    assert result.immediate_lift_pct is None
    assert result.robust_z is None
    assert any("insufficient data" in n for n in result.notes)


def test_incomplete_week_is_excluded_even_with_high_raw_day_coverage() -> None:
    """12 of 14 pre-window days present (~86% raw coverage) would have
    passed an old day-count threshold, but the missing 2 days fall in the
    same week -- so that whole week is dropped rather than letting a
    weekday-skewed partial week bias the baseline mean."""
    series: dict[date, float] = {}
    for offset in range(-14, -7):  # week 1: fully present
        series[EVENT + timedelta(days=offset)] = 100.0
    for offset in range(-7, -1):  # week 2: only 6 of 7 days
        series[EVENT + timedelta(days=offset)] = 100.0
    # offset -1 (week 2's 7th day) intentionally missing
    series.update(_constant_after(EVENT, 50, value=100.0))

    result = compute_lift(series, EVENT)

    assert result.classification is Classification.INSUFFICIENT
    assert result.pre_days_available == 7  # only week 1 counted


# ---------------------------------------------------------------------------
# Edge cases called out explicitly in the spec
# ---------------------------------------------------------------------------


def test_zero_baseline_uses_flag_not_a_sentinel() -> None:
    series = {EVENT - timedelta(days=i): 0.0 for i in range(1, 31)}
    series.update(_constant_after(EVENT, 50, value=50.0))

    result = compute_lift(series, EVENT)

    assert result.baseline == 0.0
    assert result.zero_baseline is True
    assert result.immediate_lift_pct is None
    assert result.sustained_lift_pct is None
    assert result.robust_z is None  # no sentinel value -- flag carries the signal instead
    # Zero baseline with any real positive value afterwards should still
    # read as a (sustained) lift, not silently vanish as "no signal".
    assert result.classification is Classification.SUSTAINED


def test_event_near_start_of_data_is_insufficient() -> None:
    # No data at all before the event -> can't establish a baseline.
    series = _constant_after(EVENT, 50, value=100.0)

    result = compute_lift(series, EVENT)

    assert result.classification is Classification.INSUFFICIENT
    assert result.baseline is None
    assert result.pre_days_available == 0


def test_event_near_end_of_data_is_insufficient_but_keeps_immediate_numbers() -> None:
    # Data covers baseline + immediate windows but stops right where the
    # sustain window (day 15) would begin -- e.g. a release from last week.
    series = _alternating_baseline(EVENT, 30, amplitude=3.0)
    series.update(_constant_after(EVENT, 14, value=180.0))

    result = compute_lift(series, EVENT)

    assert result.classification is Classification.INSUFFICIENT
    assert result.baseline is not None
    assert result.immediate is not None
    assert result.immediate_lift_pct is not None and result.immediate_lift_pct > 0.5
    assert result.sustained is None
    assert result.counterfactual_sustained is None
    assert any("cannot judge persistence" in n for n in result.notes)


def test_confounded_flags_overlapping_event() -> None:
    series = _alternating_baseline(EVENT, 30, amplitude=3.0)
    series.update(_constant_after(EVENT, 50, value=180.0))

    confounded = compute_lift(series, EVENT, other_event_dates=[EVENT + timedelta(days=5)])
    clean = compute_lift(series, EVENT, other_event_dates=[EVENT + timedelta(days=200)])

    assert confounded.confounded is True
    assert clean.confounded is False
    # Confounding doesn't change the math, just flags it.
    assert confounded.classification == clean.classification


def test_event_date_itself_excluded_from_confounded_check() -> None:
    series = _alternating_baseline(EVENT, 30, amplitude=3.0)
    series.update(_constant_after(EVENT, 50, value=180.0))

    result = compute_lift(series, EVENT, other_event_dates=[EVENT])
    assert result.confounded is False


# ---------------------------------------------------------------------------
# Custom window sizes / whole-week validation
# ---------------------------------------------------------------------------


def test_custom_window_sizes_are_respected() -> None:
    series = _alternating_baseline(EVENT, 10, amplitude=2.0)
    series.update(_constant_after(EVENT, 30, value=150.0))

    result = compute_lift(series, EVENT, pre=7, post=7, sustain_start=8, sustain_end=21)

    assert result.pre_days_available == 7
    assert result.post_days_available == 7
    assert result.sustain_days_available == 14  # 21 - 8 + 1
    assert result.classification is Classification.SUSTAINED


@pytest.mark.parametrize(
    "kwargs",
    [
        {"pre": 10},
        {"post": 13},
        {"sustain_start": 15, "sustain_end": 40},  # length 26, not a multiple of 7
    ],
)
def test_non_week_aligned_windows_are_rejected(kwargs: dict[str, int]) -> None:
    series = _alternating_baseline(EVENT, 30, amplitude=3.0)
    series.update(_constant_after(EVENT, 50, value=180.0))

    with pytest.raises(ValueError):
        compute_lift(series, EVENT, **kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# to_dict
# ---------------------------------------------------------------------------


def test_to_dict_is_flat_and_json_safe() -> None:
    series = _alternating_baseline(EVENT, 30, amplitude=3.0)
    series.update(_constant_after(EVENT, 50, value=180.0))
    result = compute_lift(series, EVENT, metric_name="pypi.downloads")

    d = result.to_dict()
    assert d["classification"] == "SUSTAINED"
    assert d["metric_name"] == "pypi.downloads"
    assert d["event_date"] == "2026-03-01"
    assert isinstance(d["notes"], str)
    assert "trend_pct_per_day" in d
    assert "counterfactual_immediate" in d
    assert "zero_baseline" in d


# ---------------------------------------------------------------------------
# Store-backed wrapper
# ---------------------------------------------------------------------------


def test_lift_wrapper_resolves_source_and_name(tmp_path: Path) -> None:
    store = Store(tmp_path / "wrapper.db")
    project = "acme/widget"
    series = _alternating_baseline(EVENT, 30, amplitude=3.0)
    series.update(_constant_after(EVENT, 50, value=180.0))
    store.upsert_metrics(
        MetricPoint(project, "pypi", "downloads", d, v) for d, v in series.items()
    )
    store.upsert_event(Event(project, EVENT, "release", "v1.0.0"))

    result = lift(store, project, "pypi.downloads", EVENT)

    assert result.metric_name == "pypi.downloads"
    assert result.classification is Classification.SUSTAINED


def test_lift_wrapper_rejects_bad_metric_format(tmp_path: Path) -> None:
    store = Store(tmp_path / "wrapper.db")
    with pytest.raises(ValueError):
        lift(store, "acme/widget", "downloads", EVENT)


def test_lift_wrapper_detects_confounding_from_stored_events(tmp_path: Path) -> None:
    store = Store(tmp_path / "wrapper.db")
    project = "acme/widget"
    series = _alternating_baseline(EVENT, 30, amplitude=3.0)
    series.update(_constant_after(EVENT, 50, value=180.0))
    store.upsert_metrics(
        MetricPoint(project, "pypi", "downloads", d, v) for d, v in series.items()
    )
    store.upsert_events(
        [
            Event(project, EVENT, "release", "v1.0.0"),
            Event(project, EVENT + timedelta(days=5), "post", "HN front page"),
        ]
    )

    result = lift(store, project, "pypi.downloads", EVENT)
    assert result.confounded is True
