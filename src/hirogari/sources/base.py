"""Shared HTTP + error-handling plumbing for hirogari.sources.*.

See `hirogari.sources` (this package's `__init__.py`) for why there's no
shared base class here.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import UTC, datetime
from email.message import Message
from typing import Any

USER_AGENT = "hirogari/0.1.0 (public-data OSS adoption measurement CLI)"


class SourceError(Exception):
    """A source couldn't produce data: network failure, bad HTTP status,
    unexpected response shape. Callers (the CLI) catch this to print a
    clear message and exit non-zero instead of showing a stack trace."""


class RateLimitError(SourceError):
    def __init__(self, reset_at: datetime) -> None:
        self.reset_at = reset_at
        wait_seconds = max(0, int((reset_at - datetime.now(UTC)).total_seconds()))
        super().__init__(
            "GitHub API rate limit exhausted. "
            f"Resets at {reset_at.isoformat()} (~{wait_seconds}s from now). "
            "Set the GITHUB_TOKEN env var to raise the limit from 60/hr to 5,000/hr."
        )


def http_get_json(url: str, headers: dict[str, str] | None = None) -> tuple[Any, Message]:
    """GET `url`, return (parsed JSON body, response headers).

    Raises SourceError (or RateLimitError, a subclass) on any network,
    HTTP-status, or JSON-decode failure, with a message that names the
    URL so failures are diagnosable without a stack trace.
    """
    request_headers = {"User-Agent": USER_AGENT, **(headers or {})}
    req = urllib.request.Request(url, headers=request_headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 -- fixed https APIs
            body = resp.read()
            resp_headers = resp.headers
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            check_remaining(exc.headers)
        raise SourceError(f"GET {url} -> HTTP {exc.code}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise SourceError(f"GET {url} failed: {exc.reason}") from exc

    try:
        return json.loads(body), resp_headers
    except json.JSONDecodeError as exc:
        raise SourceError(f"GET {url} returned invalid JSON: {exc}") from exc


def check_remaining(headers: Message) -> None:
    """Raise RateLimitError if `headers` shows the rate-limit budget is
    exhausted. Called both on a 403 response (to give a specific message
    instead of a generic "403 Forbidden") and proactively after every
    successful paginated response (so a long fetch fails fast with a
    clear message instead of burning the last request on a page that
    then 403s)."""
    remaining = headers.get("X-RateLimit-Remaining")
    reset = headers.get("X-RateLimit-Reset")
    if remaining == "0" and reset is not None:
        raise RateLimitError(datetime.fromtimestamp(int(reset), tz=UTC))


def github_headers(token: str | None) -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def paginate_github(url: str, headers: dict[str, str]) -> list[Any]:
    """Follow GitHub's `Link: <...>; rel="next"` pagination, concatenating
    each page's JSON array. Checks the rate-limit headers after every
    page so a long paginated fetch fails fast with a clear message
    instead of burning the last request on a page that then 403s."""
    results: list[Any] = []
    next_url: str | None = url
    while next_url:
        body, resp_headers = http_get_json(next_url, headers)
        if not isinstance(body, list):
            raise SourceError(f"GET {next_url} expected a JSON array, got {type(body).__name__}")
        results.extend(body)
        check_remaining(resp_headers)
        next_url = _next_link(resp_headers.get("Link"))
    return results


def _next_link(link_header: str | None) -> str | None:
    if not link_header:
        return None
    for part in link_header.split(","):
        segment = part.strip()
        if segment.endswith('rel="next"'):
            start = segment.find("<") + 1
            end = segment.find(">")
            if start > 0 and end > start:
                return segment[start:end]
    return None
