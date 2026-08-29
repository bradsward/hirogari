from __future__ import annotations

import json
from email.message import Message
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


def make_headers(link: str | None = None, remaining: str | None = None) -> Message:
    """Build a minimal email.message.Message the way http.client hands
    response headers back, for tests that don't want to hit the network."""
    msg = Message()
    if link is not None:
        msg["Link"] = link
    if remaining is not None:
        msg["X-RateLimit-Remaining"] = remaining
    return msg
