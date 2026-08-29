from __future__ import annotations

from datetime import date
from email.message import Message

import pytest
from conftest import load_fixture

import hirogari.sources.pypi as pypi
from hirogari.sources.base import SourceError


def test_collect_downloads_filters_to_without_mirrors(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = load_fixture("pypistats_overall.json")
    monkeypatch.setattr(pypi, "http_get_json", lambda url, headers=None: (fixture, Message()))

    points = pypi.collect_downloads("acme/widget", "acme-widget")

    assert len(points) == 3  # the 2 "with_mirrors" rows are dropped
    assert all(
        p.project == "acme/widget" and p.source == "pypi" and p.name == "downloads"
        for p in points
    )
    by_date = {p.date: p.value for p in points}
    assert by_date == {
        date(2026, 1, 1): 120.0,
        date(2026, 1, 2): 95.0,
        date(2026, 1, 3): 210.0,
    }


def test_collect_downloads_raises_on_bad_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pypi, "http_get_json", lambda url, headers=None: ({"nope": []}, Message()))
    with pytest.raises(SourceError):
        pypi.collect_downloads("acme/widget", "acme-widget")
