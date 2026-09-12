# Cross-project study — real results

Run against the 20 real projects in [projects.txt](projects.txt), using
`hirogari study study/projects.txt --did --csv study/results.csv` with a
real `GITHUB_TOKEN` (raises the rate limit, and was expected to unlock
GitHub stars — see below for why it didn't). `--did` nets every
project's lift against every *other* studied project as a
difference-in-differences control, filtered to a similar traffic scale
(`THRESHOLDS["max_control_baseline_ratio"]`) — see
[SPEC.md](../SPEC.md#difference-in-differences). Full results:
[results.csv](results.csv), 2,322 rows.

**This file has been rewritten twice.** The first version (10 projects,
no token, 787 rows) found "2 SUSTAINED, one clean." A trend-fit bug and
then a real `--did` run revised that to "1 SUSTAINED, and it doesn't
survive DiD either" — see the git history and
[notes/2026-08-30-weekly-trend-fit.md](../notes/2026-08-30-weekly-trend-fit.md).
This version (20 projects, real token, 2,322 rows) has more data and a
more interesting — and more honestly caveated — answer. Read this one.

## GitHub stars: still unavailable, for a stronger reason than last time

A real token was expected to unlock stars data. It didn't — GitHub
restricts the stargazers listing endpoint to repo admins/collaborators
as of July 2026 (confirmed against their own current docs), which no
token fixes for a project you don't administer. This run only has
`pypi.downloads`. See
[notes/2026-09-12-github-stars-locked-down.md](../notes/2026-09-12-github-stars-locked-down.md).

The tags-based release fallback, on the other hand, *did* get its first
live run today: `certifi/python-certifi` (66 tags) and
`pyca/cryptography` (160 tags) both resolved real release history for
the first time, exactly as designed.

## Aggregate (2,322 rows, 20 projects)

| classification | count | share |
|---|---|---|
| INSUFFICIENT | 2,226 | 95.9% |
| FLAT | 90 | 3.9% |
| SUSTAINED | 5 | 0.2% |
| SPIKE | 1 | 0.04% |

85% of all rows were flagged `confounded`. Both rates are consistent
with every earlier run at any project-count — pypistats' ~180-day
history ceiling and high release cadence dominate regardless of how many
or which projects are in the pool. 96 rows (4%) had at least one
DiD control that passed the scale-similarity filter and had sufficient,
unconfounded data over that exact calendar window.

## The 6 non-FLAT findings, and what DiD did to each

| project | event | own immediate | own sustained | confounded | DiD immediate | DiD sustained |
|---|---|---|---|---|---|---|
| pytest-dev/pytest | 9.0.3 | +23.7% | +58.3% | no | +0.3% | +11.5% |
| pyca/cryptography | 48.0.0 | +12.9% | +31.6% | **yes** | **-8.9%** | **-30.1%** |
| pydantic/pydantic | v2.13.4 | +34.0% | +66.5% | yes | +9.4% | +4.2% |
| pypa/pip | 26.1 | +26.7% | +19.7% | yes | +36.4% | +32.5% |
| pypa/pip | **26.1.2** | +38.7% | +43.7% | **no** | **+20.6%** | +2.3% |
| pypa/pip | 26.2 (SPIKE) | +43.9% | -3.2% | yes | +41.6% | +21.9% |

Three of six wash out to near-zero or reverse sign once checked against
real control projects over the same calendar window — pytest, pydantic,
and notably **cryptography flips negative**: its "SUSTAINED" reading
undersold what comparable projects did over that same window, so once
corrected it's actually a *relative underperformance*, not a lift.

**`pypa/pip` is the standout, and it's genuinely interesting.** All
three of its non-FLAT events retain a large DiD-adjusted immediate lift
— including 26.1.2, the only one of the six that isn't confounded by a
neighboring release. That's the single strongest result in this entire
study: individually significant on its own (`robust_z` 2.30), not
confounded, and still +20.6% after netting out eight real, similarly-
scaled, no-event control projects over the identical window. Its
sustained persistence does *not* hold up the same way (+2.3% DiD,
against an own reading of +43.7% — the multi-week "SUSTAINED"
classification was mostly shared with the ecosystem; only the immediate
bump has real pip-specific signal).

**Caveat that matters here more than anywhere else in this project:**
`pip` is the one package where the mechanical-install-traffic caveat
(`notes/2026-08-29-trend-adjustment.md`) is closer to the whole story
than a footnote. `pip install --upgrade pip` is a near-universal
first line in CI configs, Docker images, and tutorials — run
automatically, constantly, by tooling, with no human ever deciding
"I should try this pip release." A new pip version very plausibly
generates a real, immediate download spike through pure mechanical
self-upgrade behavior, which is a completely different phenomenon from
a developer reading a changelog and adopting something. This result is
the most statistically defensible one in the study and simultaneously
the one where "adoption" is the least appropriate word for what's being
measured.

## What this run does and doesn't support

It supports: the full pipeline — collection (now including the live
tags fallback), trend-adjusted lift, whole-week windowing, and
scale-matched DiD — runs end-to-end against 20 real, structurally
different public projects and produces a specific, checkable,
individually-inspectable number for every event. It also supports the
same structural point as the smaller run, with a bigger sample behind
it: most single-project "clean" findings do not survive being checked
against real no-event controls, and the ones that plausibly do (pip)
come with their own, different attribution problem once you look closely
at what actually drives that package's traffic.

It does not support any claim like "releases cause N% average growth" —
if anything, the honest reading of this run is closer to "releases
rarely produce a lift that's both statistically real and clearly
attributable to that release specifically, and the one case that gets
closest is confounded by mechanical CI traffic rather than human
adoption." That is a materially different, and more defensible,
conclusion than either of the two prior versions of this file reached —
which is the point of running the check at increasing rigor rather than
stopping at the first version that looked clean.
