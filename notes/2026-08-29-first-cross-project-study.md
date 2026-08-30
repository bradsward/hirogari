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

## The study actually found real signal, not just null results (revised next day)

Going in, I expected (based on the single-project validation run) that a
real study would be dominated by INSUFFICIENT and FLAT with maybe nothing
else — and 95% INSUFFICIENT / ~5% FLAT held. There were also **2 real
SUSTAINED results** (out of 787 rows) at the time this note was
originally written, and one of them (`pytest-dev/pytest` 9.0.3) looked
clean: not confounded, `robust_z` 3.06, sustained lift 133.6%.

**Revised 2026-08-30, don't trust the numbers above:** a real `--did` run
pointed at exactly that "clean" finding surfaced a bug in the trend fit
itself (contaminated by weekday/weekend noise — see
`2026-08-30-weekly-trend-fit.md`). After fixing it and re-running, only
1 of the 2 SUSTAINED findings survived, and DiD then showed *that one*
wasn't project-specific either — three real control projects moved
almost as much over the same calendar window with no release of their
own. Net: zero of 787 rows represent a DiD-confirmed, project-specific
lift. `study/FINDINGS.md` has the corrected, current numbers; this note
is left as-is (rather than rewritten) as a record of what the reasoning
looked like before the DiD feature existed to check it.
