from __future__ import annotations

from datetime import date
from pathlib import Path

from hirogari.store import Event, MetricPoint, Store


def make_store(tmp_path: Path) -> Store:
    return Store(tmp_path / "test.db")


def test_upsert_metrics_idempotent(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    point = MetricPoint("acme/widget", "pypi", "downloads", date(2026, 1, 1), 100.0)

    store.upsert_metric(point)
    store.upsert_metric(point)  # re-run: must not duplicate

    series = store.get_metric_series("acme/widget", "pypi", "downloads")
    assert series == {date(2026, 1, 1): 100.0}


def test_upsert_metrics_updates_value_on_conflict(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    d = date(2026, 1, 1)
    store.upsert_metric(MetricPoint("acme/widget", "pypi", "downloads", d, 100.0))
    store.upsert_metric(MetricPoint("acme/widget", "pypi", "downloads", d, 250.0))

    series = store.get_metric_series("acme/widget", "pypi", "downloads")
    assert series == {d: 250.0}


def test_get_metric_series_orders_by_date_and_skips_gaps(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.upsert_metrics(
        [
            MetricPoint("acme/widget", "pypi", "downloads", date(2026, 1, 3), 30.0),
            MetricPoint("acme/widget", "pypi", "downloads", date(2026, 1, 1), 10.0),
        ]
    )
    series = store.get_metric_series("acme/widget", "pypi", "downloads")
    assert list(series.keys()) == [date(2026, 1, 1), date(2026, 1, 3)]
    assert date(2026, 1, 2) not in series


def test_series_is_scoped_to_project_source_name(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    d = date(2026, 1, 1)
    store.upsert_metrics(
        [
            MetricPoint("acme/widget", "pypi", "downloads", d, 10.0),
            MetricPoint("acme/widget", "npm", "downloads", d, 20.0),
            MetricPoint("acme/widget", "github", "stars", d, 5.0),
            MetricPoint("other/project", "pypi", "downloads", d, 999.0),
        ]
    )
    assert store.get_metric_series("acme/widget", "pypi", "downloads") == {d: 10.0}
    assert store.get_metric_series("acme/widget", "npm", "downloads") == {d: 20.0}
    assert store.get_metric_series("acme/widget", "github", "stars") == {d: 5.0}


def test_upsert_events_idempotent(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    event = Event("acme/widget", date(2026, 1, 1), "release", "v1.0.0", "https://x/v1.0.0")
    store.upsert_event(event)
    store.upsert_event(event)

    events = store.get_events("acme/widget")
    assert events == [event]


def test_upsert_event_updates_url_on_conflict(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    d = date(2026, 1, 1)
    store.upsert_event(Event("acme/widget", d, "release", "v1.0.0", "https://old"))
    store.upsert_event(Event("acme/widget", d, "release", "v1.0.0", "https://new"))

    events = store.get_events("acme/widget")
    assert len(events) == 1
    assert events[0].url == "https://new"


def test_events_filtered_by_kind(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.upsert_events(
        [
            Event("acme/widget", date(2026, 1, 1), "release", "v1.0.0"),
            Event("acme/widget", date(2026, 1, 2), "post", "HN front page"),
        ]
    )
    releases = store.get_events("acme/widget", kind="release")
    assert [e.label for e in releases] == ["v1.0.0"]


def test_list_projects_union_of_metric_and_event(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.upsert_metric(
        MetricPoint("acme/widget", "pypi", "downloads", date(2026, 1, 1), 1.0)
    )
    store.upsert_event(Event("other/project", date(2026, 1, 1), "manual", "note"))

    assert store.list_projects() == ["acme/widget", "other/project"]


def test_list_metrics_summarizes_series(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.upsert_metrics(
        [
            MetricPoint("acme/widget", "pypi", "downloads", date(2026, 1, 1), 10.0),
            MetricPoint("acme/widget", "pypi", "downloads", date(2026, 1, 2), 20.0),
        ]
    )
    summary = store.list_metrics("acme/widget")
    assert summary == [("pypi", "downloads", "2026-01-01", "2026-01-02", 2)]


def test_reopening_existing_db_preserves_data(tmp_path: Path) -> None:
    db_path = tmp_path / "persist.db"
    store = Store(db_path)
    store.upsert_metric(
        MetricPoint("acme/widget", "pypi", "downloads", date(2026, 1, 1), 42.0)
    )
    store.close()

    reopened = Store(db_path)
    assert reopened.get_metric_series("acme/widget", "pypi", "downloads") == {
        date(2026, 1, 1): 42.0
    }
