"""Hacker News posts about a project, via the public Algolia search API
(hn.algolia.com — no auth, no API key). Turns matching stories into
`post` events.

This closes a real gap: `hirogari` has claimed to measure "posts" since
its very first README line, but until this module existed, a `post`
event could only ever be entered manually with `hirogari event add`.
Nothing found them automatically.

Read the precision/recall tradeoff below before trusting silence from
this source as "no post ever happened" — it isn't that.
"""

from __future__ import annotations

import urllib.parse
from datetime import UTC, date, datetime

from hirogari.sources.base import SourceError, http_get_json
from hirogari.store import Event

_SEARCH_URL = "https://hn.algolia.com/api/v1/search"
_MAX_PAGES = 5  # generous cap; one project rarely has more than a handful of genuine hits

# A submission needs at least this many points to count as a real `post`
# event, not noise. HN gets a constant stream of link submissions that
# never leave the "new" queue (0-2 points is common and means essentially
# nobody saw it); 50 is comfortably below front-page territory but well
# above "nobody saw this."
MIN_POINTS_DEFAULT = 50


def collect_posts(project: str, *, min_points: int = MIN_POINTS_DEFAULT) -> list[Event]:
    """Hacker News stories that link *directly* to `project`'s GitHub
    repo, turned into `post` events.

    Searches Algolia's full-text index for "github.com/{project}", then
    keeps only hits whose own `url` field actually contains that string
    (case-insensitively) — i.e. genuine link submissions of the repo,
    not any story that happens to mention the URL somewhere in a long
    text post. Verified live (2026-09-12): a bare full-text match alone
    pulls in things like an 8-point "Ask HN" rant that links to a dozen
    unrelated libraries including this one in passing. Restricting to
    the submission's own URL cut that kind of false positive out
    entirely in testing, at a real recall cost documented below.

    **This is a narrow, precision-over-recall source, by design and by
    necessity, not an oversight:** a lot of genuine discussion of a
    project links to its docs site, a blog post, or PyPI page rather
    than the bare `github.com/{owner}/{repo}` URL, and none of that is
    found here. A project with real, well-known HN history can still
    come back with only one or two hits (verified live against a very
    well-known FastAPI-adjacent repo: 11 raw full-text matches, only 1
    survived both the direct-URL and `min_points` filters). Silence from
    this source means "no *direct-link* HN submission cleared the points
    bar," not "this project was never discussed."
    """
    if "/" not in project:
        raise SourceError(f"project must be 'owner/repo', got {project!r}")

    target = f"github.com/{project}".lower()
    events: list[Event] = []
    seen_ids: set[str] = set()
    page = 0
    n_pages = 1

    while page < min(_MAX_PAGES, n_pages):
        params = urllib.parse.urlencode(
            {"query": f"github.com/{project}", "tags": "story", "hitsPerPage": 100, "page": page}
        )
        body, _ = http_get_json(f"{_SEARCH_URL}?{params}")
        try:
            hits = body["hits"]
            n_pages = body["nbPages"]
        except (KeyError, TypeError) as exc:
            raise SourceError(f"unexpected HN search response shape for {project!r}") from exc

        for hit in hits:
            try:
                object_id = hit["objectID"]
                points = hit.get("points") or 0
                created_at_i = hit["created_at_i"]
                title = hit.get("title") or f"HN post {object_id}"
                url_field = (hit.get("url") or "").lower()
            except (KeyError, TypeError) as exc:
                raise SourceError(f"unexpected HN hit shape for {project!r}: {hit!r}") from exc

            if object_id in seen_ids:
                continue
            seen_ids.add(object_id)
            if target not in url_field or points < min_points:
                continue

            try:
                when: date = datetime.fromtimestamp(created_at_i, tz=UTC).date()
            except (OverflowError, OSError, ValueError) as exc:
                raise SourceError(
                    f"unexpected created_at_i for {project!r}: {created_at_i!r}"
                ) from exc

            events.append(
                Event(project, when, "post", title, f"https://news.ycombinator.com/item?id={object_id}")
            )

        page += 1

    return events
