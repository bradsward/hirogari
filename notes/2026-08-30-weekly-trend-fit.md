# 2026-08-30 — weekly trend fit, and what DiD found underneath it

Two changes today, discovered in sequence by actually using the DiD
feature (`notes/2026-08-29-...` requested it as future work; today it got
built) on real data instead of just synthetic tests. Recording both
because the second one only became visible *because of* the first.

## Bug: the trend fit was contaminated by weekday/weekend noise

`_fit_and_predict` fit its log-linear/linear slope on individual daily
`(offset, value)` points. Applying `--did` to a real finding
(`pytest-dev/pytest` 9.0.3, previously the cleanest SUSTAINED result in
the cross-project study) surfaced something odd: three completely
unrelated control projects (certifi, flask, cryptography) all showed a
suspiciously similar `trend_pct_per_day` in the same calendar window —
around -1.7% to -2.2%/day, which compounds to roughly *halving* over the
42-day sustain horizon. No real, popular, actively-used package's
downloads halve every six weeks in steady state. Four unrelated projects
independently doing that at the same time is not four coincidences.

Traced it to the exact two calendar weekends inside that baseline window
(2026-03-21/22 and 2026-03-28/29 for that particular event date) —
PyPI/download traffic drops sharply on weekends (already known and
handled at the *coverage* level via whole-week filtering), but the
*trend fit itself* still regressed on raw daily points, and the weekend
dips in this window weren't perfectly symmetric between the two weeks
(real noise, not a clean repeating pattern). A 14-point daily regression
is sensitive to exactly that kind of noise; because every project shares
the same calendar, the noise is *correlated across unrelated projects* —
which looks exactly like a shared trend and isn't one.

Fix: fit the slope on weekly-aggregated means (`_weekly_means` — group
the already-complete-week daily points into 7-point chunks and average
each into one point) instead of the daily points. Residuals for the
z-score still use the daily points against the resulting trend line, so
that sample size is unaffected — only the slope-fitting input changed.
`test_trend_fit_ignores_compositional_weekday_noise_with_flat_weekly_means`
in `tests/test_analysis.py` is the direct regression test: a baseline
where every week's own mean is exactly flat but the weekend dip deepens
toward the event (compensated by higher weekdays, so weekly means don't
move) — a daily-point fit is fooled by the larger weekday subpopulation's
drift, weekly aggregation isn't.

Real effect of the fix: the four projects' `trend_pct_per_day` dropped
from -1.67%..-2.22%/day to -0.61%..-0.95%/day — roughly a 2-3x reduction,
much more plausible as a real short-window fluctuation than a
compounding-to-halving artifact. The cross-project study was re-run
(`study/results.csv`) — one of the two prior SUSTAINED findings
(`psf/requests` v2.33.0) flipped to FLAT under the corrected fit; the
other (`pytest-dev/pytest` 9.0.3) held.

## What DiD then showed about the one finding that survived

The fixed trend fit still left all four projects with *similar-direction*
small negative trends in that window — smaller, but still shared. Running
`--did` on the surviving SUSTAINED finding with the actual real control
pool (the other studied projects that had no event of their own in that
window and enough data — certifi, flask, cryptography qualified):

| | immediate | sustained |
|---|---|---|
| pytest's own trend-adjusted lift | +23.7% | +58.3% |
| control average over the same calendar window | +21.3% | +51.5% |
| **DiD-adjusted (pytest minus controls)** | **+2.4%** | **+6.8%** |

pytest's own reading still clears both thresholds (`robust_z` 2.21,
`immediate_lift_pct` 23.7%) and still classifies SUSTAINED — `classification`
is deliberately *not* recomputed from the DiD numbers, it's still exactly
what `compute_lift` says on its own. But the controls moved almost
exactly as much as pytest did, over the identical calendar dates, with no
release of their own. That's not further trend-fit noise (the fit is
already fixed) — three unrelated projects with no event genuinely tracked
a comparably large move over those same ~8 weeks. Whatever caused it, it
wasn't specific to pytest 9.0.3.

**Net result: zero of the 787 real event x metric rows in this study
represent a lift that's both individually significant *and* survives
being checked against what a comparable project with no event did over
the identical calendar window.** That is a genuinely different, more
defensible conclusion than "we found one clean SUSTAINED result" — and
it's the conclusion `study/FINDINGS.md` and the README now report.

`study/results.csv` was regenerated with `--did`, so every row now
carries `control_projects_used` / `did_immediate_lift_pct` /
`did_sustained_lift_pct` alongside the original trend-adjusted fields —
this is the single canonical output file now (the earlier
non-DiD-augmented `results.csv` and a separately-named DiD file were
merged into one; DiD columns are additive, nothing about the original
fields changed by including them).
