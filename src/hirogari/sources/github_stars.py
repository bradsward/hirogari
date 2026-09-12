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

    Two real, live-verified stages of this endpoint tightening, about two
    weeks apart:

    2026-08-29 — GitHub started returning 401 for every unauthenticated
    request (not just a lower rate limit).

    2026-09-12 — with a valid, authenticated (zero-scope classic) token,
    it now 404s instead: per GitHub's own docs
    (docs.github.com/rest/activity/starring), "access to the stargazers
    listing endpoints [is] limited to admins and collaborators" as of
    July 2026. That means **no token fixes this for a project you don't
    administer** — it's not a rate-limit or auth-strength problem, it's
    a permission wall.

    Tested directly against hirogari's *own* repo with that same
    zero-scope token: still 404. A zero-scope classic PAT proves you're
    an authenticated user but doesn't itself carry delegated repo
    permission, even for a repo you own — GitHub's traffic endpoint
    (`github_traffic.py`) fails the same way with the same token,
    explicitly citing "Must have push access to repository". A token
    with actual `repo` scope would very likely fix this for your own
    repos (that's what such scopes exist for), but that's inference from
    the API's own error message, not something verified here — don't
    repeat the earlier mistake of asserting this source "still works for
    repos you admin" without having actually tried it with a scope that
    could prove it. See notes/2026-09-12-github-stars-locked-down.md.
    """
    if "/" not in project:
        raise SourceError(f"project must be 'owner/repo', got {project!r}")

    headers = github_headers(token)
    headers["Accept"] = _STAR_ACCEPT
    url = f"https://api.github.com/repos/{project}/stargazers?per_page=100"
    try:
        rows = paginate_github(url, headers)
    except SourceError as exc:
        if "stargazers" in str(exc) and "404" in str(exc):
            raise SourceError(
                f"GitHub restricts stargazer listings to repo admins/collaborators as of "
                f"July 2026 -- {project!r} can't be read this way regardless of token, "
                "unless you administer that repo. See docs.github.com/rest/activity/starring."
            ) from exc
        raise

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
