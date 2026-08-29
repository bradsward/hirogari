from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from conftest import make_headers

from hirogari.sources.base import (
    RateLimitError,
    SourceError,
    check_remaining,
    github_headers,
    http_get_json,
    paginate_github,
)


class _FakeResponse:
    def __init__(self, body: Any, headers: Any) -> None:
        self._body = json.dumps(body).encode()
        self.headers = headers

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def test_http_get_json_returns_body_and_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    headers = make_headers()
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda req, timeout=30: _FakeResponse({"ok": True}, headers)
    )
    body, resp_headers = http_get_json("https://example.invalid/x")
    assert body == {"ok": True}
    assert resp_headers is headers


def test_http_get_json_raises_source_error_on_bad_json(monkeypatch: pytest.MonkeyPatch) -> None:
    class _BadResponse:
        headers = make_headers()

        def read(self) -> bytes:
            return b"not json"

        def __enter__(self) -> _BadResponse:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=30: _BadResponse())
    with pytest.raises(SourceError):
        http_get_json("https://example.invalid/x")


def test_http_get_json_raises_source_error_on_generic_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_error(req: Any, timeout: int = 30) -> Any:
        raise urllib.error.HTTPError(
            "https://example.invalid/x", 404, "Not Found", make_headers(), io.BytesIO(b"")
        )

    monkeypatch.setattr(urllib.request, "urlopen", raise_error)
    with pytest.raises(SourceError):
        http_get_json("https://example.invalid/x")


def test_http_get_json_raises_rate_limit_error_on_exhausted_403(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_at = int((datetime.now(UTC) + timedelta(minutes=5)).timestamp())
    headers = make_headers(remaining="0")
    headers["X-RateLimit-Reset"] = str(reset_at)

    def raise_error(req: Any, timeout: int = 30) -> Any:
        raise urllib.error.HTTPError(
            "https://api.github.com/x", 403, "Forbidden", headers, io.BytesIO(b"")
        )

    monkeypatch.setattr(urllib.request, "urlopen", raise_error)
    with pytest.raises(RateLimitError):
        http_get_json("https://api.github.com/x")


def test_check_remaining_raises_when_exhausted() -> None:
    reset_at = int((datetime.now(UTC) + timedelta(minutes=1)).timestamp())
    headers = make_headers(remaining="0")
    headers["X-RateLimit-Reset"] = str(reset_at)
    with pytest.raises(RateLimitError):
        check_remaining(headers)


def test_check_remaining_passes_when_budget_left() -> None:
    headers = make_headers(remaining="59")
    check_remaining(headers)  # must not raise


def test_github_headers_include_auth_only_with_token() -> None:
    assert "Authorization" not in github_headers(None)
    assert github_headers("secret")["Authorization"] == "Bearer secret"


def test_paginate_github_follows_link_header(monkeypatch: pytest.MonkeyPatch) -> None:
    page1_headers = make_headers(link='<https://api.github.com/x?page=2>; rel="next"')
    page2_headers = make_headers()
    responses = [
        _FakeResponse([{"id": 1}], page1_headers),
        _FakeResponse([{"id": 2}], page2_headers),
    ]

    def fake_urlopen(req: Any, timeout: int = 30) -> Any:
        return responses.pop(0)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    results = paginate_github("https://api.github.com/x", {})
    assert results == [{"id": 1}, {"id": 2}]


def test_paginate_github_raises_source_error_on_non_array(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_response = _FakeResponse({"not": "a list"}, make_headers())
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=30: fake_response)
    with pytest.raises(SourceError):
        paginate_github("https://api.github.com/x", {})
