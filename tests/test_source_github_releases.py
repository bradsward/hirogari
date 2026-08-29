from __future__ import annotations

from datetime import date

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
