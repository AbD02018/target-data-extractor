"""Anti-bot bypass layer.

Strategy (escalating):
  1. curl_cffi (TLS/HTTP2 fingerprint impersonation) - cheapest, fastest
  2. cloudscraper (Cloudflare-specific JS challenge solver) - lightweight
  3. playwright-stealth (real browser with stealth flags) - heavy
  4. undetected-chromedriver (anti-CDP Chromium) - last resort
  5. camoufox (Firefox with anti-fingerprint) - alternative heavy

This module exposes a single `BypassClient` facade that auto-escalates.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any

from curl_cffi.requests import AsyncSession as CurlAsyncSession
from curl_cffi.requests import Session as CurlSession

from target_data_extractor.exceptions import AntiBotError, NetworkError, RateLimitError

logger = logging.getLogger(__name__)


@dataclass
class BypassConfig:
    """Configuration for the bypass client."""

    # Strategy selection
    strategy: str = "auto"  # auto | curl_cffi | cloudscraper | playwright | undetected | camoufox
    # auto = try cheap first (curl_cffi), escalate to playwright when page is JS-heavy
    # bug bounty pages (H1, Intigriti, YWH) are heavily JS-rendered → set strategy="playwright" for fastest correct extraction

    # Proxy
    proxy: str | None = None  # http://user:pass@host:port
    rotate_proxies: list[str] = field(default_factory=list)

    # Browser fingerprint impersonation
    impersonate: str = "chrome120"  # chrome120, chrome124, firefox123, edge101, safari17_0

    # Rate limiting
    min_delay_seconds: float = 1.0
    max_delay_seconds: float = 3.0

    # Timeouts
    timeout: int = 30

    # Retry
    max_retries: int = 3
    backoff_factor: float = 2.0

    # Headers
    default_headers: dict[str, str] = field(
        default_factory=lambda: {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }
    )

    # User-Agent rotation pool
    user_agents: list[str] = field(
        default_factory=lambda: [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
        ]
    )

    def get_random_ua(self) -> str:
        return random.choice(self.user_agents)

    def get_proxy(self) -> str | None:
        if self.rotate_proxies:
            return random.choice(self.rotate_proxies)
        return self.proxy


class BypassResponse:
    """A unified response object across strategies."""

    def __init__(
        self,
        url: str,
        status_code: int,
        text: str,
        content: bytes,
        headers: dict[str, str],
        strategy_used: str,
        elapsed_seconds: float,
    ) -> None:
        self.url = url
        self.status_code = status_code
        self.text = text
        self.content = content
        self.headers = dict(headers)
        self.strategy_used = strategy_used
        self.elapsed_seconds = elapsed_seconds

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    @property
    def is_blocked(self) -> bool:
        """Heuristic: looks like a Cloudflare/DataDome/Akamai block page."""
        if self.status_code in (403, 1020, 1010):
            return True
        lower = self.text.lower()[:5000]
        block_signatures = [
            "just a moment",
            "checking your browser",
            "attention required",
            "access denied",
            "sorry, you have been blocked",
            "datadome",
            "cf-chl-bypass",
            "cf_clearance",
            "ray id:",
            "akamai",
        ]
        return any(sig in lower for sig in block_signatures)

    def json(self) -> Any:
        import json
        return json.loads(self.text)

    def __repr__(self) -> str:
        return f"<BypassResponse {self.status_code} strategy={self.strategy_used} url={self.url[:80]!r}>"


class BypassClient:
    """Anti-bot-aware HTTP client with auto-escalation.

    Usage:
        client = BypassClient(BypassConfig())
        response = await client.get("https://intigriti.com/researcher/programs/...")
        if response.is_blocked:
            ...
    """

    def __init__(self, config: BypassConfig | None = None) -> None:
        self.config = config or BypassConfig()
        self._curl_session: CurlSession | None = None

    def _ensure_curl_session(self) -> CurlSession:
        if self._curl_session is None:
            self._curl_session = CurlSession(
                impersonate=self.config.impersonate,
                timeout=self.config.timeout,
                proxy=self.config.get_proxy(),
            )
        return self._curl_session

    async def get(self, url: str, **kwargs: Any) -> BypassResponse:
        """Async GET with auto-escalation. Returns BypassResponse.

        Escalates to next strategy on:
          - explicit failure (exception)
          - HTTP non-2xx
          - detected anti-bot block
          - JS-only page (response <4KB and no useful markup) - signals hydration needed
        """
        start = time.monotonic()
        strategy = self.config.strategy
        last_error: Exception | None = None

        strategies = self._resolve_strategies(strategy)

        for current in strategies:
            for attempt in range(1, self.config.max_retries + 1):
                try:
                    response = await self._dispatch_get(current, url, **kwargs)
                    response.strategy_used = current
                    response.elapsed_seconds = time.monotonic() - start
                    if not response.is_blocked and response.ok and self._looks_like_real_content(response):
                        await self._respect_rate_limit()
                        return response
                    logger.debug(
                        "Strategy %s attempt %d insufficient (status=%d blocked=%s len=%d) for %s",
                        current, attempt, response.status_code, response.is_blocked, len(response.text), url,
                    )
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    logger.debug("Strategy %s attempt %d failed: %s", current, attempt, exc)
                if attempt < self.config.max_retries:
                    backoff = self.config.backoff_factor ** attempt
                    await asyncio.sleep(backoff)

        raise AntiBotError(
            f"All bypass strategies failed for {url!r}: {last_error}",
            url=url,
        )

    def _looks_like_real_content(self, response: "BypassResponse") -> bool:
        """Heuristic: is the page hydrated / has substance, or is it a JS shell?"""
        if response.strategy_used in ("playwright", "camoufox", "undetected"):
            return True  # browser always renders
        text = response.text
        if len(text) < 1500:
            return False
        # Real bug bounty pages mention things like 'scope', 'reward', 'bounty', 'severity', 'bounty', '$'
        lower = text.lower()
        signals = ("scope", "reward", "bounty", "severity", "critical", "out-of-scope", "eligible", "asset", "vulnerability", "report", "program")
        if any(s in lower for s in signals):
            return True
        # Has JSON state injection (Next.js / Nuxt)
        if "__NEXT_DATA__" in text or "window.__NUXT__" in text or "window.__PRELOADED_STATE__" in text:
            return True
        # If it's a normal HTML page > 5KB without obvious JS shell markers, accept it
        if len(text) > 5000 and "<body" in text and "<p " in text:
            return True
        return False

    async def _dispatch_get(self, strategy: str, url: str, **kwargs: Any) -> BypassResponse:
        if strategy == "curl_cffi":
            return await self._curl_cffi_get(url, **kwargs)
        if strategy == "cloudscraper":
            return await self._cloudscraper_get(url, **kwargs)
        if strategy in ("playwright", "camoufox"):
            return await self._playwright_get(url, strategy, **kwargs)
        if strategy == "undetected":
            return await self._undetected_get(url, **kwargs)
        raise ValueError(f"Unknown strategy: {strategy!r}")

    def _resolve_strategies(self, requested: str) -> list[str]:
        if requested != "auto":
            return [requested]
        # Auto-escalation: try cheap static first, escalate on JS-heavy or blocked
        return ["curl_cffi", "cloudscraper", "playwright"]

    async def _curl_cffi_get(self, url: str, **kwargs: Any) -> BypassResponse:
        try:
            session = self._ensure_curl_session()
            headers = {**self.config.default_headers, "User-Agent": self.config.get_random_ua(), **kwargs.pop("headers", {})}
            resp = await asyncio.to_thread(session.get, url, headers=headers, **kwargs)
            return BypassResponse(
                url=str(resp.url),
                status_code=resp.status_code,
                text=resp.text,
                content=resp.content,
                headers=dict(resp.headers),
                strategy_used="curl_cffi",
                elapsed_seconds=0.0,
            )
        except Exception as exc:
            raise NetworkError(f"curl_cffi GET failed: {exc}", url=url) from exc

    async def _cloudscraper_get(self, url: str, **kwargs: Any) -> BypassResponse:
        try:
            import cloudscraper  # type: ignore[import-not-found]

            scraper = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "linux", "desktop": True},
            )
            headers = {**self.config.default_headers, **kwargs.pop("headers", {})}
            resp = await asyncio.to_thread(scraper.get, url, headers=headers, **kwargs)
            return BypassResponse(
                url=resp.url,
                status_code=resp.status_code,
                text=resp.text,
                content=resp.content,
                headers=dict(resp.headers),
                strategy_used="cloudscraper",
                elapsed_seconds=0.0,
            )
        except Exception as exc:
            raise NetworkError(f"cloudscraper GET failed: {exc}", url=url) from exc

    async def _playwright_get(self, url: str, strategy: str, **kwargs: Any) -> BypassResponse:
        try:
            from playwright.async_api import async_playwright  # type: ignore[import-not-found]
        except ImportError as exc:
            raise AntiBotError("playwright is not installed", url=url) from exc

        browser_type = "firefox" if strategy == "camoufox" else "chromium"
        async with async_playwright() as p:
            launch_kwargs: dict[str, Any] = {"headless": True}
            if strategy == "camoufox":
                launch_kwargs["firefox_user_prefs"] = {"general.useragent.override": self.config.get_random_ua()}
            browser = await getattr(p, browser_type).launch(**launch_kwargs)
            try:
                context = await browser.new_context(
                    user_agent=self.config.get_random_ua(),
                    viewport={"width": 1920, "height": 1080},
                    locale="en-US",
                )
                # Apply playwright-stealth
                try:
                    from playwright_stealth import stealth_async  # type: ignore[import-not-found]
                    await stealth_async(context)
                except ImportError:
                    logger.debug("playwright-stealth not available, continuing without it")
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=self.config.timeout * 1000)
                # Wait for Cloudflare/JS challenge to resolve
                await page.wait_for_load_state("networkidle", timeout=self.config.timeout * 1000)
                content = await page.content()
                status = page.url
                return BypassResponse(
                    url=status,
                    status_code=200,  # Playwright does not surface HTTP status after redirects
                    text=content,
                    content=content.encode("utf-8", errors="ignore"),
                    headers={},
                    strategy_used=strategy,
                    elapsed_seconds=0.0,
                )
            finally:
                await browser.close()

    async def _undetected_get(self, url: str, **kwargs: Any) -> BypassResponse:
        # undetected-chromedriver is sync; run in thread
        try:
            import undetected_chromedriver as uc  # type: ignore[import-not-found]
        except ImportError as exc:
            raise AntiBotError("undetected-chromedriver is not installed", url=url) from exc

        def _fetch() -> BypassResponse:
            options = uc.ChromeOptions()
            options.add_argument("--headless=new")
            options.add_argument(f"--user-agent={self.config.get_random_ua()}")
            driver = uc.Chrome(options=options, use_subprocess=True)
            try:
                driver.get(url)
                # Allow JS to settle
                time.sleep(2)
                content = driver.page_source
                return BypassResponse(
                    url=driver.current_url,
                    status_code=200,
                    text=content,
                    content=content.encode("utf-8", errors="ignore"),
                    headers={},
                    strategy_used="undetected",
                    elapsed_seconds=0.0,
                )
            finally:
                driver.quit()

        return await asyncio.to_thread(_fetch)

    async def _respect_rate_limit(self) -> None:
        delay = random.uniform(self.config.min_delay_seconds, self.config.max_delay_seconds)
        await asyncio.sleep(delay)

    def close(self) -> None:
        if self._curl_session is not None:
            self._curl_session.close()
            self._curl_session = None
