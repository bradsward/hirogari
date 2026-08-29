from __future__ import annotations

from datetime import date

import pytest
from conftest import load_fixture

import hirogari.sources.github_stars as gh_stars
from hirogari.sources.base import SourceError


def test_collect_stars_buckets_daily_and_fills_zero_gap(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = load_fixture("github_stargazers.json")
    monkeypatch.setattr(gh_stars, "paginate_github", lambda url, headers: fixture)

    points = gh_stars.collect_stars("acme/widget")

    by_date = {p.date: p.value for p in points}
    assert by_date == {
        date(2026, 1, 1): 2.0,  # alice + bob
        date(2026, 1, 2): 0.0,  # real zero, not a gap -- no one starred that day
        date(2026, 1, 3): 1.0,  # carol
    }
    assert all(p.source == "github" and p.name == "stars" for p in points)


def test_collect_stars_empty_when_no_stargazers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gh_stars, "paginate_github", lambda url, headers: [])
    assert gh_stars.collect_stars("acme/widget") == []


def test_collect_stars_rejects_bad_project_format() -> None:
    with pytest.raises(SourceError):
        gh_stars.collect_stars("not-a-repo-id")
