"""GitHub stargazers, bucketed into daily *new*-star counts."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta

from hirogari.sources.base import SourceError, github_headers, paginate_github
from hirogari.store import MetricPoint

_STAR_ACCEPT = "application/vnd.github.star+json"


def collect_stars(project: str, *, token: str | None = None) -> list[MetricPoint]:
    """Daily new-star counts for `project`, derived from individual
    `starred_at` timestamps.

    Stored as a daily rate (new stars that day), not a cumulative running
    total, so it's the same shape as downloads/views/clones and the
    trend-adjusted lift math treats it consistently. Days between the
    first and last observed star with zero new stars are filled in as
    real zeros — the star API only returns rows for days something
    happened, but a day with nothing happening is data ("zero that day"),
    not a gap ("we don't know"), and analysis.py depends on that
    distinction for its coverage checks.

    The stargazers API caps at 40,000 entries; beyond that this
    undercounts (GitHub's limit, not hirogari's).

    Verified live (2026-08-29): GitHub now returns 401 for every
    unauthenticated request to this endpoint, not just a lower rate
    limit -- `token` is optional in this signature (for interface
    consistency with the other GitHub sources) but is effectively
    required in practice. The CLI checks for `GITHUB_TOKEN` and skips
    this source entirely when it's absent, rather than calling in and
    always getting the same 401.
    """
    if "/" not in project:
        raise SourceError(f"project must be 'owner/repo', got {project!r}")

    headers = github_headers(token)
    headers["Accept"] = _STAR_ACCEPT
    url = f"https://api.github.com/repos/{project}/stargazers?per_page=100"
    rows = paginate_github(url, headers)

    daily: Counter[date] = Counter()
    for row in rows:
        starred_at = row.get("starred_at")
        if not starred_at:
            raise SourceError(f"unexpected stargazer shape for {project!r}: {row!r}")
        try:
            day = datetime.strptime(starred_at, "%Y-%m-%dT%H:%M:%SZ").date()
        except ValueError as exc:
            raise SourceError(f"unexpected starred_at for {project!r}: {starred_at!r}") from exc
        daily[day] += 1

    if not daily:
        return []

    points: list[MetricPoint] = []
    d = min(daily)
    last = max(daily)
    while d <= last:
        points.append(MetricPoint(project, "github", "stars", d, float(daily.get(d, 0))))
        d += timedelta(days=1)
    return points
