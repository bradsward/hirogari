from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path

from hirogari.analysis import Classification, compute_diff_in_diff, diff_in_diff
from hirogari.store import Event, MetricPoint, Store

EVENT = date(2026, 3, 1)


def _flat_with_step(
    event: date, baseline: float, amplitude: float, post_value: float
) -> dict[date, float]:
    """30 days of oscillating baseline before `event`, then a flat step
    to `post_value` for 50 days from `event` on."""
    series: dict[date, float] = {}
    for i in range(1, 31):
        delta = amplitude if i % 2 == 0 else -amplitude
        series[event - timedelta(days=i)] = baseline + delta
    for i in range(50):
        series[event + timedelta(days=i)] = post_value
    return series


# ---------------------------------------------------------------------------
# An ecosystem-wide shock, shared by treatment and controls, must cancel
# ---------------------------------------------------------------------------


def test_shared_shock_cancels_out_in_did() -> None:
    treatment = _flat_with_step(EVENT, baseline=100.0, amplitude=3.0, post_value=130.0)  # +30%
    control_a = _flat_with_step(EVENT, baseline=200.0, amplitude=6.0, post_value=260.0)  # +30%
    control_b = _flat_with_step(EVENT, baseline=50.0, amplitude=1.5, post_value=65.0)  # +30%

    result = compute_diff_in_diff(
        treatment, {"control/a": control_a, "control/b": control_b}, EVENT
    )

    assert result.treatment.classification is Classification.SUSTAINED
    assert result.treatment.immediate_lift_pct is not None
    # Wider tolerance than a "clean" 30%: _flat_with_step's day-to-day
    # (period-2) alternation doesn't evenly divide a 7-day week, so
    # weekly-aggregated trend fitting (see _weekly_means) picks up a
    # small deterministic slope from that mismatch -- unrelated to the
    # real-world weekday/weekend (period-7) noise this fix targets, and
    # harmless here since it affects treatment and controls identically
    # (see the near-exact DiD cancellation asserted below).
    assert math.isclose(result.treatment.immediate_lift_pct, 0.30, abs_tol=0.04)

    assert set(result.control_projects_used) == {"control/a", "control/b"}
    assert result.control_projects_skipped == []
    assert result.control_immediate_lift_pct is not None
    assert math.isclose(result.control_immediate_lift_pct, 0.30, abs_tol=0.04)  # see note above

    # The shock hit treatment and controls alike -> nets to ~0, not ~30%.
    assert result.did_immediate_lift_pct is not None
    assert abs(result.did_immediate_lift_pct) < 0.03
    assert result.did_sustained_lift_pct is not None
    assert abs(result.did_sustained_lift_pct) < 0.03


# ---------------------------------------------------------------------------
# A treatment-specific effect, with flat controls, must survive DiD intact
# ---------------------------------------------------------------------------


def test_project_specific_lift_survives_flat_controls() -> None:
    treatment = _flat_with_step(EVENT, baseline=100.0, amplitude=3.0, post_value=130.0)  # +30%
    control_a = _flat_with_step(EVENT, baseline=200.0, amplitude=6.0, post_value=200.0)  # flat
    control_b = _flat_with_step(EVENT, baseline=50.0, amplitude=1.5, post_value=50.0)  # flat

    result = compute_diff_in_diff(
        treatment, {"control/a": control_a, "control/b": control_b}, EVENT
    )

    assert result.control_immediate_lift_pct is not None
    assert abs(result.control_immediate_lift_pct) < 0.02  # controls read ~flat

    assert result.did_immediate_lift_pct is not None
    assert math.isclose(result.did_immediate_lift_pct, 0.30, abs_tol=0.03)  # lift preserved


# ---------------------------------------------------------------------------
# A control with an event inside its own window is excluded, not averaged in
# ---------------------------------------------------------------------------


def test_control_with_its_own_event_in_window_is_skipped() -> None:
    treatment = _flat_with_step(EVENT, baseline=100.0, amplitude=3.0, post_value=130.0)
    clean_control = _flat_with_step(EVENT, baseline=200.0, amplitude=6.0, post_value=200.0)
    confounded_control = _flat_with_step(EVENT, baseline=50.0, amplitude=1.5, post_value=50.0)

    result = compute_diff_in_diff(
        treatment,
        {"control/clean": clean_control, "control/confounded": confounded_control},
        EVENT,
        control_events_by_project={
            "control/confounded": [EVENT + timedelta(days=5)],  # falls inside its own window
        },
    )

    assert result.control_projects_used == ["control/clean"]
    assert result.control_projects_skipped == ["control/confounded"]


# ---------------------------------------------------------------------------
# No usable controls -> DiD fields are None with an explanatory note, not a crash
# ---------------------------------------------------------------------------


def test_no_usable_controls_is_none_not_a_crash() -> None:
    treatment = _flat_with_step(EVENT, baseline=100.0, amplitude=3.0, post_value=130.0)

    result = compute_diff_in_diff(treatment, {}, EVENT)

    assert result.control_projects_used == []
    assert result.control_immediate_lift_pct is None
    assert result.did_immediate_lift_pct is None
    assert any("no usable control" in n for n in result.notes)
    # treatment's own reading is completely unaffected by having no controls
    assert result.treatment.classification is Classification.SUSTAINED


def test_all_controls_insufficient_are_skipped() -> None:
    treatment = _flat_with_step(EVENT, baseline=100.0, amplitude=3.0, post_value=130.0)
    sparse_control = {EVENT: 10.0}  # nowhere near enough data

    result = compute_diff_in_diff(treatment, {"control/sparse": sparse_control}, EVENT)

    assert result.control_projects_used == []
    assert result.control_projects_skipped == ["control/sparse"]
    assert result.did_immediate_lift_pct is None


# ---------------------------------------------------------------------------
# to_dict
# ---------------------------------------------------------------------------


def test_to_dict_includes_both_treatment_and_did_fields() -> None:
    treatment = _flat_with_step(EVENT, baseline=100.0, amplitude=3.0, post_value=130.0)
    control_a = _flat_with_step(EVENT, baseline=200.0, amplitude=6.0, post_value=200.0)

    result = compute_diff_in_diff(
        treatment, {"control/a": control_a}, EVENT, metric_name="pypi.downloads"
    )
    d = result.to_dict()

    assert d["metric_name"] == "pypi.downloads"  # from the embedded treatment LiftResult
    assert d["classification"] == "SUSTAINED"
    assert d["control_projects_used"] == "control/a"
    assert "did_immediate_lift_pct" in d
    assert isinstance(d["did_notes"], str)


# ---------------------------------------------------------------------------
# Store-backed wrapper
# ---------------------------------------------------------------------------


def test_diff_in_diff_wrapper_reads_from_store(tmp_path: Path) -> None:
    store = Store(tmp_path / "did.db")
    treatment_series = _flat_with_step(EVENT, baseline=100.0, amplitude=3.0, post_value=130.0)
    control_series = _flat_with_step(EVENT, baseline=200.0, amplitude=6.0, post_value=200.0)

    store.upsert_metrics(
        MetricPoint("acme/treatment", "pypi", "downloads", d, v)
        for d, v in treatment_series.items()
    )
    store.upsert_metrics(
        MetricPoint("acme/control", "pypi", "downloads", d, v) for d, v in control_series.items()
    )
    store.upsert_event(Event("acme/treatment", EVENT, "release", "v1.0.0"))

    result = diff_in_diff(
        store, "acme/treatment", "pypi.downloads", EVENT, control_projects=["acme/control"]
    )

    assert result.control_projects_used == ["acme/control"]
    assert result.did_immediate_lift_pct is not None
    assert math.isclose(result.did_immediate_lift_pct, 0.30, abs_tol=0.03)


def test_diff_in_diff_wrapper_excludes_treatment_from_its_own_controls(tmp_path: Path) -> None:
    store = Store(tmp_path / "did.db")
    treatment_series = _flat_with_step(EVENT, baseline=100.0, amplitude=3.0, post_value=130.0)
    store.upsert_metrics(
        MetricPoint("acme/treatment", "pypi", "downloads", d, v)
        for d, v in treatment_series.items()
    )
    store.upsert_event(Event("acme/treatment", EVENT, "release", "v1.0.0"))

    # Passing the treatment project itself in the control pool must not
    # make it its own control.
    result = diff_in_diff(
        store,
        "acme/treatment",
        "pypi.downloads",
        EVENT,
        control_projects=["acme/treatment"],
    )
    assert result.control_projects_used == []
    assert result.control_projects_skipped == []
