# 2026-09-12 — a real `post` event source, and an honest limit on it

`hirogari`'s README has said "posts" since the very first line, but
until today a `post` event only ever existed if someone typed
`hirogari event add ... --kind post` by hand. Nothing found them. Closed
that gap with `hirogari.sources.hn` — Hacker News's public Algolia
search API (`hn.algolia.com`, no auth, no key).

## Design: precision over recall, on purpose

First attempt: full-text search for `"github.com/{owner}/{repo}"`.
Tested live against `psf/requests` — the top few hits included an 8
-point "Ask HN" rant that happens to link to a dozen unrelated libraries,
`requests` among them, in passing. That's not a "post about requests,"
it's noise a naive keyword match can't tell apart from a real one.

Fix: keep the full-text search (it's the only way to search HN at all),
but only keep hits whose *own* `url` field actually contains the target
string — i.e. the story's submitted link is a direct link to the repo,
not just a story that mentions it somewhere. Combined with a
`min_points` floor (default 50 — well below front-page, comfortably
above "nobody saw this").

Tested live against `tiangolo/fastapi`: 11 raw full-text hits, only 1
survived both filters (a 66-point post about async/await, which does
link directly to the repo). That's a huge cut — and it's the right
tradeoff, not a bug to fix later. A lot of genuine HN discussion of a
project links to its docs site, a blog post, or a PyPI page rather than
the bare GitHub URL, and none of that will ever be found here. Silence
from this source means "no direct-link submission cleared the points
bar," not "nobody ever discussed this project."

## A second, harder limit: found posts skew old

Real events found (live, 2026-09-12):

- `psf/requests` — "Requests moved to Python Software Foundation" (2019)
- `pypa/pip` — "Pipfile for Python" (2016), "If this project is dead,
  just tell us" (2019), "New Pip resolver takes a long time to complete"
  (2020)
- `tiangolo/fastapi` — "Too many emojis in 'Concurrency and async /
  await' explanation" (2022)
- `pytest-dev/pytest`, `pallets/click` — none found (0, not an error)

Every one of these predates pypistats' ~180-day download history by
years. That's not a coincidence specific to these projects: an
established, well-known project's *notable* HN moments (launch,
controversy, a widely-shared post) tend to cluster around when it was
new or newsworthy, which for a mature project is long ago — while
pypistats can only ever see the trailing ~180 days. The intersection of
"has a real HN post" and "that post is recent enough to have download
data on both sides of it" is going to be small in practice, for the same
underlying reason (`notes/2026-08-29-window-vs-history-length.md`) that
already dominates the release-event INSUFFICIENT rate. A newer or
currently-trending project is exactly the case where this source and
pypistats' window would actually overlap usefully — it just won't be
any of the mature, famous projects already in `study/projects.txt`.
