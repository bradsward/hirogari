"""GitHub traffic (views/clones) -- optional, requires a token with push
access to the repo. GitHub only exposes 14 days of history per call, so
this is meant to be run repeatedly (e.g. via `collect`, run at least every
two weeks) and accumulated into the local DB through the store's
idempotent upsert -- a single run can never backfill more than 14 days.
"""

from __future__ import annotations

from datetime import datetime

from hirogari.sources.base import SourceError, github_headers, http_get_json
from hirogari.store import MetricPoint


def collect_traffic(project: str, *, token: str) -> list[MetricPoint]:
    if "/" not in project:
        raise SourceError(f"project must be 'owner/repo', got {project!r}")
    headers = github_headers(token)
    return [
        *_collect_one(project, "views", headers),
        *_collect_one(project, "clones", headers),
    ]


def _collect_one(project: str, name: str, headers: dict[str, str]) -> list[MetricPoint]:
    url = f"https://api.github.com/repos/{project}/traffic/{name}"
    body, _ = http_get_json(url, headers)
    try:
        rows = body[name]
    except (KeyError, TypeError) as exc:
        raise SourceError(
            f"unexpected GitHub traffic response shape for {project!r} ({name})"
        ) from exc

    points: list[MetricPoint] = []
    for row in rows:
        try:
            day = datetime.strptime(row["timestamp"], "%Y-%m-%dT%H:%M:%SZ").date()
            value = float(row["count"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SourceError(f"unexpected GitHub traffic row for {project!r}: {row!r}") from exc
        points.append(MetricPoint(project, "github", name, day, value))
    return points
