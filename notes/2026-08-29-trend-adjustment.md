# 2026-08-29 — trend adjustment: the flat-baseline bug

Caught in review before the module was used for real, but worth recording
because it's the kind of thing that's easy to reintroduce.

## The bug

`compute_lift` compared `immediate`/`sustained` means to a flat mean of the
pre-event window. A project growing organically at, say, 5%/week has every
post-event window sitting above every pre-event window *regardless of the
event* — the baseline is systematically lower than the post window for a
reason that has nothing to do with what happened on the event date. Run
against a genuinely growing real-world project, nearly every release
comes back SUSTAINED. That's measuring growth, not attribution — exactly
the failure mode this tool exists to avoid.

## The fix

`compute_lift` now fits a trend on the baseline window and extrapolates it
forward as the counterfactual — what the metric would have looked like if
nothing had happened — and measures lift against *that*, not the flat
mean. Prefers a log-linear fit (assumes constant %/day growth, which is
how adoption curves actually behave) and falls back to plain linear only
when the baseline has non-positive values. The fitted rate is exposed as
`trend_pct_per_day` specifically so it's visible whenever the correction
is doing real work — a report that shows a big `trend_pct_per_day` next to
a FLAT classification is exactly the "would have looked like lift under
the old logic" case made visible.

`test_organic_growth_with_no_event_effect_is_flat_not_sustained` in
`tests/test_analysis.py` is the direct regression test: a smoothly growing
series with literally no event effect must classify FLAT.
`test_real_lift_on_top_of_growth_trend_is_still_detected` checks the fix
doesn't overcorrect — a real step-change riding on top of organic growth
still reads as SUSTAINED.

**Not done yet, flagged as the stronger version for later:**
difference-in-differences against a matched control set of projects with
no event in the same window. That also nets out ecosystem-wide effects
(holidays, PyPI outages) that a single-project trend fit can't see, and is
what would make the eventual cross-project `study` output defensible as
more than "this one project's own history." The trend fit gets most of
the value for a fraction of the implementation cost; DiD is the follow-up.

## Three related tightenings, same session

- `min_window_coverage` raised from 0.60 to 0.80 (`THRESHOLDS` in
  `analysis.py`) — 8/14 days deciding a baseline was too loose.
- Coverage and the underlying means are now computed on **whole weeks**,
  not raw days: a window is split into 7-day blocks, and a block only
  counts if all 7 of its days are present. PyPI/star traffic is
  weekday-skewed (CI runs weekdays, humans mostly don't `pip install` on
  Sundays), so a window missing three Tuesdays reads differently from one
  missing three Sundays at identical raw-day coverage — whole-week
  filtering makes those two cases behave identically instead. `pre`,
  `post`, and the sustain window length must each be a multiple of 7 now;
  `compute_lift` raises `ValueError` otherwise.
- The old zero-baseline handling returned a fabricated large `robust_z`
  sentinel (`min_robust_z * 10`, signed) so the classifier had *something*
  to compare against a zero MAD. That value would have flowed straight
  into `study`'s CSV output and silently poisoned any aggregate (mean,
  percentile, whatever) computed over `robust_z` across projects. Replaced
  with an explicit `zero_baseline: bool` field — `robust_z` is `None` when
  it's genuinely undefined, and the classifier (`_is_meaningful`) reads
  the flag directly instead of inferring it from a suspiciously large
  number.

## Two more caveats for the eventual writeup (not bugs, known tradeoffs)

**Extrapolation confidence decays with distance from the fit window.** The
trend is fit on 14-28 days of baseline (2-4 weeks, whatever `pre` is) and
then extrapolated up to 42 days *forward* — further out than the window it
was estimated on. `immediate_lift_pct`/`robust_z` (days 0-13) rest on a
much shorter extrapolation than `sustained_lift_pct` (days 15-42), so the
two are not equally trustworthy even though they're reported side by side
with the same precision. Any cross-project aggregation should weight or
caveat `sustained_lift_pct` accordingly rather than treating a SUSTAINED
classification as exactly as solid as a SPIKE/FLAT call, which only
depends on the shorter, closer extrapolation.

**Trend adjustment eats its own tail on fast-shipping projects.** If a
release causes real, durable growth, that new higher growth rate becomes
part of the baseline trend fitted for the *next* release 2-6 weeks later —
the effect gets folded into "the trend" instead of staying attributed to
the release that caused it. Consecutive releases on a fast-shipping
project will each systematically read smaller than their true effect,
worst for releases close together. This is the correct tradeoff against
the alternative (flat-baseline, which overattributes ambient growth to
every release, the bug fixed earlier today) — but it's a real, opposite-
direction bias, not a free lunch, and the writeup needs to name it instead
of presenting `sustained_lift_pct` as a clean per-release effect size on
projects that ship frequently.

## Interpretive caveat that belongs in the eventual writeup

A release causes some install traffic mechanically, independent of any
human deciding to adopt the tool: CI pins get bumped, Dependabot opens a
PR and CI installs the new pin, package mirrors resync. None of that is a
person reading a changelog and choosing to try the library. `hirogari`
has no way to separate mechanical install traffic from human-driven
installs using public download-count data alone — a spike is a spike
either way.

This means `release` events and `post`/`docs` events are not measuring
the same construct. A release's lift is contaminated by a predictable
mechanical floor that scales with the size of the dependent ecosystem
(more downstream projects pinning it -> more mechanical traffic on every
release, independent of adoption). A HN/Reddit post or a docs change has
no equivalent mechanical trigger — its lift, if any, is closer to pure
human signal. Cross-project comparisons (the `study` command) should not
pool `release` lift and `post` lift as if they were the same measurement,
and any writeup needs to say this explicitly rather than let a reader
assume "lift" means the same thing across event kinds.
