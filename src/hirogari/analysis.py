"""Did an event move the metric, and did the movement last?

The core entry points are two functions:

* `compute_lift` — pure, operates on a plain `{date: value}` series plus an
  event date. No I/O. This is deliberately the thing under heavy test with
  synthetic series, because it's the part that has to be right.
* `lift` — a thin wrapper that pulls a series and the project's other
  events out of a `Store` and calls `compute_lift`. This is what the CLI
  calls.

Trend adjustment (read this before touching thresholds)
---------------------------------------------------------
A project growing organically at, say, 5%/week will have every post-event
window sitting above every pre-event window for reasons that have nothing
to do with the event. Comparing to the flat baseline mean would call that
"lift" on every single release. Instead, `compute_lift` fits a trend on the
baseline window and extrapolates it forward as the counterfactual: what the
metric would have looked like if nothing had happened. Lift is the actual
minus that counterfactual, not the actual minus the historical average.
The fit prefers log-linear (i.e. assumes the metric grows a constant
*percentage* per day, which is how adoption curves actually behave) and
falls back to plain linear only when the baseline has non-positive values,
where log() is undefined. Either way the fitted daily growth rate is
reported as `trend_pct_per_day` so it's visible whenever the correction is
doing real work.

Whole-week windows
-------------------
PyPI/star data is heavily weekday-skewed (CI runs on weekdays, humans
mostly don't `pip install` on Sundays). `pre`, `post`, and the sustain
window length must each be a whole number of weeks, and any 7-day block
within a window that isn't *fully* present in the series is dropped
entirely rather than averaged in partially — so a window missing three
Tuesdays and one missing three Sundays are treated identically (both drop
whatever week those gaps fall in), instead of silently landing on
different weekday mixes at "the same" coverage percentage.

One thing this tool does not and cannot separate: a release causes some
install traffic mechanically (CI pins bump, Dependabot fires, mirrors
resync) with no human ever deciding to adopt anything. `release` events
therefore measure something structurally different from `post`/`docs`
events, which are closer to pure human signal. See notes/ for more.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import StrEnum
from statistics import median
from typing import Any

# MAD -> stdev-equivalent scale factor for a normal distribution. Standard
# constant (1 / Phi^-1(3/4)) used so robust_z is roughly comparable in
# magnitude to an ordinary z-score, not just "some units of MAD".
_MAD_TO_STDEV = 1.4826

THRESHOLDS: dict[str, float] = {
    # A window is usable only if at least this fraction of its expected
    # *whole weeks* have all 7 days present. Raised from an earlier 0.60:
    # 8/14 days deciding a baseline was too loose, and day-granularity
    # coverage doesn't protect against weekday-skewed gaps the way
    # week-granularity coverage does (see module docstring). At the
    # default window sizes (2, 2, and 4 expected weeks) this rounds up to
    # requiring every week but one at most to be fully present -- that's
    # intentional, not a rounding accident.
    "min_window_coverage": 0.80,
    # immediate_lift_pct (measured against the trend counterfactual, not
    # the flat baseline mean) must clear this to count as an economically
    # meaningful bump, not everyday noise. 10% is well above the day-to-day
    # wobble of a stable series but low enough to catch a real minor-release
    # bump.
    "min_immediate_lift_pct": 0.10,
    # robust_z must also clear this. Two-sigma-equivalent: "notably
    # unusual" without demanding a rare, huge swing. Both this and the pct
    # threshold must pass (see _is_meaningful) so a big percentage move on
    # a tiny/noisy baseline, or a big z-score on a trivial percentage,
    # don't alone trigger a positive read.
    "min_robust_z": 2.0,
    # Fraction of the immediate lift (as an absolute amount over the trend
    # counterfactual) that must still be present in the sustained window
    # for the effect to count as SUSTAINED rather than a decaying SPIKE.
    # 0.5 = "at least half of the bump held up six weeks out."
    "sustain_fraction": 0.50,
}


class Classification(StrEnum):
    SUSTAINED = "SUSTAINED"
    SPIKE = "SPIKE"
    FLAT = "FLAT"
    INSUFFICIENT = "INSUFFICIENT"


@dataclass(frozen=True, slots=True)
class LiftResult:
    event_date: date
    metric_name: str
    baseline: float | None
    """Raw (untrended) mean of the pre-event window. Descriptive only —
    lift is measured against the trend counterfactual below, not this."""
    immediate: float | None
    sustained: float | None
    trend_pct_per_day: float | None
    """Fitted daily growth rate from the baseline trend (e.g. 0.005 =
    ~0.5%/day). None only when there wasn't enough baseline data to fit."""
    counterfactual_immediate: float | None
    """What the trend predicts for the immediate window if nothing had
    happened. This, not `baseline`, is what `immediate` is compared to."""
    counterfactual_sustained: float | None
    immediate_lift_pct: float | None
    sustained_lift_pct: float | None
    robust_z: float | None
    zero_baseline: bool
    """True when the counterfactual is zero/negative and percentage lift
    is therefore undefined (e.g. a project with a genuinely zero-download
    baseline). When True, immediate_lift_pct/sustained_lift_pct/robust_z
    are all None by construction — the classifier falls back to a
    qualitative "did it move off zero" check instead of a fabricated
    numeric stand-in, so this flag (not a sentinel value) is what carries
    the "can't compute a percentage here" signal into aggregates."""
    classification: Classification
    confounded: bool
    pre_days_available: int
    post_days_available: int
    sustain_days_available: int
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_date": self.event_date.isoformat(),
            "metric_name": self.metric_name,
            "baseline": self.baseline,
            "immediate": self.immediate,
            "sustained": self.sustained,
            "trend_pct_per_day": self.trend_pct_per_day,
            "counterfactual_immediate": self.counterfactual_immediate,
            "counterfactual_sustained": self.counterfactual_sustained,
            "immediate_lift_pct": self.immediate_lift_pct,
            "sustained_lift_pct": self.sustained_lift_pct,
            "robust_z": self.robust_z,
            "zero_baseline": self.zero_baseline,
            "classification": self.classification.value,
            "confounded": self.confounded,
            "pre_days_available": self.pre_days_available,
            "post_days_available": self.post_days_available,
            "sustain_days_available": self.sustain_days_available,
            "notes": "; ".join(self.notes),
        }


def _complete_week_points(
    series: dict[date, float], start: date, length_days: int, event_date: date
) -> tuple[list[tuple[int, float]], int, int]:
    """(day_offset_from_event, value) pairs for [start, start+length_days).

    `length_days` must be a whole number of weeks. The window is split
    into non-overlapping 7-day blocks; a block contributes its 7 points
    only if all 7 of its calendar days are present in `series`. Any 7
    consecutive calendar days contain each weekday exactly once, so this
    guarantees the returned points are never weekday-skewed by gaps, no
    matter which specific days are missing.

    Returns (points, complete_blocks, expected_blocks).
    """
    assert length_days % 7 == 0, "caller must validate week-alignment first"
    expected_blocks = length_days // 7
    points: list[tuple[int, float]] = []
    complete_blocks = 0
    for w in range(expected_blocks):
        block_start = start + timedelta(days=7 * w)
        block_dates = [block_start + timedelta(days=i) for i in range(7)]
        if all(d in series for d in block_dates):
            complete_blocks += 1
            points.extend(((d - event_date).days, series[d]) for d in block_dates)
    return points, complete_blocks, expected_blocks


def _median_absolute_deviation(values: list[float]) -> float:
    m = median(values)
    return median(abs(v - m) for v in values)


def _ols(pairs: list[tuple[float, float]]) -> tuple[float, float]:
    """Ordinary least squares slope, intercept for (x, y) pairs."""
    n = len(pairs)
    x_mean = sum(x for x, _ in pairs) / n
    y_mean = sum(y for _, y in pairs) / n
    denominator = sum((x - x_mean) ** 2 for x, _ in pairs)
    if denominator == 0:
        return 0.0, y_mean
    slope = sum((x - x_mean) * (y - y_mean) for x, y in pairs) / denominator
    intercept = y_mean - slope * x_mean
    return slope, intercept


def _fit_and_predict(
    baseline_points: list[tuple[int, float]], offsets_to_predict: list[int]
) -> tuple[dict[int, float], float | None, str, list[float]]:
    """Fit a trend on baseline (day_offset, value) points and predict the
    counterfactual value at each offset in `offsets_to_predict`.

    Prefers a log-linear fit (constant %/day growth — the usual shape of
    an adoption curve) and falls back to plain linear when the baseline
    has non-positive values (log undefined) or the log-linear
    extrapolation overflows float range.

    Returns (predicted_by_offset, trend_pct_per_day, model_name, baseline_residuals).
    """
    values = [y for _, y in baseline_points]
    if all(y > 0 for y in values):
        try:
            slope, intercept = _ols([(float(t), math.log(y)) for t, y in baseline_points])
            predicted = {t: math.exp(intercept + slope * t) for t in offsets_to_predict}
            residuals = [y - math.exp(intercept + slope * t) for t, y in baseline_points]
            log_linear_pct_per_day: float | None = math.exp(slope) - 1.0
            return predicted, log_linear_pct_per_day, "log-linear", residuals
        except OverflowError:
            pass  # extrapolation range too wide/steep for exp() -- fall back to linear

    slope, intercept = _ols([(float(t), y) for t, y in baseline_points])
    predicted = {t: intercept + slope * t for t in offsets_to_predict}
    residuals = [y - (intercept + slope * t) for t, y in baseline_points]
    baseline_mean = sum(values) / len(values)
    trend_pct_per_day = slope / baseline_mean if baseline_mean != 0 else None
    return predicted, trend_pct_per_day, "linear", residuals


def _z_score(deviation: float, mad: float) -> float | None:
    if mad == 0:
        return None
    return deviation / (_MAD_TO_STDEV * mad)


def _is_meaningful(
    lift_pct: float | None,
    robust_z: float | None,
    zero_baseline: bool,
    lift_amount: float | None,
) -> bool:
    """"Meaningful" immediate lift = economically sized AND statistically
    unusual, evaluated against the trend counterfactual. Requiring both
    keeps a big % move on a noisy, near-zero counterfactual from
    qualifying alone, and keeps a high z-score on a series with tiny
    natural variance from qualifying on a practically trivial move alone.
    """
    if zero_baseline:
        # Percentage lift is undefined against a ~zero counterfactual, and
        # z-score along with it. The qualitative move is the only signal
        # available: going from ~nothing to something is real; staying at
        # ~nothing is not.
        return lift_amount is not None and lift_amount > 0
    if lift_pct is None:
        return False
    if robust_z is None:
        # Baseline had zero residual variance around its own trend (a
        # perfect or near-perfect fit) -- z is undefined, so the
        # percentage threshold alone has to carry the decision.
        return lift_pct >= THRESHOLDS["min_immediate_lift_pct"]
    return (
        lift_pct >= THRESHOLDS["min_immediate_lift_pct"]
        and robust_z >= THRESHOLDS["min_robust_z"]
    )


def compute_lift(
    series: dict[date, float],
    event_date: date,
    *,
    pre: int = 14,
    post: int = 14,
    sustain_start: int = 15,
    sustain_end: int = 42,
    other_event_dates: Iterable[date] = (),
    metric_name: str = "",
) -> LiftResult:
    """Pure computation over an in-memory series. See module docstring."""
    sustain_length = sustain_end - sustain_start + 1
    if pre % 7 != 0 or post % 7 != 0 or sustain_length % 7 != 0:
        raise ValueError(
            "pre, post, and (sustain_end - sustain_start + 1) must each be a whole "
            "number of weeks (multiples of 7) -- PyPI/star data is weekday-skewed, "
            "so a window that isn't a whole number of weeks biases the mean toward "
            f"whichever weekdays happen to be included (got pre={pre}, post={post}, "
            f"sustain_length={sustain_length})"
        )

    notes: list[str] = []

    baseline_start = event_date - timedelta(days=pre)
    immediate_start = event_date
    sustained_start = event_date + timedelta(days=sustain_start)

    baseline_points, baseline_complete, baseline_expected = _complete_week_points(
        series, baseline_start, pre, event_date
    )
    immediate_points, immediate_complete, immediate_expected = _complete_week_points(
        series, immediate_start, post, event_date
    )
    sustained_points, sustained_complete, sustained_expected = _complete_week_points(
        series, sustained_start, sustain_length, event_date
    )

    baseline_ok = baseline_complete / baseline_expected >= THRESHOLDS["min_window_coverage"]
    immediate_ok = immediate_complete / immediate_expected >= THRESHOLDS["min_window_coverage"]
    sustained_ok = sustained_complete / sustained_expected >= THRESHOLDS["min_window_coverage"]

    baseline_mean = (
        sum(y for _, y in baseline_points) / len(baseline_points) if baseline_points else None
    )
    immediate_mean = (
        sum(y for _, y in immediate_points) / len(immediate_points) if immediate_points else None
    )
    sustained_mean = (
        sum(y for _, y in sustained_points) / len(sustained_points) if sustained_points else None
    )

    sustained_end_date = event_date + timedelta(days=sustain_end)
    confounded = any(
        d != event_date and baseline_start <= d <= sustained_end_date for d in other_event_dates
    )
    if confounded:
        notes.append("another event falls within this event's analysis window")

    if not baseline_ok or not immediate_ok:
        notes.append(
            f"insufficient data: baseline {baseline_complete}/{baseline_expected} complete "
            f"weeks, immediate {immediate_complete}/{immediate_expected} complete weeks"
        )
        return LiftResult(
            event_date=event_date,
            metric_name=metric_name,
            baseline=baseline_mean,
            immediate=immediate_mean,
            sustained=sustained_mean,
            trend_pct_per_day=None,
            counterfactual_immediate=None,
            counterfactual_sustained=None,
            immediate_lift_pct=None,
            sustained_lift_pct=None,
            robust_z=None,
            zero_baseline=False,
            classification=Classification.INSUFFICIENT,
            confounded=confounded,
            pre_days_available=len(baseline_points),
            post_days_available=len(immediate_points),
            sustain_days_available=len(sustained_points),
            notes=notes,
        )

    assert immediate_mean is not None  # immediate_ok implies immediate_points is non-empty

    offsets_to_predict = [t for t, _ in immediate_points] + [t for t, _ in sustained_points]
    predicted, trend_pct_per_day, trend_model, residuals = _fit_and_predict(
        baseline_points, offsets_to_predict
    )
    if trend_model == "linear" and any(y <= 0 for _, y in baseline_points):
        notes.append("baseline has non-positive values; used a linear (not log-linear) trend fit")
    elif trend_model == "linear":
        notes.append("log-linear extrapolation overflowed; fell back to a linear trend fit")

    counterfactual_immediate = sum(predicted[t] for t, _ in immediate_points) / len(
        immediate_points
    )
    counterfactual_sustained = (
        sum(predicted[t] for t, _ in sustained_points) / len(sustained_points)
        if sustained_points
        else None
    )

    zero_baseline = counterfactual_immediate <= 0
    if zero_baseline:
        notes.append("trend counterfactual is zero/negative; percentage lift is undefined")

    immediate_lift_pct = (
        (immediate_mean - counterfactual_immediate) / counterfactual_immediate
        if not zero_baseline
        else None
    )
    sustained_lift_pct = (
        (sustained_mean - counterfactual_sustained) / counterfactual_sustained
        if not zero_baseline
        and sustained_mean is not None
        and counterfactual_sustained is not None
        and counterfactual_sustained > 0
        else None
    )

    residual_mad = _median_absolute_deviation(residuals) if residuals else 0.0
    immediate_lift_amount = immediate_mean - counterfactual_immediate
    robust_z = None if zero_baseline else _z_score(immediate_lift_amount, residual_mad)
    if not zero_baseline and robust_z is None:
        notes.append("baseline has zero residual variance around its trend; z-score undefined")

    meaningful = _is_meaningful(immediate_lift_pct, robust_z, zero_baseline, immediate_lift_amount)

    if not sustained_ok:
        # We can judge the immediate effect but not whether it held: the
        # sustain window isn't sufficiently collected yet, most commonly
        # because the event is recent. Rather than guess SPIKE vs
        # SUSTAINED, call it INSUFFICIENT -- but keep the immediate
        # numbers so the caller can still see the bump.
        notes.append(
            f"sustained window has only {sustained_complete}/{sustained_expected} complete "
            "weeks of data; cannot judge persistence"
        )
        classification = Classification.INSUFFICIENT
    elif not meaningful:
        classification = Classification.FLAT
    else:
        sustained_lift_amount = (
            sustained_mean - counterfactual_sustained
            if sustained_mean is not None and counterfactual_sustained is not None
            else None
        )
        retained_fraction = (
            sustained_lift_amount / immediate_lift_amount
            if sustained_lift_amount is not None and immediate_lift_amount != 0
            else None
        )
        if retained_fraction is not None and retained_fraction >= THRESHOLDS["sustain_fraction"]:
            classification = Classification.SUSTAINED
        else:
            classification = Classification.SPIKE

    return LiftResult(
        event_date=event_date,
        metric_name=metric_name,
        baseline=baseline_mean,
        immediate=immediate_mean,
        sustained=sustained_mean,
        trend_pct_per_day=trend_pct_per_day,
        counterfactual_immediate=counterfactual_immediate,
        counterfactual_sustained=counterfactual_sustained,
        immediate_lift_pct=immediate_lift_pct,
        sustained_lift_pct=sustained_lift_pct,
        robust_z=robust_z,
        zero_baseline=zero_baseline,
        classification=classification,
        confounded=confounded,
        pre_days_available=len(baseline_points),
        post_days_available=len(immediate_points),
        sustain_days_available=len(sustained_points),
        notes=notes,
    )


def lift(
    store: Any,
    project: str,
    metric: str,
    event_date: date,
    *,
    pre: int = 14,
    post: int = 14,
    sustain_start: int = 15,
    sustain_end: int = 42,
) -> LiftResult:
    """Store-backed convenience wrapper around `compute_lift`.

    `metric` is a "source.name" pair, e.g. "pypi.downloads" or
    "github.stars" — matches the `metric` table's (source, name) key
    directly, so it's unambiguous when a project has more than one series
    under the same name (e.g. pypi and npm downloads side by side).
    """
    source, _, name = metric.partition(".")
    if not name:
        raise ValueError(f"metric must be 'source.name' (e.g. 'pypi.downloads'), got {metric!r}")

    series = store.get_metric_series(project, source, name)
    other_event_dates = [e.date for e in store.get_events(project) if e.date != event_date]
    return compute_lift(
        series,
        event_date,
        pre=pre,
        post=post,
        sustain_start=sustain_start,
        sustain_end=sustain_end,
        other_event_dates=other_event_dates,
        metric_name=metric,
    )
