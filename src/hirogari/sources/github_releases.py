"""GitHub releases, turned into `release` events."""

from __future__ import annotations

from datetime import datetime

from hirogari.sources.base import SourceError, github_headers, paginate_github
from hirogari.store import Event


def collect_releases(project: str, *, token: str | None = None) -> list[Event]:
    """Fetch all releases for `project` ("owner/repo") as `release` events.

    Draft releases (`published_at` is null) are skipped: a draft was
    never actually visible to users, so it can't have moved adoption and
    has no publish date to anchor an event on anyway.
    """
    if "/" not in project:
        raise SourceError(f"project must be 'owner/repo', got {project!r}")

    url = f"https://api.github.com/repos/{project}/releases?per_page=100"
    rows = paginate_github(url, github_headers(token))

    events: list[Event] = []
    for row in rows:
        published_at = row.get("published_at")
        if published_at is None:
            continue
        try:
            tag = row["tag_name"]
            when = datetime.strptime(published_at, "%Y-%m-%dT%H:%M:%SZ").date()
        except (KeyError, ValueError) as exc:
            raise SourceError(f"unexpected GitHub release shape for {project!r}: {row!r}") from exc
        events.append(Event(project, when, "release", tag, row.get("html_url")))
    return events
