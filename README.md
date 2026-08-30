# hirogari

Developer-tool companies acquire users through GitHub repos, docs pages, package registries, and forum posts — none of which shows up in normal marketing analytics, because the buyer is an engineer who never fills out a form. `hirogari` measures that path using only public data: which releases, docs changes, and posts actually moved adoption, and did the lift last.

広がり (hirogari) — spread, diffusion. How far something traveled, not how much of it there is.

This is a methodology/credibility project, not a product — see [SPEC.md](SPEC.md) for what it is and isn't in scope for, and why it exists. **Pre-alpha**, but the pipeline runs end-to-end against real public APIs and has a first published cross-project study: [study/](study/) (787 real events across 8 projects, [findings here](study/FINDINGS.md)).

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

`--db PATH` (before the subcommand) points at a SQLite file other than `./hirogari.db`. `--csv`/`--json` work anywhere a command produces rows. `GITHUB_TOKEN` raises GitHub's rate limit from 60/hr to 5,000/hr and is required for the stars and traffic sources (see below).

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
every project in a list, ready for cross-project analysis. First real run:
10 real public PyPI/GitHub projects, chosen to mix release cadence on
purpose (see why below) — [study/projects.txt](study/projects.txt) in,
[study/results.csv](study/results.csv) out, 787 rows.

Headline results: **95% of rows came back INSUFFICIENT** (pypistats' ~180
-day history against years of release history — a hard ceiling), **84%
of the rest were flagged `confounded`**, and out of 787 rows there were
exactly **2 SUSTAINED findings** — one of them (`pytest-dev/pytest`
9.0.3, unconfounded: +45.7% immediate, +133.6% sustained, `robust_z`
3.06) is the one result in the whole run the methodology can actually
stand behind as a clean, specific, defensible claim. Full breakdown,
per-project table, and what this run does/doesn't support:
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
  "counterfactual_immediate": 9947740.65,
  "immediate_lift_pct": 0.2440,
  "robust_z": 1.0274,
  "classification": "FLAT",
  "confounded": true,
  "notes": "another event falls within this event's analysis window"
}
```

That row is a real validation of the methodology working as intended, not just a data point: a 24% immediate lift *looks* significant, but `robust_z` is only ~1.0 — not statistically unusual against this project's own noise — so it correctly reads FLAT instead of a false positive. That's the AND-not-OR gate (percentage threshold *and* z-score threshold) doing its job on real, noisy, high-volume download data.

Aggregate findings across all 300 releases:

| | count | share |
|---|---|---|
| INSUFFICIENT (no data in pypistats' ~180-day window) | 284 | 95% |
| Evaluable at all (full pre/post/sustain windows available) | 16 | 5% |
| ...of which FLAT | 16 | 100% |
| ...of which flagged `confounded` | 16 | 100% |

The 95% INSUFFICIENT rate is almost entirely pypistats' ~180-day download history against a release history going back to 2018 — a hard ceiling, not a tuning problem. More notably: of the releases that *were* evaluable, **100% were confounded** — this project ships often enough that nearly every release has another release inside its own analysis window, making clean single-release attribution close to structurally impossible at that cadence. Full writeup: [notes/2026-08-29-window-vs-history-length.md](notes/2026-08-29-window-vs-history-length.md).

**What this predicted, and what actually happened:** a project list weighted toward fast-shipping projects would produce mostly INSUFFICIENT and mostly `confounded` results, not a clean cross-project signal — so the study above deliberately mixed in slower-cadence projects. It still came back 95% INSUFFICIENT and 84% confounded, which held the prediction, and found exactly 2 real SUSTAINED results in the other 5%.

## Methodology

Full detail in [SPEC.md](SPEC.md) and the dated notes in [notes/](notes/). Short version: `hirogari lift` doesn't compare an event's aftermath to the flat historical average — it fits a trend on the pre-event baseline and extrapolates it forward as the counterfactual, then measures lift against *that*. A project growing organically at 5%/week will otherwise show "lift" after every single release, which is measuring growth, not attribution. See [notes/2026-08-29-trend-adjustment.md](notes/2026-08-29-trend-adjustment.md) for the full account, including the tradeoffs this introduces (extrapolation confidence decays with distance from the fit window; a release's real effect partly leaks into the next release's baseline on fast-shipping projects) and the mechanical-install-traffic caveat that applies to every `release` event regardless of methodology.

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
