# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project doesn't have versioned releases yet — everything so far is
`[Unreleased]`.

## [Unreleased]

### Added

- SQLite store layer (`metric`/`event` tables, idempotent upserts).
- Trend-adjusted lift analysis (`hirogari.analysis`): fits a log-linear
  (falling back to linear) trend on the pre-event baseline and measures
  lift against that extrapolated counterfactual rather than a flat
  baseline mean, specifically to avoid attributing organic growth to
  events. Classifies each event as `SUSTAINED` / `SPIKE` / `FLAT` /
  `INSUFFICIENT`. Windows must be whole numbers of weeks (weekday-skew
  protection); coverage is computed per whole week, not per raw day.
- Data sources (`hirogari.sources`): PyPI downloads, npm downloads,
  GitHub releases (-> events), GitHub stargazers (-> daily new-star
  counts, requires `GITHUB_TOKEN` in practice — GitHub now 401s
  unauthenticated requests to this endpoint), GitHub traffic
  (views/clones, requires `GITHUB_TOKEN`). GitHub rate-limit handling
  (`X-RateLimit-Remaining`/`-Reset`) with a clear error instead of a
  stack trace.
- CLI (`hirogari`): `collect`, `events`, `event add`, `lift`, `report`,
  `study`, `list`. Table output by default; `--csv`/`--json` everywhere
  that produces rows. Non-zero exit on collection failure.
- `SPEC.md` (the living spec) and `notes/` (dated engineering log).
- First real cross-project study: `study/projects.txt` (10 real public
  projects, deliberately mixed release cadence) and `study/results.csv`
  (787 rows), with a full writeup in `study/FINDINGS.md`. Also surfaced a
  real gap: 2 of the 10 projects use only git tags, not GitHub Releases,
  so they contribute zero events.
- `github_releases.collect_releases` now falls back to tags when a
  project has zero GitHub Releases (fixes the gap above), gated on
  `GITHUB_TOKEN` being set — resolving each tag's date costs one extra
  API request per tag with no bulk endpoint available, which a project
  with 60+ tags would exhaust the unauthenticated 60/hr budget on by
  itself. Verified against real API response shapes; not yet re-run live
  end-to-end against certifi/cryptography since this environment has no
  `GITHUB_TOKEN` available.
- Difference-in-differences (`compute_diff_in_diff`/`diff_in_diff`,
  `--did` on `lift` and `study`): nets a treatment project's
  trend-adjusted lift against a set of control projects with no event of
  their own in the same calendar window, to catch a shared ecosystem
  -wide effect that a single-project trend fit can't see on its own.
  Real result: applying it to the cross-project study's one SUSTAINED
  finding (which cleared both thresholds on its own) dropped it to a
  negligible DiD-adjusted lift once checked against three real
  no-event controls over the same window — see `study/FINDINGS.md` and
  `notes/2026-08-30-weekly-trend-fit.md`.

### Fixed (pre-release, caught before or via real use, not by users)

- `compute_lift` originally compared events to the flat pre-window mean,
  which misattributes organic growth to every event on a growing project.
  Replaced with the trend-counterfactual approach described above.
- `cli.py`: `--db` given before the subcommand was silently overwritten
  by the subcommand's own default (argparse subparser-dispatch footgun —
  see `notes/2026-08-29-cli-bugs.md`).
- `output.py`: `print_table`/`print_json` defaulted their `file` parameter
  to `sys.stdout` evaluated at import time, so later stdout redirection
  (tests, pipes) was invisible to them. Now resolved at call time.
- The trend fit was regressing on individual daily points, which a short
  (2-4 week) baseline made vulnerable to weekday/weekend noise —
  contaminating the fitted slope in a way that's *correlated across
  unrelated projects* sharing the same calendar, found via a real `--did`
  run. Now fits on weekly-aggregated points instead
  (`notes/2026-08-30-weekly-trend-fit.md`). `study/results.csv`
  regenerated; one of the two prior SUSTAINED findings flipped to FLAT
  under the corrected fit.
