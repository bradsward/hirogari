# First cross-project study — real results

Run 2026-08-29 against the 10 real projects in [projects.txt](projects.txt),
using `hirogari study study/projects.txt --csv study/results.csv` with no
`GITHUB_TOKEN` set (so GitHub stars and traffic were skipped for every
project — see `notes/2026-08-29-window-vs-history-length.md` on why stars
now requires auth). Only `pypi.downloads` lift is in this run. Full
results: [results.csv](results.csv), 787 rows.

## Two projects contributed zero events

`certifi/python-certifi` and `pyca/cryptography` both returned 0 releases
from GitHub's releases API — verified directly against the API, not a
`hirogari` bug. Both projects tag versions without creating GitHub
Release objects. This is a real blind spot in the `release`-event source:
`hirogari events` only sees projects that use GitHub's Releases feature,
not projects that only tag. A future source could fall back to git tags
when releases are empty; not built yet.

## Aggregate, the other 8 projects (787 rows)

| classification | count | share |
|---|---|---|
| INSUFFICIENT | 750 | 95% |
| FLAT | 35 | 4% |
| SUSTAINED | 2 | 0.3% |
| SPIKE | 0 | 0% |

84% of all 787 rows were flagged `confounded`. Both numbers land close to
the single-project validation run in `notes/2026-08-29-window-vs-history-length.md`
(95% INSUFFICIENT there too) — pypistats' ~180-day history ceiling
dominates the INSUFFICIENT rate regardless of which project it's run
against, exactly as that earlier note predicted.

Per-project breakdown:

| project | events | INSUFFICIENT | FLAT | SUSTAINED |
|---|---|---|---|---|
| tiangolo/fastapi | 300 | 284 | 16 | 0 |
| sqlalchemy/sqlalchemy | 193 | 188 | 5 | 0 |
| pytest-dev/pytest | 84 | 81 | 2 | 1 |
| python-pillow/Pillow | 65 | 63 | 2 | 0 |
| urllib3/urllib3 | 58 | 57 | 1 | 0 |
| pallets/flask | 38 | 38 | 0 | 0 |
| pallets/click | 30 | 25 | 5 | 0 |
| psf/requests | 19 | 14 | 4 | 1 |

## The two SUSTAINED results

**`pytest-dev/pytest` 9.0.3** (released 2026-04-07) — the cleanest result
in the whole run: **not confounded**, immediate lift 45.7%, sustained
lift 133.6%, `robust_z` 3.06 (baseline ~19.6M/day -> immediate ~22.2M/day
-> sustained ~24.8M/day). This is the one row in this study that the
methodology can actually stand behind as "this release coincided with a
durable, statistically unusual jump in downloads, with no other release
in the window to confuse the attribution."

**`psf/requests` v2.33.0** (released 2026-03-25) — immediate lift 17.5%,
sustained lift 35.0%, `robust_z` 2.16, but **`confounded = True`**: another
event falls inside this release's analysis window, so the lift can't be
cleanly attributed to v2.33.0 alone versus whatever else shipped nearby.
Directionally interesting, not a clean claim.

Every other evaluable row across all 8 projects was FLAT — including
several with a large-looking `immediate_lift_pct` that didn't clear
`robust_z >= 2.0` against that project's own noise, the same AND-gate
behavior documented in the single-project validation run.

## What this run does and doesn't support

It supports: the pipeline runs end-to-end against real, varied public
projects without crashing or needing manual intervention; the
trend-adjusted, week-aligned, dual-threshold methodology produces a small
number of specific, defensible positive findings rather than flagging
lift on every release (contrast with the flat-baseline bug fixed earlier
the same day, which would have over-called most of these 787 rows).

It does not support any claim like "releases cause N% average growth" —
n=2 positive findings out of 787 rows is not a statistical claim, this
is a single run with no repeated sampling, and (per
`notes/2026-08-29-trend-adjustment.md`) release events carry an
unremovable mechanical-install-traffic component that post/docs events
don't. Difference-in-differences against matched control projects
(documented as future work in that same note) is what would be needed
before this became a defensible aggregate claim rather than a
per-release, per-project observation.
