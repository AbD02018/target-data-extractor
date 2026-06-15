"""Test the bypass layer (curl_cffi tier is the default and we can run it)."""

from __future__ import annotations

import pytest

from target_data_extractor.bypass import BypassConfig, BypassResponse
from target_data_extractor.exceptions import AntiBotError


def test_config_defaults():
    c = BypassConfig()
    assert c.strategy == "auto"
    assert c.timeout == 30
    assert c.max_retries == 3
    assert len(c.user_agents) > 0


def test_config_random_ua_varies():
    c = BypassConfig()
    uas = {c.get_random_ua() for _ in range(20)}
    assert len(uas) > 1  # random pool actually returns different UAs


def test_response_is_blocked_on_cloudflare_marker():
    resp = BypassResponse(
        url="https://example.com",
        status_code=403,
        text="<html>Just a moment... Checking your browser before accessing example.com.</html>",
        content=b"",
        headers={},
        strategy_used="curl_cffi",
        elapsed_seconds=0.1,
    )
    assert resp.is_blocked is True
    assert resp.ok is False


def test_response_not_blocked_on_200():
    resp = BypassResponse(
        url="https://example.com",
        status_code=200,
        text="<html>Hello</html>",
        content=b"<html>Hello</html>",
        headers={"content-type": "text/html"},
        strategy_used="curl_cffi",
        elapsed_seconds=0.1,
    )
    assert resp.is_blocked is False
    assert resp.ok is True


@pytest.mark.asyncio
@pytest.mark.network
async def test_get_https_example():
    """Real network test - skipped if no network. Verifies bypass curl_cffi tier.

    Uses YesWeHack's programs page (public, has bug-bounty signals in HTML).
    Note: YesWeHack is JS-rendered, so curl_cffi gets a small HTML shell.
    This test asserts the client fetched successfully with status 200; the
    auto-escalation to Playwright is exercised in a separate test."""
    from target_data_extractor.bypass import BypassClient
    client = BypassClient(BypassConfig(strategy="curl_cffi", min_delay_seconds=0, max_delay_seconds=0))
    try:
        resp = await client.get("https://yeswehack.com/programs")
        assert resp.ok
        assert resp.status_code == 200
    finally:
        client.close()
