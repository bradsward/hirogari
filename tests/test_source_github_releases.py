from __future__ import annotations

from datetime import date
from email.message import Message
from typing import Any

import pytest
from conftest import load_fixture

import hirogari.sources.github_releases as gh_releases
from hirogari.sources.base import SourceError


def test_collect_releases_paginates_and_skips_drafts(monkeypatch: pytest.MonkeyPatch) -> None:
    page1 = load_fixture("github_releases_page1.json")
    page2 = load_fixture("github_releases_page2.json")
    monkeypatch.setattr(gh_releases, "paginate_github", lambda url, headers: page1 + page2)

    events = gh_releases.collect_releases("acme/widget")

    labels = {e.label: e.date for e in events}
    assert labels == {
        "v1.1.0": date(2026, 2, 1),
        "v1.0.0": date(2026, 1, 1),
    }
    assert "v1.0.0-draft" not in labels  # published_at was null -> skipped
    assert all(e.kind == "release" and e.project == "acme/widget" for e in events)


def test_collect_releases_rejects_bad_project_format() -> None:
    with pytest.raises(SourceError):
        gh_releases.collect_releases("not-a-repo-id")


def test_collect_releases_skips_tag_fallback_when_releases_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page1 = load_fixture("github_releases_page1.json")
    page2 = load_fixture("github_releases_page2.json")

    def fake_paginate(url: str, headers: dict[str, str]) -> list[Any]:
        assert "tags" not in url  # must not fall back when releases already have data
        return page1 + page2

    monkeypatch.setattr(gh_releases, "paginate_github", fake_paginate)
    events = gh_releases.collect_releases("acme/widget", token="tok")
    assert len(events) == 2


def test_collect_releases_no_tag_fallback_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_paginate(url: str, headers: dict[str, str]) -> list[Any]:
        assert "tags" not in url  # unauthenticated: must not attempt the tag fallback at all
        return []

    monkeypatch.setattr(gh_releases, "paginate_github", fake_paginate)
    assert gh_releases.collect_releases("acme/widget") == []


def test_collect_releases_falls_back_to_tags_when_empty_and_token_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tags = load_fixture("github_tags.json")
    commits = {
        "https://api.github.com/repos/acme/widget/commits/aaa111": (
            {"commit": {"committer": {"date": "2026-07-22T10:00:00Z"}}},
            Message(),
        ),
        "https://api.github.com/repos/acme/widget/commits/bbb222": (
            {"commit": {"committer": {"date": "2026-01-01T09:00:00Z"}}},
            Message(),
        ),
    }

    def fake_paginate(url: str, headers: dict[str, str]) -> list[Any]:
        if "releases" in url:
            return []
        assert "tags" in url
        return tags

    def fake_get(url: str, headers: dict[str, str] | None = None) -> tuple[Any, Message]:
        return commits[url]

    monkeypatch.setattr(gh_releases, "paginate_github", fake_paginate)
    monkeypatch.setattr(gh_releases, "http_get_json", fake_get)
    monkeypatch.setattr(gh_releases, "check_remaining", lambda headers: None)

    events = gh_releases.collect_releases("acme/widget", token="tok")

    by_label = {e.label: e.date for e in events}
    assert by_label == {
        "2026.07.22": date(2026, 7, 22),
        "2026.01.01": date(2026, 1, 1),
    }
    assert all(e.kind == "release" and e.project == "acme/widget" for e in events)
    assert all("tree" in (e.url or "") for e in events)


def test_collect_releases_falls_back_raises_on_bad_tag_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        gh_releases,
        "paginate_github",
        lambda url, headers: [] if "releases" in url else [{"nope": "no commit field"}],
    )
    with pytest.raises(SourceError):
        gh_releases.collect_releases("acme/widget", token="tok")
