# 2026-09-12 — GitHub stargazers is now admin/collaborator-only

Two weeks ago (`2026-08-29-window-vs-history-length.md`) the finding was
"GitHub now requires auth for stargazers" and the fix was: gate
`collect_stars` on `GITHUB_TOKEN`, skip gracefully without one. Got a
real token today to unlock it properly — and it still 404s, on every
project, authenticated or not.

Checked GitHub's own current docs
(docs.github.com/rest/activity/starring) rather than guess further:

> In July 2026, to ensure responsible use of this data and to protect
> users from misuse, we are introducing new access restrictions to the
> endpoints related to starring. Access to the stargazers listing
> endpoints will be limited to admins and collaborators.

That's a permission wall, not an auth-strength problem. **No token fixes
this for a project you don't administer.** The two-week-old fix (gate on
`GITHUB_TOKEN`) was correct for the intermediate state GitHub was in on
2026-08-29, but the endpoint has moved past that — the restriction fully
landed since then, and now covers everyone except the repo's own
admins/collaborators, authenticated or not.

## What changed

- `github_stars.collect_stars` now catches the specific 404 and re-raises
  a clear message pointing at GitHub's own docs, instead of a generic
  "HTTP 404: Not Found" that gives no hint this isn't fixable by trying
  harder. Verified against the live API today (not synthetic).
- CLI's no-token skip message updated: it no longer implies getting a
  token would help for a third-party repo, since it wouldn't.
- The source itself is kept, not removed — it still works for a repo you
  actually admin (hirogari's own repo, for instance), which is a
  legitimate if narrow use case. It cannot be used for the tool's actual
  purpose here: pulling star history for *other people's* projects as
  part of a cross-project study.

## What this means for hirogari going forward

`github.stars` is now permanently unavailable as a metric for any
cross-project study of third-party OSS adoption, full stop — not a
missing-token problem to revisit later. `pypi.downloads` (and `npm`,
where relevant) are the only metrics this tool can realistically use for
external analysis targets going forward, since releases/tags are still
publicly readable and pypistats/npm's download-count APIs remain
unauthenticated and public. SPEC.md and the README are updated to stop
describing `GITHUB_TOKEN` as "unlocking stars data" and instead say
plainly that it doesn't, for anything but your own repos.
