# 2026-08-29 — window length vs. pypistats' ~180-day history

Flagged before building the PyPI source: pypistats.org's `overall`
endpoint returns roughly 180 days of daily downloads. Each event needs
`pre` (14) + `sustain_end` (42) = 56 usable days spanning it — the pre
window before, the sustain window after — before it can be classified as
anything but INSUFFICIENT. Events within the first 14 or last 42 days of
the ~180-day history drop out automatically, and on top of that, whole-
week filtering (`2026-08-29-trend-adjustment.md`'s sibling note on
`min_window_coverage`) can drop more if any week in an event's windows
has a gap.

Action for step 3: before building `study` on top of this, pull real
downloads for an actual fast-shipping open-source package (kept unnamed
here on purpose — see SPEC.md's "never reference specific companies or
projects" framing; pick any real, frequently-releasing PyPI package when
running this check) and count what fraction of its releases actually
survive to a non-INSUFFICIENT classification.

## Result (run 2026-08-29, target redacted)

Ran `hirogari collect`/`hirogari lift` for real against a real,
extremely-frequently-releasing PyPI package/GitHub repo (~300 releases
since 2018, several per month). Findings:

- **284 of 300 releases (95%) came back INSUFFICIENT** — but almost all
  of that is pypistats' ~180-day history limit, not window strictness:
  the release history goes back to 2018, download history only to
  ~6 months ago, so the large majority of releases simply predate any
  available download data by construction. This is a hard ceiling
  pypistats imposes, not something `hirogari`'s window choices can fix.
- Restricting to releases that actually fall inside the
  theoretically-evaluable date range (new enough to have a full pre
  window, old enough to have a full post+sustain window), **16 of 16
  (100%) got a real classification** — zero additional INSUFFICIENT from
  whole-week coverage strictness once history-limit exclusion is
  accounted for. The 0.80/whole-week tightening from earlier today is
  not the bottleneck on real data; the ~180-day history window is.
- **All 16 of those were flagged `confounded`, and all 16 classified
  FLAT.** A project shipping this often has another release inside the
  analysis window of nearly every release — clean single-release
  attribution is structurally close to impossible for a project at this
  release cadence, independent of anything in `hirogari`'s own logic.
  One spot-checked row had a 24% immediate_lift_pct that still read FLAT
  because robust_z was only ~1.0 — exactly the AND-not-OR gate in
  `_is_meaningful` doing its job on real, noisy, high-volume data (a
  pct-only threshold would have false-positived this). (2026-08-30: the
  trend fit itself was fixed the next day — see
  `2026-08-30-weekly-trend-fit.md` — and re-checking this same row now
  shows -12.4%/z=-1.13 instead of +24%/z=1.0. Sign flipped, same
  conclusion: still correctly reads FLAT, still the AND-gate doing its
  job. The 284/16/100%/100% counts above are unchanged by that fix.)

**Implication for `study`:** a project list weighted toward
fast-shipping projects will yield mostly INSUFFICIENT (history-limited)
and mostly `confounded` (cadence-limited) results, not a clean signal.
`study`'s eventual output/writeup should report the confounded-rate and
history-exclusion-rate as diagnostics alongside the lift numbers, and the
project list should mix in lower-cadence projects (a project releasing
every 6-8+ weeks has room for both a clean pre-window and a clean,
unconfounded post/sustain window) rather than assuming any public GitHub
project will do.

## Separate finding from the same run: GitHub stargazers now requires auth

Not part of the original question, but discovered while running this
check: `GET /repos/{owner}/{repo}/stargazers` returned 401 for every
unauthenticated request tried (multiple real, definitely-public repos,
with and without the `star+json` Accept header) — GitHub has tightened
this beyond just a lower rate limit at some point after this tool's
knowledge cutoff. `collect_stars` still accepts `token: str | None` for
interface consistency with the other GitHub sources, but the CLI now
checks for `GITHUB_TOKEN` and skips stars collection proactively (same
pattern as traffic) instead of always hitting the same 401.
