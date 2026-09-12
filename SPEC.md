# hirogari — spec

広がり (hirogari) — spread, diffusion. How far something traveled, not how
much of it there is. That's the thing this tool measures.

This is the living spec. Implementation decisions not fully pinned down
here, and the reasoning behind them, are logged in `notes/` as they're
made — this file states what the tool should do; `notes/` explains why a
particular choice was made where the spec left room.

## The problem

Developer-tool companies acquire users through GitHub repos, docs pages,
package registries, and forum posts. None of that shows up in normal
marketing analytics, because the buyer is an engineer who never fills out
a form. The path is: read something -> `pip install` -> hit the API ->
pay, weeks later.

`hirogari` measures the front of that path using only public data. It
answers one question: which releases, docs changes, and posts actually
moved adoption, and did the lift last?

## Scope

`hirogari` is a measurement tool for public open-source adoption signals.
It collects, stores, and analyzes.

`hirogari` is NOT an analytics SDK, a tracking pixel, a dashboard service,
or anything that touches private user data. It never requires a login to
produce useful output.

## Why this exists

This project is a credibility artifact for a specific claim: that its author can
instrument and measure a developer-led funnel with real code and defensible
methodology. The audience is a hiring manager or founder at an AI infrastructure
or developer-tools company who needs someone to own growth where the buyer is an
engineer and the funnel runs through repos, docs, and package registries instead
of forms and ad platforms. Every scope decision should serve that. Methodological
rigor beats feature count: a tool that measures three things correctly and says
plainly what it cannot conclude is worth more here than one that measures ten
things with hand-wavy attribution. The cross-project study output is the point
and the code is the means, so when the two compete, favor whatever makes the
published findings more trustworthy. Do not add dashboards, web UIs, integrations
with commercial analytics platforms, or ML models. Do not expand into private or
authenticated data sources beyond the optional GitHub traffic API. If a proposed
feature would not change what the study can honestly conclude, it does not belong
in this repo.

Consistent with that: this repo does not name specific companies, or hold
up any specific real project as a target or case study. Examples use
placeholder names (`acme/widget`); real-world checks (e.g. validating
event survival rate against actual release history) are run against real
public data but reported without naming which project was used.

## Constraints

- Python 3.11+
- Zero runtime dependencies. stdlib only: `urllib.request`, `sqlite3`,
  `statistics`, `json`, `argparse`, `datetime`, `csv`.
- Dev dependencies only: `pytest`, `ruff`, `mypy`
- `src/hirogari/` layout, `pyproject.toml`, Apache-2.0 license
- Type-annotated throughout, must pass `mypy --strict src/`
- Tests must never hit the network. Use recorded JSON fixtures in
  `tests/fixtures/`.

## Data sources

Each implemented as a module in `src/hirogari/sources/` behind a common
interface.

1. **PyPI downloads** —
   `https://pypistats.org/api/packages/{package}/overall`. Daily download
   counts, roughly 180 days of history. Use `category:
   "without_mirrors"`. No auth.
2. **GitHub releases** —
   `https://api.github.com/repos/{owner}/{repo}/releases`. Tag name,
   publish date, body. These become events. Paginated.
3. **GitHub stars over time** —
   `https://api.github.com/repos/{owner}/{repo}/stargazers` with header
   `Accept: application/vnd.github.star+json` to get `starred_at`.
   Paginated, 100/page, capped at 40,000 by the API. Bucket into daily
   counts. **Discovered during implementation, in two stages**: first
   (2026-08-29) that GitHub returns 401 for every unauthenticated
   request; then (2026-09-12, confirmed against a real token and
   GitHub's own current docs) that as of July 2026 this endpoint is
   restricted to repo admins/collaborators, full stop — **no token
   fixes this for a project you don't administer**. This is a
   permanent, structural limit, not a missing-credential problem: the
   source is kept because it still works for a repo you actually admin,
   but it cannot be used for third-party cross-project analysis, which
   was its purpose here. See `notes/2026-09-12-github-stars-locked-down.md`.
   `pypi.downloads` (and `npm`, where relevant) are the only metrics
   this tool can realistically use against external analysis targets.
4. **npm downloads** (optional, for JS projects) —
   `https://api.npmjs.org/downloads/range/{start}:{end}/{package}`
5. **GitHub traffic** (optional, requires a token with push access to the
   repo) — `https://api.github.com/repos/{owner}/{repo}/traffic/views`
   and `/traffic/clones`. Only 14 days of history, so collect
   incrementally and accumulate in the local DB. Read the token from the
   `GITHUB_TOKEN` env var. Degrade gracefully when it is absent.

Handle GitHub rate limits properly: read `X-RateLimit-Remaining` and
`X-RateLimit-Reset`, and fail with a clear message rather than a stack
trace. Unauthenticated is 60 req/hr, authenticated is 5,000.

## Storage

SQLite at `./hirogari.db` by default, `--db` to override.

```sql
CREATE TABLE metric (
  project TEXT NOT NULL,      -- 'acme/widget'
  source  TEXT NOT NULL,      -- 'pypi' | 'github' | 'npm'
  name    TEXT NOT NULL,      -- 'downloads' | 'stars' | 'views' | 'clones'
  date    TEXT NOT NULL,      -- ISO date
  value   REAL NOT NULL,
  PRIMARY KEY (project, source, name, date)
);

CREATE TABLE event (
  project TEXT NOT NULL,
  date    TEXT NOT NULL,
  kind    TEXT NOT NULL,      -- 'release' | 'post' | 'docs' | 'manual'
  label   TEXT NOT NULL,      -- 'v0.5.0', 'HN front page', 'docs rewrite'
  url     TEXT,
  PRIMARY KEY (project, date, kind, label)
);
```

Collection must be idempotent. Re-running `collect` upserts and never
duplicates.

## Analysis: this is the part that matters

The core function measures whether an event moved adoption, and whether
the movement persisted.

```
lift(project, metric, event_date, pre=14, post=14, sustain_start=15, sustain_end=42)
```

Compute, on daily values of the metric:

- `baseline` — mean of the `pre` days before the event (exclusive of
  event day)
- `immediate` — mean of the `post` days starting on the event day
- `sustained` — mean of days `sustain_start` through `sustain_end` after
  the event
- `immediate_lift_pct` = (immediate - baseline) / baseline
- `sustained_lift_pct` = (sustained - baseline) / baseline
- `robust_z` — the immediate window's deviation from baseline in units of
  the baseline's median absolute deviation (MAD, not stdev — download
  data is spiky and a single bad day wrecks a stdev-based signal)

Then classify:

- `SUSTAINED` — immediate lift is meaningful AND sustained lift holds at
  a substantial fraction of it
- `SPIKE` — immediate lift is meaningful but sustained lift decays toward
  baseline
- `FLAT` — no meaningful immediate lift
- `INSUFFICIENT` — not enough days of data on either side to judge

Every threshold lives in a single `THRESHOLDS` dict at the top of
`analysis.py`, with a comment explaining the choice — visible and
tunable, not scattered through the logic.

Edge cases handled explicitly, not by crashing: zero baseline, missing
days in the series, an event closer to the start or end of the data than
the window requires, overlapping events within the same window (flagged
as `confounded`).

**Superseded during implementation** (see `notes/2026-08-29-trend-adjustment.md`
for the full account): a flat pre-window mean as the lift denominator was
found to misattribute organic growth to every event. `baseline`/`immediate`
/`sustained` and their formulas above describe the *raw, descriptive*
numbers `hirogari` still reports; the actual lift percentages and
`robust_z` are computed against a trend-extrapolated counterfactual, not
the flat baseline mean. `THRESHOLDS["min_window_coverage"]` was raised
from an initial 0.60 to 0.80, and windows are further required to be
whole numbers of weeks to avoid weekday-skewed gaps. The trend fit itself
was later found to be vulnerable to weekday/weekend noise when fit on raw
daily points (see "Difference-in-differences" below and
`notes/2026-08-30-weekly-trend-fit.md`) and now fits on weekly-aggregated
points instead.

### Difference-in-differences

Originally scoped as future work ("worth doing eventually... nets out
ecosystem-wide effects like holidays and PyPI outages"), built the same
day the trend-fit bug above was found — by using it for real:

```
compute_diff_in_diff(treatment_series, control_series_by_project, event_date, ...)
diff_in_diff(store, project, metric, event_date, control_projects, ...)
```

Runs `compute_lift` once for the treatment event and once per candidate
control project, all anchored to the *same* `event_date` and window
sizes. A control is only used if it has no event of its own inside its
own window for that period, has enough data to be non-INSUFFICIENT, and
(added after the first real study, see
`notes/2026-09-12-github-stars-locked-down.md`'s sibling analysis in
`study/FINDINGS.md`) is within
`THRESHOLDS["max_control_baseline_ratio"]` of the treatment's own
baseline scale — a tiny project's percentage swings can be huge on
ordinary noise and would otherwise dominate the control average.
`did_immediate_lift_pct`/`did_sustained_lift_pct` = the treatment's own
lift minus the mean of the usable controls' lift over that identical
calendar window. `classification` is never recomputed from the DiD
numbers — it's still exactly what the treatment's own `compute_lift`
says; DiD is reported alongside as an additional check, not a
replacement verdict.

CLI: `--did` on `hirogari lift` (controls = every other project in the
local db sharing the metric) and `hirogari study` (controls = every
other project in that study's list). Real results across two study runs
(10 projects/787 rows, then 20 projects/2,322 rows with a real token):
most individually-significant findings drop to near-zero or reverse sign
once checked against real no-event controls over the same calendar
window; the one that mostly survives (`pypa/pip`, three separate
releases) turns out to be the package where mechanical CI self-upgrade
traffic (`pip install --upgrade pip` in nearly every CI config) is the
most plausible explanation, not human adoption — see `study/FINDINGS.md`.

## CLI

```
hirogari collect <owner/repo> [--pypi PKG] [--npm PKG]   # fetch + store all available metrics
hirogari events <owner/repo>                             # fetch releases as events
hirogari event add <owner/repo> --date D --label L [--kind K] [--url U]
hirogari lift <owner/repo> [--metric downloads] [--pre N] [--post N]
hirogari report <owner/repo> [--csv PATH]
hirogari study <projects.txt> [--csv PATH]               # run the pipeline across many projects
hirogari list                                            # what's in the local db
```

`study` is the most important command. It takes a newline-delimited file
of `owner/repo[,pypi_package]` lines, collects everything, computes lift
for every release, and writes one tidy CSV row per event. That CSV is the
input to a cross-project analysis, which is the actual point of the tool.

**Added during implementation:** `--did` on both `lift` and `study` —
see "Difference-in-differences" above.

Default output is a readable text table. `--csv` and `--json` everywhere
for machine consumption. Exit non-zero on collection failure so it can
run in CI.

## Repo hygiene

- `README.md`: state the problem in the first two lines. Include a
  one-line note on what the name means. Include real command output
  only — no illustrative or made-up sample output. If there are no
  published results yet, say "pre-alpha, no published results yet" and
  leave the output block out entirely.
- `.github/workflows/tests.yml` running ruff, `mypy --strict`, and pytest
  on 3.11/3.12/3.13
- `CHANGELOG.md`
- `notes/` — an engineering log. When something surprises, or a decision
  was non-obvious, a short dated note about what broke and why the fix is
  what it is.
- Apache-2.0 LICENSE

## Build order

1. Store layer + tests
2. Analysis module + tests against synthetic series with known lift
   (correctness matters most here — a clean step change, a decaying
   spike, pure noise, a series with gaps)
3. PyPI source + fixture tests
4. GitHub releases and stars sources + fixture tests
5. CLI wiring
6. `study` command
7. README
