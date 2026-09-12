# hirogari

[![tests](https://github.com/bradsward/hirogari/actions/workflows/tests.yml/badge.svg)](https://github.com/bradsward/hirogari/actions/workflows/tests.yml)
[![python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)](pyproject.toml)
[![license](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)
[![dependencies](https://img.shields.io/badge/runtime%20deps-0-brightgreen)](pyproject.toml)

Developer-tool companies acquire users through GitHub repos, docs pages, package registries, and forum posts — none of which shows up in normal marketing analytics, because the buyer is an engineer who never fills out a form. `hirogari` measures that path using only public data: which releases, docs changes, and posts actually moved adoption, and did the lift last.

広がり (hirogari) — spread, diffusion. How far something traveled, not how much of it there is.

This is a methodology/credibility project, not a product — see [SPEC.md](SPEC.md) for what it is and isn't in scope for, and why it exists. **Pre-alpha**, but the pipeline runs end-to-end against real public APIs and has a published cross-project study with difference-in-differences applied: [study/](study/) (2,322 real events across 20 projects, [findings here](study/FINDINGS.md)).

## Install

```bash
pip install -e ".[dev]"
```

Python 3.11+. Zero runtime dependencies (stdlib only).

## Commands

```
hirogari collect <owner/repo> [--pypi PKG] [--npm PKG]   # fetch + store all available metrics
hirogari events <owner/repo>                              # fetch releases as events
hirogari event add <owner/repo> --date D --label L [--kind K] [--url U]
hirogari lift <owner/repo> [--metric pypi.downloads] [--pre N] [--post N]
hirogari report <owner/repo> [--csv PATH]
hirogari study <projects.txt> [--csv PATH]                 # run the pipeline across many projects
hirogari list                                               # what's in the local db
```

`--db PATH` (before the subcommand) points at a SQLite file other than `./hirogari.db`. `--csv`/`--json` work anywhere a command produces rows. `GITHUB_TOKEN` raises GitHub's rate limit from 60/hr to 5,000/hr, is required for the traffic source, and lets the release-events source fall back to tags for projects that don't use GitHub Releases. It does **not** unlock GitHub stars for other people's projects — see [Cross-project study](#cross-project-study) below.

## Real output

`hirogari --help`:

```
usage: hirogari [-h] [--db DB]
                {collect,events,event,lift,report,study,list} ...

Measure whether releases, docs changes, and posts moved OSS adoption, and
whether it lasted.

positional arguments:
  {collect,events,event,lift,report,study,list}
    collect             fetch + store all available metrics for a project
    events              fetch GitHub releases as events
    event               manage events
    lift                compute lift for every stored event against one metric
    report              lift for every stored event against every stored
                        metric
    study               collect + compute lift across many projects at once
    list                show what's in the local db

options:
  -h, --help            show this help message and exit
  --db DB               SQLite database path (default: hirogari.db)
```

Adding events and listing the local db (`example/project` is a local placeholder — no network call):

```
$ hirogari event add example/project --date 2026-01-15 --label "docs rewrite" --kind docs
added docs event 'docs rewrite' on 2026-01-15 for example/project

$ hirogari event add example/project --date 2026-02-01 --label "v1.2.0" --kind release
added release event 'v1.2.0' on 2026-02-01 for example/project

$ hirogari list
example/project
  events: 2 (1 docs, 1 release)
```

## Cross-project study

`study` is the point of the tool — one CSV row per (event, metric), across
every project in a list, ready for cross-project analysis, with
difference-in-differences applied (`--did`): every project's lift is also
netted against every *other* studied project as a control (filtered to a
similar traffic scale, so a tiny project's noisy percentage swings can't
dominate the average), to catch a shared calendar-window effect
masquerading as one project's result. Real run: 20 real public
PyPI/GitHub projects, chosen to mix release cadence and domain on purpose
(see why below) — [study/projects.txt](study/projects.txt) in,
[study/results.csv](study/results.csv) out, 2,322 rows.

Headline results: **95.9% INSUFFICIENT** (pypistats' ~180-day history
against years of release history — a hard ceiling), **85% of the rest
flagged `confounded`**, and **6 non-FLAT findings** out of 2,322 rows.
Checking each against DiD: 3 wash out to near-zero or flip sign (one,
`pyca/cryptography`, actually reverses — its "SUSTAINED" reading turns
out to be an *underperformance* once compared to what similar projects
did over that window). The other 3 all belong to **`pypa/pip`**, and its
cleanest, unconfounded release (`26.1.2`: `robust_z` 2.30, +38.7% own
immediate lift) still shows **+20.6% immediate lift after DiD** — the
single most defensible positive result across the whole study. But pip
is also the one package where `pip install --upgrade pip` runs
automatically in nearly every CI pipeline with no human ever deciding to
adopt anything — the result that survives the most rigorous check in
this project is also the one where "adoption" is the least appropriate
word for what's actually being measured. Full breakdown, the per-event
table, and the trend-fit bug a real DiD run surfaced along the way:
[study/FINDINGS.md](study/FINDINGS.md).

## Single-project deep dive (methodology demonstration)

Before running the multi-project study above, I validated the methodology
against a single real, very-frequently-releasing PyPI package and GitHub
repo (~300 releases since 2018, several per month — this is the same
`tiangolo/fastapi` project that appears by name in the study above, but
this section predates the decision to name real projects in this repo, so
it stays redacted as originally written).

```
$ hirogari collect <redacted> --pypi <redacted>
<redacted>: github releases: 300 row(s)
<redacted>: github stars: skipped (GITHUB_TOKEN not set; GitHub requires auth)
<redacted>: pypi downloads: 181 row(s)
<redacted>: github traffic: skipped (GITHUB_TOKEN not set)
```

One representative row from `hirogari lift <redacted> --json` (real numbers, not illustrative):

```json
{
  "event_kind": "release",
  "event_label": "0.135.2",
  "event_date": "2026-03-23",
  "baseline": 11681052.43,
  "immediate": 12375391.43,
  "sustained": 14663055.61,
  "trend_pct_per_day": 0.0136,
  "counterfactual_immediate": 14121481.99,
  "immediate_lift_pct": -0.1236,
  "robust_z": -1.1342,
  "classification": "FLAT",
  "confounded": true,
  "notes": "another event falls within this event's analysis window"
}
```

That row is a real validation of the methodology working as intended, not just a data point: `immediate` (12.4M) is actually higher than `baseline` (11.7M) — looks like growth at a glance — but the fitted trend was already climbing faster than that (`trend_pct_per_day` +1.4%/day), so the counterfactual it's compared against is *higher still* (14.1M), and the actual value undershoots it. `robust_z` (-1.13) doesn't clear ±2.0, so it correctly reads FLAT instead of crediting a release for growth the project was already on track for anyway. That's the trend-counterfactual and the AND-not-OR gate (percentage threshold *and* z-score threshold) both doing their job on real, noisy, high-volume download data.

Aggregate findings across all 300 releases:

| | count | share |
|---|---|---|
| INSUFFICIENT (no data in pypistats' ~180-day window) | 284 | 95% |
| Evaluable at all (full pre/post/sustain windows available) | 16 | 5% |
| ...of which FLAT | 16 | 100% |
| ...of which flagged `confounded` | 16 | 100% |

The 95% INSUFFICIENT rate is almost entirely pypistats' ~180-day download history against a release history going back to 2018 — a hard ceiling, not a tuning problem. More notably: of the releases that *were* evaluable, **100% were confounded** — this project ships often enough that nearly every release has another release inside its own analysis window, making clean single-release attribution close to structurally impossible at that cadence. Full writeup: [notes/2026-08-29-window-vs-history-length.md](notes/2026-08-29-window-vs-history-length.md).

**What this predicted, and what actually happened:** a project list weighted toward fast-shipping projects would produce mostly INSUFFICIENT and mostly `confounded` results, not a clean cross-project signal — so the study above deliberately mixed in slower-cadence projects and different domains. It still came back 95.9% INSUFFICIENT and 85% confounded, which held the prediction, and the handful of real findings mostly didn't survive being checked against real controls — except one, for a reason that has more to do with CI automation than adoption (see above).

## Methodology

Full detail in [SPEC.md](SPEC.md) and the dated notes in [notes/](notes/). Short version:

- `hirogari lift` doesn't compare an event's aftermath to the flat historical average — it fits a trend on the pre-event baseline (on weekly-aggregated points, not raw days — see below) and extrapolates it forward as the counterfactual, then measures lift against *that*. A project growing organically at 5%/week will otherwise show "lift" after every single release, which is measuring growth, not attribution. [notes/2026-08-29-trend-adjustment.md](notes/2026-08-29-trend-adjustment.md) has the full account, including the tradeoffs this introduces (extrapolation confidence decays with distance from the fit window; a release's real effect partly leaks into the next release's baseline on fast-shipping projects).
- `--did` (on `lift` and `study`) nets that trend-adjusted lift against every other project in the pool as a control, filtered to a similar traffic scale — a shared calendar-window effect (not specific to any one project) shows up in both and cancels; a project-specific effect doesn't. Built after a real DiD run caught a real bug in the trend fit itself (raw-daily-point regression contaminated by weekday/weekend noise, fixed by fitting on weekly-aggregated points instead) and then, with that fixed, showed most of the cross-project study's "clean" findings weren't actually project-specific — see [notes/2026-08-30-weekly-trend-fit.md](notes/2026-08-30-weekly-trend-fit.md) for the full, fairly striking, account.
- Every `release` event carries a mechanical-install-traffic caveat (CI pins, Dependabot, mirror resyncs) that no amount of statistical adjustment removes — `pypa/pip` in the cross-project study is close to a worked example of exactly this. See the same trend-adjustment note.
- GitHub stargazer history cannot be collected for third-party projects at all as of July 2026 (GitHub restricts it to repo admins/collaborators) — see [notes/2026-09-12-github-stars-locked-down.md](notes/2026-09-12-github-stars-locked-down.md). `pypi.downloads` is the only metric this tool can realistically use against external analysis targets today.
- "Posts" (the third thing in this README's first sentence) had no automated source until today — `hirogari collect` now also checks Hacker News (`hn.algolia.com`, no auth) for direct-link submissions of the repo, real points threshold applied. Verified live against 5 real projects: `pypa/pip` had 3 real hits, `psf/requests` and `tiangolo/fastapi` 1 each, `pytest-dev/pytest` and `pallets/click` 0. It's a deliberately narrow, precision-over-recall source (a story that mentions a project without linking directly to its GitHub repo is invisible to it) — see [notes/2026-09-12-hn-posts-source.md](notes/2026-09-12-hn-posts-source.md) for what that trades away and why.

## Development

```bash
pip install -e ".[dev]"
ruff check src/ tests/
mypy --strict src/
pytest tests/
```

Tests never hit the network — sources are tested against recorded fixtures in `tests/fixtures/`.

## License

Apache-2.0. See [LICENSE](LICENSE).
