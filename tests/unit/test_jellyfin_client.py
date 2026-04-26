"""URL-normalization smoke tests for the Jellyfin client."""

from __future__ import annotations

import pytest

from jfin2etv.jellyfin.client import _normalize_jellyfin_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://jellyfin:8096", "http://jellyfin:8096"),
        ("http://jellyfin:8096/", "http://jellyfin:8096"),
        # Browser-tab URL: the web UI's hash route must be stripped.
        ("https://example.com/web/#/home", "https://example.com"),
        # Trailing slashes/queries.
        ("https://host/?foo=1", "https://host"),
        # Already-clean URL with explicit port.
        ("https://example.com:443", "https://example.com:443"),
    ],
)
def test_normalize_jellyfin_url(raw: str, expected: str) -> None:
    assert _normalize_jellyfin_url(raw) == expected
