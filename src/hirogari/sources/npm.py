"""npm download counts via the npm registry API. No auth required."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from hirogari.sources.base import SourceError, http_get_json
from hirogari.store import MetricPoint


def collect_downloads(project: str, package: str, *, days: int = 365) -> list[MetricPoint]:
    """Daily download counts for `package` over the last `days` days.

    The npm registry's range endpoint lags by about a day, so the range
    ends yesterday rather than today (today's count would otherwise be
    perpetually partial/zero and read as a gap).
    """
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    url = f"https://api.npmjs.org/downloads/range/{start.isoformat()}:{end.isoformat()}/{package}"
    body, _ = http_get_json(url)
    try:
        rows = body["downloads"]
    except (KeyError, TypeError) as exc:
        raise SourceError(f"unexpected npm registry response shape for {package!r}") from exc

    points: list[MetricPoint] = []
    for row in rows:
        try:
            day = datetime.strptime(row["day"], "%Y-%m-%d").date()
            value = float(row["downloads"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SourceError(f"unexpected npm registry row for {package!r}: {row!r}") from exc
        points.append(MetricPoint(project, "npm", "downloads", day, value))
    return points
