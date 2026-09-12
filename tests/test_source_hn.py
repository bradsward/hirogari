from __future__ import annotations

from datetime import date
from email.message import Message
from typing import Any

import pytest
from conftest import load_fixture

import hirogari.sources.hn as hn
from hirogari.sources.base import SourceError


def test_collect_posts_filters_to_direct_url_and_default_points(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = load_fixture("hn_search.json")
    monkeypatch.setattr(hn, "http_get_json", lambda url: (fixture, Message()))

    events = hn.collect_posts("acme/widget")

    assert len(events) == 1
    e = events[0]
    assert e.label == "Show HN: Acme Widget - a thing"
    assert e.date == date(2026, 1, 15)
    assert e.kind == "post"
    assert e.url == "https://news.ycombinator.com/item?id=111"


def test_collect_posts_excludes_text_only_mentions(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = load_fixture("hn_search.json")
    monkeypatch.setattr(hn, "http_get_json", lambda url: (fixture, Message()))

    events = hn.collect_posts("acme/widget", min_points=0)  # points can't save a url mismatch

    labels = {e.label for e in events}
    assert "Ask HN: does anyone use Acme Widget?" not in labels  # url field doesn't match


def test_collect_posts_respects_custom_min_points(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = load_fixture("hn_search.json")
    monkeypatch.setattr(hn, "http_get_json", lambda url: (fixture, Message()))

    events = hn.collect_posts("acme/widget", min_points=10)

    labels = {e.label for e in events}
    assert labels == {"Show HN: Acme Widget - a thing", "Acme Widget hits 1.0"}


def test_collect_posts_paginates(monkeypatch: pytest.MonkeyPatch) -> None:
    page1 = {
        "hits": [
            {
                "objectID": "1",
                "title": "post one",
                "url": "https://github.com/acme/widget",
                "points": 100,
                "created_at_i": 1700000000,
            }
        ],
        "nbPages": 2,
    }
    page2 = {
        "hits": [
            {
                "objectID": "2",
                "title": "post two",
                "url": "https://github.com/acme/widget",
                "points": 100,
                "created_at_i": 1700000100,
            }
        ],
        "nbPages": 2,
    }
    pages = [page1, page2]

    def fake_get(url: str) -> tuple[dict[str, Any], Message]:
        return pages.pop(0), Message()

    monkeypatch.setattr(hn, "http_get_json", fake_get)

    events = hn.collect_posts("acme/widget")
    assert {e.label for e in events} == {"post one", "post two"}


def test_collect_posts_rejects_bad_project_format() -> None:
    with pytest.raises(SourceError):
        hn.collect_posts("not-a-repo-id")


def test_collect_posts_raises_on_bad_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hn, "http_get_json", lambda url: ({"nope": []}, Message()))
    with pytest.raises(SourceError):
        hn.collect_posts("acme/widget")


def test_collect_posts_raises_on_bad_hit_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    body = {"hits": [{"objectID": "1"}], "nbPages": 1}  # missing created_at_i
    monkeypatch.setattr(hn, "http_get_json", lambda url: (body, Message()))
    with pytest.raises(SourceError):
        hn.collect_posts("acme/widget")
