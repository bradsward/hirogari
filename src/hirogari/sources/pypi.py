"""PyPI download counts via pypistats.org. No auth required."""

from __future__ import annotations

from datetime import datetime

from hirogari.sources.base import SourceError, http_get_json
from hirogari.store import MetricPoint

_CATEGORY = "without_mirrors"


def collect_downloads(project: str, package: str) -> list[MetricPoint]:
    """Daily download counts for `package` (~180 days of history),
    stored under `project`. `project` is typically the owner/repo being
    tracked; `package` is the PyPI distribution name, which doesn't have
    to match the repo name.
    """
    url = f"https://pypistats.org/api/packages/{package}/overall"
    body, _ = http_get_json(url)
    try:
        rows = body["data"]
    except (KeyError, TypeError) as exc:
        raise SourceError(f"unexpected pypistats response shape for {package!r}") from exc

    points: list[MetricPoint] = []
    for row in rows:
        if row.get("category") != _CATEGORY:
            continue
        try:
            day = datetime.strptime(row["date"], "%Y-%m-%d").date()
            value = float(row["downloads"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SourceError(f"unexpected pypistats row for {package!r}: {row!r}") from exc
        points.append(MetricPoint(project, "pypi", "downloads", day, value))
    return points
