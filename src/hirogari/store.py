"""SQLite data layer for hirogari.

Two tables, exactly as specified: `metric` (time series points from a
source) and `event` (things that happened on a date — releases, posts,
docs changes, manual annotations). Both are upserted on their full primary
key so re-running collection is idempotent: it updates values in place
rather than duplicating rows.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS metric (
  project TEXT NOT NULL,
  source  TEXT NOT NULL,
  name    TEXT NOT NULL,
  date    TEXT NOT NULL,
  value   REAL NOT NULL,
  PRIMARY KEY (project, source, name, date)
);

CREATE TABLE IF NOT EXISTS event (
  project TEXT NOT NULL,
  date    TEXT NOT NULL,
  kind    TEXT NOT NULL,
  label   TEXT NOT NULL,
  url     TEXT,
  PRIMARY KEY (project, date, kind, label)
);

CREATE INDEX IF NOT EXISTS idx_metric_series ON metric (project, source, name);
CREATE INDEX IF NOT EXISTS idx_event_project ON event (project);
"""

DEFAULT_DB_PATH = "hirogari.db"


def _to_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


@dataclass(frozen=True, slots=True)
class MetricPoint:
    project: str
    source: str
    name: str
    date: date
    value: float


@dataclass(frozen=True, slots=True)
class Event:
    project: str
    date: date
    kind: str
    label: str
    url: str | None = None


class Store:
    """Thin wrapper around a single SQLite connection.

    Not thread-safe beyond what sqlite3 itself provides — hirogari is a
    single-process CLI, so that's not a real constraint.
    """

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- writes ----------------------------------------------------------

    def upsert_metrics(self, points: Iterable[MetricPoint]) -> int:
        """Insert or update metric points. Returns the number processed."""
        rows = [
            (p.project, p.source, p.name, p.date.isoformat(), p.value) for p in points
        ]
        if not rows:
            return 0
        self._conn.executemany(
            """
            INSERT INTO metric (project, source, name, date, value)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (project, source, name, date)
            DO UPDATE SET value = excluded.value
            """,
            rows,
        )
        self._conn.commit()
        return len(rows)

    def upsert_metric(self, point: MetricPoint) -> None:
        self.upsert_metrics([point])

    def upsert_events(self, events: Iterable[Event]) -> int:
        rows = [(e.project, e.date.isoformat(), e.kind, e.label, e.url) for e in events]
        if not rows:
            return 0
        self._conn.executemany(
            """
            INSERT INTO event (project, date, kind, label, url)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (project, date, kind, label)
            DO UPDATE SET url = excluded.url
            """,
            rows,
        )
        self._conn.commit()
        return len(rows)

    def upsert_event(self, event: Event) -> None:
        self.upsert_events([event])

    # -- reads -------------------------------------------------------------

    def get_metric_series(self, project: str, source: str, name: str) -> dict[date, float]:
        """Return the stored series as {date: value}, ordered by date.

        Missing days are simply absent from the dict — hirogari never
        synthesizes zeros for gaps, so downstream code (analysis.py) can
        tell "no data that day" apart from "zero downloads that day".
        """
        cur = self._conn.execute(
            """
            SELECT date, value FROM metric
            WHERE project = ? AND source = ? AND name = ?
            ORDER BY date
            """,
            (project, source, name),
        )
        return {_to_date(row[0]): row[1] for row in cur.fetchall()}

    def get_events(self, project: str, kind: str | None = None) -> list[Event]:
        if kind is None:
            cur = self._conn.execute(
                "SELECT project, date, kind, label, url FROM event "
                "WHERE project = ? ORDER BY date",
                (project,),
            )
        else:
            cur = self._conn.execute(
                "SELECT project, date, kind, label, url FROM event "
                "WHERE project = ? AND kind = ? ORDER BY date",
                (project, kind),
            )
        return [
            Event(project=row[0], date=_to_date(row[1]), kind=row[2], label=row[3], url=row[4])
            for row in cur.fetchall()
        ]

    def list_projects(self) -> list[str]:
        cur = self._conn.execute(
            "SELECT project FROM metric UNION SELECT project FROM event ORDER BY project"
        )
        return [row[0] for row in cur.fetchall()]

    def list_metrics(self, project: str) -> list[tuple[str, str, str, str, int]]:
        """Distinct (source, name) series for a project, with date range and count."""
        cur = self._conn.execute(
            """
            SELECT source, name, MIN(date), MAX(date), COUNT(*)
            FROM metric WHERE project = ?
            GROUP BY source, name
            ORDER BY source, name
            """,
            (project,),
        )
        return [tuple(row) for row in cur.fetchall()]
