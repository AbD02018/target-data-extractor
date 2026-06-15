"""HackerOne platform extractor.

HackerOne has a public API at https://api.hackerone.com/ that exposes:
  - /v1/programs/{handle}
  - /v1/programs/{handle}/structured_scopes
  - /v1/programs/{handle}/bounty_awards

Auth: basic auth with API token (https://hackerone.com/settings/api_token/edit).
For unauthenticated fallback, scrape the public program page.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from typing import Any
from urllib.parse import quote

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


class HackerOnePlatform(BasePlatform):
    platform_name = "hackerone"
    hostnames = ["hackerone.com"]
    requires_auth = True  # API requires token; public scrape works without

    def __init__(self, *, api_token: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.api_token = (
            api_token
            or os.environ.get("HACKERONE_API_TOKEN")
            or os.environ.get("H1_API_TOKEN")
        )
        self.api_url = "https://api.hackerone.com"

    def _auth_header(self) -> str:
        if not self.api_token:
            raise AuthenticationError(
                "HackerOne API token required. Set HACKERONE_API_TOKEN or pass api_token=...",
                platform=self.platform_name,
            )
        encoded = base64.b64encode(self.api_token.encode()).decode()
        return f"Basic {encoded}"

    async def extract(self, url: str, **kwargs: Any) -> BountyProgram:
        handle = self.extract_handle_from_url(url)
        if not handle:
            raise ParseError(f"Could not extract program handle from URL: {url}", platform=self.platform_name)
        if self.api_token:
            try:
                return await self._extract_via_api(handle, url)
            except Exception as exc:  # noqa: BLE001
                logger.warning("HackerOne API path failed (%s); falling back to scrape", exc)
        return await self._extract_via_scrape(handle, url)

    async def _extract_via_api(self, handle: str, url: str) -> BountyProgram:
        import httpx

        headers = {
            "Authorization": self._auth_header(),
            "Accept": "application/json",
        }

        program_data = await self._api_get(f"/v1/programs/{quote(handle)}", headers)
        program = program_data.get("data", program_data)

        scopes_data: list[dict[str, Any]] = []
        page = 1
        while True:
            chunk = await self._api_get(
                f"/v1/programs/{quote(handle)}/structured_scopes?page%5Bnumber%5D={page}&page%5Bsize%5D=100",
                headers,
            )
            data = chunk.get("data", [])
            if not data:
                break
            scopes_data.extend(data)
            if len(data) < 100:
                break
            page += 1
            if page > 50:
                break

        bounty_data: list[dict[str, Any]] = []
        try:
            bounty_resp = await self._api_get(
                f"/v1/programs/{quote(handle)}/bounty_awards",
                headers,
            )
            bounty_data = bounty_resp.get("data", [])
        except Exception as exc:  # noqa: BLE001
            logger.debug("bounty_awards fetch failed: %s", exc)

        return self._build_program(program, scopes_data, bounty_data, url)

    async def _api_get(self, path: str, headers: dict[str, str]) -> dict[str, Any]:
        import httpx
        url = f"{self.api_url}{path}"
        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 401:
                raise AuthenticationError(
                    "HackerOne API rejected the token (401). Check HACKERONE_API_TOKEN.",
                    platform=self.platform_name,
                )
            if resp.status_code == 404:
                raise ParseError(f"Program not found: {path}", platform=self.platform_name)
            if resp.status_code == 429:
                from target_data_extractor.exceptions import RateLimitError
                retry_after = int(resp.headers.get("Retry-After", "60"))
                raise RateLimitError(
                    "HackerOne API rate limit hit",
                    retry_after=retry_after,
                    platform=self.platform_name,
                )
            resp.raise_for_status()
            return resp.json()

    async def _extract_via_scrape(self, handle: str, url: str) -> BountyProgram:
        directory_url = f"https://hackerone.com/{quote(handle)}"
        html = await self._fetch_html(directory_url)
        soup = self._parse_html(html)

        program_data: dict[str, Any] = {}
        for script in soup.find_all("script"):
            text = script.string or ""
            if "__NEXT_DATA__" in text:
                match = re.search(r"__NEXT_DATA__\s*=\s*({.+?})\s*</script>", text, re.DOTALL)
                if match:
                    try:
                        program_data = json.loads(match.group(1))
                        break
                    except json.JSONDecodeError:
                        continue

        if not program_data:
            program_data = self._scrape_fallback_parse(soup, handle, url)

        return self._build_program(
            program_data.get("program", program_data),
            program_data.get("scopes", []),
            program_data.get("bounty_awards", []),
            url,
        )

    def _scrape_fallback_parse(self, soup: Any, handle: str, url: str) -> dict[str, Any]:
        title = (soup.title.string.strip() if soup.title and soup.title.string else handle)
        text = soup.get_text(" ", strip=True)
        scope_assets: list[dict[str, Any]] = []
        for link in soup.select("a[href*='://']"):
            href = link.get("href", "")
            if href.startswith("http") and "hackerone.com" not in href:
                from urllib.parse import urlparse
                host = urlparse(href).netloc
                if host:
                    scope_assets.append({
                        "asset_identifier": host,
                        "asset_type": "URL",
                        "eligible_for_bounty": True,
                    })
        return {
            "program": {
                "attributes": {
                    "name": title,
                    "handle": handle,
                    "url": url,
                }
            },
            "scopes": scope_assets,
            "bounty_awards": [],
        }

    def _classify_asset(self, asset_type_str: str, asset_id: str) -> AssetType:
        s = (asset_type_str or "").lower()
        if "wildcard" in s or asset_id.startswith("*."):
            return AssetType.WILDCARD
        if "android" in s:
            return AssetType.ANDROID_APP
        if "ios" in s:
            return AssetType.IOS_APP
        if "smart_contract" in s or "smart contract" in s or asset_id.endswith(".sol"):
            return AssetType.SMART_CONTRACT
        if "source" in s and "code" in s:
            return AssetType.SOURCE_CODE
        if "binary" in s or "executable" in s:
            return AssetType.BINARY
        if "cidr" in s or "ip_range" in s:
            return AssetType.CIDR
        if "hardware" in s:
            return AssetType.OTHER
        if "url" in s or asset_id.startswith("http"):
            return AssetType.URL
        return AssetType.classify(asset_id)

    def _build_program(
        self,
        program: dict[str, Any],
        scopes: list[dict[str, Any]],
        bounty_awards: list[dict[str, Any]],
        source_url: str,
    ) -> BountyProgram:
        attrs = program.get("attributes", program)
        handle = attrs.get("handle", self.extract_handle_from_url(source_url) or "")
        name = attrs.get("name") or handle

        in_scope: list[ScopeAsset] = []
        out_of_scope: list[ScopeAsset] = []
        for s in scopes:
            s_attrs = s.get("attributes", s)
            asset_id = s_attrs.get("asset_identifier", "")
            if not asset_id:
                continue
            eligible = bool(s_attrs.get("eligible_for_bounty", True))
            asset_type_str = s_attrs.get("asset_type", "")
            severity_str = s_attrs.get("max_severity", "")
            asset = ScopeAsset(
                target=asset_id,
                asset_type=self._classify_asset(asset_type_str, asset_id),
                in_scope=eligible,
                max_severity=Severity.normalize(severity_str),
                description=s_attrs.get("instruction") or s_attrs.get("description"),
            )
            (in_scope if eligible else out_of_scope).append(asset)

        bounty_table: list[BountyRange] = []
        max_amt: float | None = None
        min_amt: float | None = None
        for ba in bounty_awards:
            ba_attrs = ba.get("attributes", ba)
            sev = Severity.normalize(ba_attrs.get("severity", ""))
            amount = ba_attrs.get("amount")
            try:
                amount_f = float(str(amount).replace(",", "").replace("$", "")) if amount else None
            except (TypeError, ValueError):
                amount_f = None
            if amount_f is not None:
                bounty_table.append(BountyRange(severity=sev, min_amount=amount_f, max_amount=amount_f))
                if max_amt is None or amount_f > max_amt:
                    max_amt = amount_f
                if min_amt is None or amount_f < min_amt:
                    min_amt = amount_f

        rules = ProgramRules(
            safe_harbor=attrs.get("offers_bounties") or None,
            disclosure_policy=attrs.get("disclosure_policy"),
            submission_format="Report via HackerOne platform",
            rules_text=attrs.get("policy") or attrs.get("description"),
        )

        return BountyProgram(
            platform=self.platform_name,
            program_handle=handle,
            program_name=name,
            program_url=source_url,  # type: ignore[arg-type]
            bounty_table=bounty_table,
            max_bounty_usd=max_amt,
            min_bounty_usd=min_amt,
            is_paid=bool(bounty_table),
            is_private=bool(attrs.get("private", False)),
            program_type="bug_bounty",
            scope=ProgramScope(in_scope=in_scope, out_of_scope=out_of_scope),
            rules=rules,
            description=attrs.get("description"),
            tags=list(attrs.get("tags", []) or []),
            submission_count=attrs.get("number_of_reports"),
            source_url=source_url,  # type: ignore[arg-type]
            extracted_at=self._now(),
            raw_data={"program": program, "scopes": scopes, "bounty_awards": bounty_awards},
        )

    async def list_programs(self, **kwargs: Any) -> list[BountyProgram]:
        """List all public programs accessible via the API."""
        import httpx
        if not self.api_token:
            raise AuthenticationError(
                "HackerOne list_programs requires HACKERONE_API_TOKEN",
                platform=self.platform_name,
            )
        headers = {"Authorization": self._auth_header(), "Accept": "application/json"}
        results: list[BountyProgram] = []
        page = 1
        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            while True:
                resp = await client.get(
                    f"{self.api_url}/v1/programs?page%5Bnumber%5D={page}&page%5Bsize%5D=100",
                    headers=headers,
                )
                resp.raise_for_status()
                payload = resp.json()
                data = payload.get("data", [])
                for prog in data:
                    p_attrs = prog.get("attributes", prog)
                    handle = p_attrs.get("handle", "")
                    if handle:
                        try:
                            results.append(await self.extract(f"https://hackerone.com/{handle}"))
                        except Exception as exc:  # noqa: BLE001
                            logger.debug("Skipping program %s: %s", handle, exc)
                if len(data) < 100:
                    break
                page += 1
                if page > 100:
                    break
        return results
