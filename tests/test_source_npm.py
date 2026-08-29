from __future__ import annotations

from datetime import date
from email.message import Message

import pytest
from conftest import load_fixture

import hirogari.sources.npm as npm
from hirogari.sources.base import SourceError


def test_collect_downloads_parses_range(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = load_fixture("npm_downloads_range.json")
    captured_url = {}

    def fake_get(url: str, headers: dict[str, str] | None = None) -> tuple[object, Message]:
        captured_url["url"] = url
        return fixture, Message()

    monkeypatch.setattr(npm, "http_get_json", fake_get)

    points = npm.collect_downloads("acme/widget", "acme-widget")

    assert "acme-widget" in captured_url["url"]
    assert len(points) == 3
    assert all(p.source == "npm" and p.name == "downloads" for p in points)
    assert {p.date: p.value for p in points} == {
        date(2026, 1, 1): 10.0,
        date(2026, 1, 2): 12.0,
        date(2026, 1, 3): 8.0,
    }


def test_collect_downloads_raises_on_bad_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(npm, "http_get_json", lambda url, headers=None: ({"nope": []}, Message()))
    with pytest.raises(SourceError):
        npm.collect_downloads("acme/widget", "acme-widget")
