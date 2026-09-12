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


def test_collect_stars_gives_clear_message_on_admin_only_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_404(url: str, headers: dict[str, str]) -> list[object]:
        raise SourceError(f"GET {url} -> HTTP 404: Not Found")

    monkeypatch.setattr(gh_stars, "paginate_github", raise_404)

    with pytest.raises(SourceError, match="admins/collaborators"):
        gh_stars.collect_stars("acme/widget", token="tok")


def test_collect_stars_reraises_unrelated_source_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_other(url: str, headers: dict[str, str]) -> list[object]:
        raise SourceError(f"GET {url} -> HTTP 500: Internal Server Error")

    monkeypatch.setattr(gh_stars, "paginate_github", raise_other)

    with pytest.raises(SourceError, match="500"):
        gh_stars.collect_stars("acme/widget", token="tok")
