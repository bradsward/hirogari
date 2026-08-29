from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

import hirogari.cli as cli
from hirogari.store import Event, MetricPoint, Store

EVENT = date(2026, 3, 1)


def _seed_sustained_series(store: Store, project: str) -> None:
    for i in range(1, 31):
        delta = 3.0 if i % 2 == 0 else -3.0
        store.upsert_metric(
            MetricPoint(project, "pypi", "downloads", EVENT - timedelta(days=i), 100.0 + delta)
        )
    for i in range(50):
        store.upsert_metric(
            MetricPoint(project, "pypi", "downloads", EVENT + timedelta(days=i), 180.0)
        )
    store.upsert_event(Event(project, EVENT, "release", "v1.0.0"))


def test_list_on_empty_db(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "hirogari.db"
    code = cli.main(["--db", str(db), "list"])
    assert code == 0
    assert "empty database" in capsys.readouterr().out


def test_event_add_then_list(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "hirogari.db"
    code = cli.main(
        [
            "--db", str(db), "event", "add", "acme/widget",
            "--date", "2026-01-01", "--label", "HN front page", "--kind", "post",
        ]
    )
    assert code == 0

    capsys.readouterr()
    code = cli.main(["--db", str(db), "list"])
    assert code == 0
    out = capsys.readouterr().out
    assert "acme/widget" in out
    assert "1 post" in out


def test_event_add_rejects_bad_date(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "hirogari.db"
    code = cli.main(
        ["--db", str(db), "event", "add", "acme/widget", "--date", "not-a-date", "--label", "x"]
    )
    assert code == 1
    assert "YYYY-MM-DD" in capsys.readouterr().err


def test_lift_end_to_end_table_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "hirogari.db"
    store = Store(db)
    _seed_sustained_series(store, "acme/widget")
    store.close()

    capsys.readouterr()
    code = cli.main(["--db", str(db), "lift", "acme/widget"])
    assert code == 0
    out = capsys.readouterr().out
    assert "SUSTAINED" in out
    assert "v1.0.0" in out


def test_lift_with_no_events_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "hirogari.db"
    Store(db).close()
    code = cli.main(["--db", str(db), "lift", "acme/widget"])
    assert code == 1
    assert "no events" in capsys.readouterr().err


def test_lift_json_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "hirogari.db"
    store = Store(db)
    _seed_sustained_series(store, "acme/widget")
    store.close()

    capsys.readouterr()
    code = cli.main(["--db", str(db), "lift", "acme/widget", "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["classification"] == "SUSTAINED"
    assert payload[0]["event_label"] == "v1.0.0"


def test_lift_csv_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "hirogari.db"
    csv_path = tmp_path / "out.csv"
    store = Store(db)
    _seed_sustained_series(store, "acme/widget")
    store.close()

    code = cli.main(["--db", str(db), "lift", "acme/widget", "--csv", str(csv_path)])
    assert code == 0
    assert csv_path.exists()
    content = csv_path.read_text()
    assert "SUSTAINED" in content
    assert "v1.0.0" in content


def test_report_covers_every_stored_metric(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "hirogari.db"
    store = Store(db)
    _seed_sustained_series(store, "acme/widget")
    # a second metric under the same project
    for i in range(1, 31):
        store.upsert_metric(
            MetricPoint("acme/widget", "github", "stars", EVENT - timedelta(days=i), 10.0)
        )
    for i in range(50):
        store.upsert_metric(
            MetricPoint("acme/widget", "github", "stars", EVENT + timedelta(days=i), 10.0)
        )
    store.close()

    capsys.readouterr()
    code = cli.main(["--db", str(db), "report", "acme/widget", "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    metric_names = {row["metric_name"] for row in payload}
    assert metric_names == {"pypi.downloads", "github.stars"}


def test_study_end_to_end_with_monkeypatched_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    project = "acme/widget"

    def fake_releases(p: str, *, token: str | None = None) -> list[Event]:
        return [Event(p, EVENT, "release", "v1.0.0")]

    def fake_stars(p: str, *, token: str | None = None) -> list[MetricPoint]:
        points = []
        for i in range(1, 31):
            points.append(MetricPoint(p, "github", "stars", EVENT - timedelta(days=i), 10.0))
        for i in range(50):
            points.append(MetricPoint(p, "github", "stars", EVENT + timedelta(days=i), 25.0))
        return points

    def fake_pypi(p: str, package: str) -> list[MetricPoint]:
        points = []
        for i in range(1, 31):
            delta = 3.0 if i % 2 == 0 else -3.0
            when = EVENT - timedelta(days=i)
            points.append(MetricPoint(p, "pypi", "downloads", when, 100.0 + delta))
        for i in range(50):
            points.append(MetricPoint(p, "pypi", "downloads", EVENT + timedelta(days=i), 180.0))
        return points

    monkeypatch.setattr(cli.github_releases, "collect_releases", fake_releases)
    monkeypatch.setattr(cli.github_stars, "collect_stars", fake_stars)
    monkeypatch.setattr(cli.pypi, "collect_downloads", fake_pypi)

    projects_file = tmp_path / "projects.txt"
    projects_file.write_text(f"{project},acme-widget\n# a comment line\n\n")
    db = tmp_path / "hirogari.db"
    csv_path = tmp_path / "study.csv"

    code = cli.main(["--db", str(db), "study", str(projects_file), "--csv", str(csv_path)])
    assert code == 0
    assert csv_path.exists()
    content = csv_path.read_text()
    assert project in content
    assert "SUSTAINED" in content


def test_study_reports_nonzero_on_source_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hirogari.sources.base import SourceError

    def raise_error(p: str, *, token: str | None = None) -> list[Event]:
        raise SourceError("simulated failure")

    monkeypatch.setattr(cli.github_releases, "collect_releases", raise_error)
    monkeypatch.setattr(cli.github_stars, "collect_stars", lambda p, *, token=None: [])

    projects_file = tmp_path / "projects.txt"
    projects_file.write_text("acme/widget\n")
    db = tmp_path / "hirogari.db"

    code = cli.main(["--db", str(db), "study", str(projects_file)])
    assert code == 1
