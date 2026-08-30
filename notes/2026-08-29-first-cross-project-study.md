# 2026-08-29 — first real cross-project study run

Ran `hirogari study study/projects.txt --csv study/results.csv` for real
against 10 real public projects (list deliberately mixes release cadence,
per the same-day finding in `2026-08-29-window-vs-history-length.md`
that fast-shipping-only project lists produce almost nothing usable). No
`GITHUB_TOKEN` set, so only `pypi.downloads` was evaluated (stars/traffic
skipped for every project, consistent with the earlier finding that
GitHub now requires auth for stargazers).

Full results and analysis: `study/FINDINGS.md`. Two things surprised me
enough to write down here specifically:

## Two projects contributed zero events, and it's not a bug

`certifi/python-certifi` and `pyca/cryptography` both came back with 0
releases from `hirogari events`. Checked directly against the GitHub API
(not through hirogari) before assuming a bug — confirmed both projects
tag versions without ever creating a GitHub Release object, so the
releases endpoint genuinely returns an empty list for them. This is a
real gap in the `release`-event source: it only sees adoption signal for
projects that use GitHub's Releases feature. Worth remembering before
assuming a project that shows 0 events in `hirogari list` has no release
history at all — it might just not use Releases.

**Update (same day):** built the tags-based fallback. GitHub's REST API
has no bulk "tag name + date" endpoint — the tags list gives a commit
SHA per tag, and resolving each one to a date costs a separate
`/commits/{sha}` request. certifi alone has 66 tags and cryptography has
100+, so an unauthenticated run (60 req/hr total) would blow its entire
budget resolving one project's tags before touching anything else. The
fallback is gated on `GITHUB_TOKEN` being present for exactly this
reason — same pattern as stars/traffic. Verified the tag-list and
commit-detail JSON shapes directly against the live API (both match what
the code expects) and covered the logic with fixture tests, but haven't
re-run the actual `certifi`/`cryptography` fallback live end-to-end,
since this environment has no `GITHUB_TOKEN` available.

## The study actually found real signal, not just null results

Going in, I expected (based on the single-project validation run) that a
real study would be dominated by INSUFFICIENT and FLAT with maybe nothing
else — and 95% INSUFFICIENT / 4% FLAT held. But there were also **2 real
SUSTAINED results** (out of 787 rows), and one of them
(`pytest-dev/pytest` 9.0.3) is clean: not confounded, `robust_z` 3.06,
sustained lift 133.6%. That's not a fluke of loose thresholds — it's the
same 0.10/2.0/0.80/whole-week thresholds that produced FLAT on everything
else in this run, including rows with a bigger raw `immediate_lift_pct`
that didn't clear `robust_z`. Worth keeping as a concrete existence proof
that the methodology can and does distinguish a specific real event from
noise, not just a filter that outputs INSUFFICIENT/FLAT forever.
