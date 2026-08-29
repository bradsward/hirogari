from __future__ import annotations

from datetime import date
from email.message import Message

import pytest
from conftest import load_fixture

import hirogari.sources.github_traffic as gh_traffic
from hirogari.sources.base import SourceError


def test_collect_traffic_merges_views_and_clones(monkeypatch: pytest.MonkeyPatch) -> None:
    views = load_fixture("github_traffic_views.json")
    clones = load_fixture("github_traffic_clones.json")

    def fake_get(url: str, headers: dict[str, str] | None = None) -> tuple[object, Message]:
        return (views if url.endswith("/views") else clones), Message()

    monkeypatch.setattr(gh_traffic, "http_get_json", fake_get)

    points = gh_traffic.collect_traffic("acme/widget", token="tok")

    by_name_date = {(p.name, p.date): p.value for p in points}
    assert by_name_date == {
        ("views", date(2026, 2, 1)): 50.0,
        ("views", date(2026, 2, 2)): 78.0,
        ("clones", date(2026, 2, 1)): 15.0,
        ("clones", date(2026, 2, 2)): 15.0,
    }
    assert all(p.source == "github" for p in points)


def test_collect_traffic_rejects_bad_project_format() -> None:
    with pytest.raises(SourceError):
        gh_traffic.collect_traffic("not-a-repo-id", token="tok")


def test_collect_traffic_raises_on_bad_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    bad_body = ({"nope": []}, Message())
    monkeypatch.setattr(gh_traffic, "http_get_json", lambda url, headers=None: bad_body)
    with pytest.raises(SourceError):
        gh_traffic.collect_traffic("acme/widget", token="tok")
