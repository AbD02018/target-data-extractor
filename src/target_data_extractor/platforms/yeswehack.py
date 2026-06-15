"""YesWeHack platform extractor.

YesWeHack does not expose a public program-scope API. The official path requires
a researcher account + bearer token (2FA). For unauthenticated access, we scrape
the public program page (yeswehack.com/programs/<handle>).
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from target_data_extractor.exceptions import AuthenticationError, ParseError
from target_data_extractor.models import (
    AssetType,
    BountyProgram,
    BountyRange,
    ProgramRules,
    ProgramScope,
    ScopeAsset,
    Severity,
)
from target_data_extractor.platforms.base import BasePlatform

logger = logging.getLogger(__name__)


class YesWeHackPlatform(BasePlatform):
    platform_name = "yeswehack"
    hostnames = ["yeswehack.com"]
    requires_auth = False  # Scrape works without

    def __init__(self, *, bearer_token: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.bearer_token = (
            bearer_token
            or os.environ.get("YESWEHACK_TOKEN")
            or os.environ.get("YWH_BEARER")
        )
        self.api_url = "https://api.yeswehack.com"

    async def extract(self, url: str, **kwargs: Any) -> BountyProgram:
        handle = self.extract_handle_from_url(url)
        if not handle:
            raise ParseError(f"Could not extract program handle from URL: {url}", platform=self.platform_name)

        if self.bearer_token:
            try:
                return await self._extract_via_api(handle, url)
            except Exception as exc:  # noqa: BLE001
                logger.warning("YesWeHack API path failed (%s); falling back to scrape", exc)
        return await self._extract_via_scrape(handle, url)

    async def _extract_via_api(self, handle: str, url: str) -> BountyProgram:
        import httpx
        headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            resp = await client.get(
                f"{self.api_url}/programs/{handle}",
                headers=headers,
            )
            if resp.status_code == 401:
                raise AuthenticationError(
                    "YesWeHack API rejected the bearer token (401).",
                    platform=self.platform_name,
                )
            if resp.status_code == 404:
                raise ParseError(f"Program not found: {handle}", platform=self.platform_name)
            resp.raise_for_status()
            program = resp.json()

            scopes: list[dict[str, Any]] = []
            try:
                s_resp = await client.get(
                    f"{self.api_url}/programs/{handle}/scopes",
                    headers=headers,
                )
                if s_resp.status_code == 200:
                    scopes = s_resp.json().get("scopes", s_resp.json() or [])
            except Exception as exc:  # noqa: BLE001
                logger.debug("scope fetch failed: %s", exc)

        return self._build_program(program, scopes, url)

    async def _extract_via_scrape(self, handle: str, url: str) -> BountyProgram:
        candidates = [
            f"https://yeswehack.com/programs/{handle}",
            f"https://www.yeswehack.com/programs/{handle}",
            url,
        ]
        html = ""
        for u in candidates:
            try:
                html = await self._fetch_html(u)
                if html and len(html) > 1500:
                    break
            except Exception as exc:  # noqa: BLE001
                logger.debug("ywh fetch %s failed: %s", u, exc)
        if not html:
            raise ParseError(f"Could not fetch YesWeHack page for {handle}", platform=self.platform_name)
        soup = self._parse_html(html)
        data = self._extract_state(soup)
        return self._build_program(data.get("program", data), data.get("scopes", []), url)

    def _extract_state(self, soup: Any) -> dict[str, Any]:
        for script in soup.find_all("script"):
            text = script.string or ""
            for marker in ("__NEXT_DATA__", "window.__NUXT__", "window.__INITIAL_STATE__"):
                if marker in text:
                    m = re.search(re.escape(marker) + r"\s*[=:]\s*(\{.+?\});?\s*$", text, re.DOTALL)
                    if m:
                        try:
                            return json.loads(m.group(1))
                        except json.JSONDecodeError:
                            continue
        return {}

    def _build_program(
        self,
        program: dict[str, Any],
        scopes: list[dict[str, Any]],
        source_url: str,
    ) -> BountyProgram:
        handle = program.get("slug") or program.get("id") or self.extract_handle_from_url(source_url) or ""
        name = program.get("title") or program.get("name") or handle
        description = program.get("description") or program.get("brief")

        in_scope: list[ScopeAsset] = []
        out_of_scope: list[ScopeAsset] = []
        for s in scopes if isinstance(scopes, list) else []:
            if not isinstance(s, dict):
                continue
            target = s.get("target") or s.get("url") or s.get("host") or s.get("name", "")
            is_in = bool(s.get("in_scope", True))
            sev = Severity.normalize(s.get("max_severity", ""))
            asset = ScopeAsset(
                target=target,
                asset_type=AssetType.classify(target),
                in_scope=is_in,
                max_severity=sev,
                description=s.get("description"),
            )
            (in_scope if is_in else out_of_scope).append(asset)

        bounty_table: list[BountyRange] = []
        max_amt: float | None = None
        min_amt: float | None = None
        rewards = program.get("rewards") or program.get("bounty") or {}
        if isinstance(rewards, dict):
            bounty_table, min_amt, max_amt = self._bounty_table_from_dict(rewards)
        else:
            try:
                if rewards:
                    max_amt = float(str(rewards).replace(",", "").replace("€", "").replace("$", ""))
            except (TypeError, ValueError):
                pass

        rules = ProgramRules(
            safe_harbor=program.get("safe_harbor"),
            disclosure_policy=program.get("disclosure_policy"),
            submission_format="Report via YesWeHack platform",
            rules_text=description,
        )

        return BountyProgram(
            platform=self.platform_name,
            program_handle=handle,
            program_name=name,
            program_url=source_url,  # type: ignore[arg-type]
            bounty_table=bounty_table,
            max_bounty_usd=max_amt,
            min_bounty_usd=min_amt,
            is_paid=bool(bounty_table) or bool(max_amt),
            is_private=False,
            program_type="bug_bounty",
            scope=ProgramScope(in_scope=in_scope, out_of_scope=out_of_scope),
            rules=rules,
            description=description,
            tags=program.get("tags", []) or [],
            source_url=source_url,  # type: ignore[arg-type]
            extracted_at=self._now(),
            raw_data={"program": program, "scopes": scopes},
        )
