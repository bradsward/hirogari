"""GitHub releases, turned into `release` events.

Falls back to tags when a project has zero GitHub Releases -- some
projects (verified live 2026-08-29 against certifi and cryptography, see
notes/2026-08-29-first-cross-project-study.md) tag every version without
ever creating a Release object, so the releases API genuinely returns an
empty list for them even though they have real version history.
"""

from __future__ import annotations

from datetime import datetime

from hirogari.sources.base import (
    SourceError,
    check_remaining,
    github_headers,
    http_get_json,
    paginate_github,
)
from hirogari.store import Event


def collect_releases(project: str, *, token: str | None = None) -> list[Event]:
    """Fetch all releases for `project` ("owner/repo") as `release` events.

    Draft releases (`published_at` is null) are skipped: a draft was
    never actually visible to users, so it can't have moved adoption and
    has no publish date to anchor an event on anyway.

    If the releases API returns nothing at all, falls back to tags (see
    `_collect_from_tags`) -- but only when `token` is given. Resolving
    each tag's date costs one extra API request per tag (GitHub's REST
    API has no bulk tag-date endpoint), which a project with 60+ tags
    would exhaust the entire 60/hr unauthenticated budget on by itself.
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

    if events or token is None:
        return events
    return _collect_from_tags(project, token=token)


def _collect_from_tags(project: str, *, token: str) -> list[Event]:
    headers = github_headers(token)
    tags = paginate_github(f"https://api.github.com/repos/{project}/tags?per_page=100", headers)

    events: list[Event] = []
    for tag in tags:
        try:
            name = tag["name"]
            commit_url = tag["commit"]["url"]
        except (KeyError, TypeError) as exc:
            raise SourceError(f"unexpected tag shape for {project!r}: {tag!r}") from exc

        commit_body, commit_headers = http_get_json(commit_url, headers)
        check_remaining(commit_headers)
        try:
            date_str = commit_body["commit"]["committer"]["date"]
            when = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ").date()
        except (KeyError, TypeError, ValueError) as exc:
            raise SourceError(
                f"unexpected commit shape for {project!r} tag {name!r}: {commit_body!r}"
            ) from exc
        events.append(Event(project, when, "release", name, f"https://github.com/{project}/tree/{name}"))
    return events
