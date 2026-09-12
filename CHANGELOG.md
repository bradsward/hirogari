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
  counts — restricted by GitHub to repo admins/collaborators as of
  July 2026, see Fixed below), GitHub traffic (views/clones, requires
  `GITHUB_TOKEN`). GitHub rate-limit handling
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
  itself. Live-verified 2026-09-12 with a real token: certifi (66 tags)
  and cryptography (160 tags) both resolved correctly.
- Difference-in-differences (`compute_diff_in_diff`/`diff_in_diff`,
  `--did` on `lift` and `study`): nets a treatment project's
  trend-adjusted lift against a set of control projects with no event of
  their own in the same calendar window, to catch a shared ecosystem
  -wide effect that a single-project trend fit can't see on its own.
  Controls are also filtered to a similar traffic scale
  (`THRESHOLDS["max_control_baseline_ratio"]`) so one noisy small
  project's percentage swings can't dominate the average.
- Expanded the cross-project study from 10 to 20 real projects (mixing
  domain as well as release cadence) and re-ran it with a real
  `GITHUB_TOKEN`: 2,322 rows. Live-verified the tags-fallback for the
  first time (certifi: 66 tags, cryptography: 160 tags, both resolved
  correctly). Of 6 non-FLAT findings, 3 wash out under DiD (one,
  `pyca/cryptography`, reverses sign entirely), and the 3 that don't are
  all `pypa/pip` — whose surviving signal is more plausibly explained by
  automatic `pip install --upgrade pip` CI traffic than human adoption.
  See `study/FINDINGS.md`.

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
- GitHub stargazers still doesn't work with a real token: as of July
  2026 GitHub restricts the listing endpoint to repo admins/collaborators
  (confirmed against their own current docs), not just "needs auth" as
  the 2026-08-29 fix assumed. No token fixes this for a third-party
  project. `collect_stars` now gives a clear message explaining this
  instead of a generic 404; docs updated to stop implying `GITHUB_TOKEN`
  unlocks it. See `notes/2026-09-12-github-stars-locked-down.md`.
