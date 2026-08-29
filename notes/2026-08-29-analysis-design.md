# 2026-08-29 — analysis module design decisions

Three things in `compute_lift`/`lift` weren't fully pinned down by the spec.
Recording the reasoning so they're easy to revisit.

## metric identifier format

The spec's `lift(project, metric, event_date, ...)` signature takes a single
`metric` string, but the `metric` table keys on `(source, name)` — a project
can have both `pypi.downloads` and `npm.downloads` at once. Asked the user;
answer was "whichever is more robust/accurate." Went with a `"source.name"`
string (`"pypi.downloads"`, `"github.stars"`) since it maps 1:1 onto the
table's primary key with no guessing logic and no separate flag to keep in
sync with `--metric`.

## zero / flat baseline breaks percentage lift and MAD z-score

`immediate_lift_pct = (immediate - baseline) / baseline` divides by zero
whenever baseline is 0 (a brand-new package with a slow start, or an event
early enough that the pre-window is literally empty of downloads). Same
problem hits `robust_z` when the baseline MAD is 0 — happens more than
expected, e.g. flat-zero baselines but also any baseline window with an
odd-length run of identical values.

Fix: `immediate_lift_pct`/`sustained_lift_pct` are `None` when the (now
trend-extrapolated) counterfactual is 0, division being genuinely
undefined. `robust_z` is also `None` in that case — **superseded**: this
originally fell back to a fixed large signed sentinel instead of `None`,
which turned out to leak into `study`'s CSV and poison aggregates; see
`2026-08-29-trend-adjustment.md` for the fix (an explicit `zero_baseline:
bool` flag that the classifier reads directly, no sentinel).

The SUSTAINED/SPIKE retained-fraction check works off absolute lift
*amounts* (`immediate - counterfactual_immediate`,
`sustained - counterfactual_sustained`) rather than the percentages,
specifically so it keeps working when the counterfactual is 0 and the
percentages are undefined.

## sustained window not yet collected != FLAT

An event from last week can't be judged SUSTAINED vs SPIKE — days 15-42
post-event don't exist yet. Initially considered classifying on immediate
data alone in that case, but that conflates "we don't know yet" with "we
know it didn't hold" (FLAT) or "we know it decayed" (SPIKE), both of which
imply data that doesn't exist. Instead: insufficient sustain-window
coverage always classifies as INSUFFICIENT, but `baseline`/`immediate`
values and `immediate_lift_pct` are still populated (only `sustained` and
`sustained_lift_pct` are `None`) — see `test_event_near_end_of_data_is_
insufficient_but_keeps_immediate_numbers` in `tests/test_analysis.py`.
This means `study` will mark a lot of recent releases INSUFFICIENT until
more data accumulates; that's intentional, not a bug to "fix" later by
loosening the coverage threshold.
