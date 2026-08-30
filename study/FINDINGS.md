# Cross-project study — real results

Run against the 10 real projects in [projects.txt](projects.txt), using
`hirogari study study/projects.txt --did --csv study/results.csv` with no
`GITHUB_TOKEN` set (so GitHub stars/traffic were skipped for every
project). Only `pypi.downloads` lift is in this run. `--did` nets every
project's lift against every *other* studied project as a
difference-in-differences control — see
[SPEC.md](../SPEC.md#difference-in-differences) and
[notes/2026-08-30-weekly-trend-fit.md](../notes/2026-08-30-weekly-trend-fit.md).
Full results: [results.csv](results.csv), 787 rows.

**This file was rewritten after two same-day fixes changed the numbers.**
The first run found "2 SUSTAINED, one clean" — see the git history of
this file for that version. A bug in the trend fit (contaminated by
weekday/weekend noise) and, more importantly, actually applying the new
`--did` feature to that "clean" result, changed the conclusion. The
current numbers below are the corrected ones.

## Two projects contributed zero events

`certifi/python-certifi` and `pyca/cryptography` both returned 0 releases
from GitHub's releases API — verified directly against the API, not a
`hirogari` bug. Both tag versions without creating GitHub Release
objects. `collect_releases` now has a tags-based fallback for this
(gated on `GITHUB_TOKEN`, not available in this environment — see
[notes/2026-08-29-first-cross-project-study.md](../notes/2026-08-29-first-cross-project-study.md)),
so this run still shows zero events for both. Useful side effect: with
no events of their own, both are *always* eligible `--did` controls for
every other project's window in this study.

## Aggregate (787 rows)

| classification | count | share |
|---|---|---|
| INSUFFICIENT | 750 | 95% |
| FLAT | 36 | 5% |
| SUSTAINED | 1 | 0.1% |
| SPIKE | 0 | 0% |

84% of all 787 rows were flagged `confounded`. The INSUFFICIENT rate
matches the earlier single-project validation run almost exactly (95%
there too) — pypistats' ~180-day history ceiling dominates it regardless
of which project it's run against.

37 rows had at least one usable `--did` control (enough of the rest of
the study pool had clean, sufficient data over that specific calendar
window). Every project ends up in this study as *both* a treatment (for
its own events) and a potential control (for every other project's
events) — the 8 with releases and the 2 without both contribute either
way.

## The one SUSTAINED result, and what DiD did to it

**`pytest-dev/pytest` 9.0.3** (2026-04-07): not confounded, immediate
lift 23.7%, sustained lift 58.3%, `robust_z` 2.21 — clears both
thresholds on its own, which is why it's still classified SUSTAINED
(`classification` is never recomputed from the DiD numbers; it's exactly
what the project's own trend-adjusted reading says). Three other studied
projects qualified as `--did` controls for this exact window — no event
of their own, sufficient data: `certifi/python-certifi`, `pallets/flask`,
`pyca/cryptography`.

| | immediate | sustained |
|---|---|---|
| pytest's own lift | +23.7% | +58.3% |
| control average, same calendar window | +21.3% | +51.5% |
| **DiD-adjusted** | **+2.4%** | **+6.8%** |

The three controls — a certs bundle, a web framework, and a crypto
library, sharing nothing with pytest except being on PyPI — moved almost
exactly as much as pytest did, over the identical calendar dates, with no
release of their own. Whatever happened in that window, it wasn't
specific to pytest 9.0.3. Once netted against what comparable projects
did with no event of their own, there's effectively nothing left.

**Net conclusion: zero of the 787 rows in this study represent a lift
that is both individually significant *and* survives being checked
against a real, no-event control over the same calendar window.** That's
a materially different (and more defensible) headline than "found one
clean result," and it's what actually happened when the stronger version
of the methodology — the one flagged as future work when this project
started — got built and pointed at the one finding that looked cleanest
under the weaker version.

## What this does and doesn't support

It supports: the full pipeline — collection, trend-adjusted lift,
whole-week windowing, and now DiD — runs end-to-end against real, varied
public projects and produces a specific, checkable number for every
event, not a vague impression. It also supports a structural point: a
single-project trend counterfactual is not enough on its own to call a
result clean, even when it clears every threshold by a comfortable
margin (z=2.21 is not marginal) — this run is a concrete, real example of
exactly the failure mode difference-in-differences exists to catch,
catching it.

It does not support any claim like "releases cause N% average growth,"
now more than ever — n=1 candidate finding out of 787 rows, and that one
didn't survive its own control check. Release events also still carry
the unremovable mechanical-install-traffic caveat from
[notes/2026-08-29-trend-adjustment.md](../notes/2026-08-29-trend-adjustment.md)
regardless of any of the above.
