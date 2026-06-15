"""Bugcrowd platform extractor.

Bugcrowd has a public API at https://api.bugcrowd.com/ that exposes:
  - GET /programs                    (public list)
  - GET /programs/{code}             (single program)
  - GET /programs/{code}/groups      (scope groups, requires auth for private)

Auth: `Authorization: Token <api_key>` header.
The API key is requested separately by Bugcrowd (not the researcher login).
For unauthenticated fallback, scrape the public program page.
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


class BugcrowdPlatform(BasePlatform):
    platform_name = "bugcrowd"
    hostnames = ["bugcrowd.com"]
    requires_auth = False  # Public API can list; scope may need auth

    def __init__(self, *, api_key: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.api_key = (
            api_key
            or os.environ.get("BUGCROWD_API_KEY")
            or os.environ.get("BUGCROWD_TOKEN")
        )
        self.api_url = "https://api.bugcrowd.com"

    def _auth_headers(self) -> dict[str, str]:
        if not self.api_key:
            return {}
        return {
            "Authorization": f"Token {self.api_key}",
            "Accept": "application/json",
        }

    async def extract(self, url: str, **kwargs: Any) -> BountyProgram:
        handle = self.extract_handle_from_url(url)
        if not handle:
            raise ParseError(f"Could not extract program code from URL: {url}", platform=self.platform_name)

        if self.api_key:
            try:
                return await self._extract_via_api(handle, url)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Bugcrowd API path failed (%s); falling back to scrape", exc)
        return await self._extract_via_scrape(handle, url)

    async def _extract_via_api(self, handle: str, url: str) -> BountyProgram:
        import httpx
        headers = self._auth_headers()
        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            resp = await client.get(f"{self.api_url}/programs/{handle}", headers=headers)
            if resp.status_code == 401:
                raise AuthenticationError(
                    "Bugcrowd API rejected the token (401). Check BUGCROWD_API_KEY.",
                    platform=self.platform_name,
                )
            if resp.status_code == 404:
                raise ParseError(f"Program not found: {handle}", platform=self.platform_name)
            resp.raise_for_status()
            program = resp.json()

            # Fetch groups (scope) — may 403 for private programs
            groups: list[dict[str, Any]] = []
            try:
                g_resp = await client.get(
                    f"{self.api_url}/programs/{handle}/groups",
                    headers=headers,
                )
                if g_resp.status_code == 200:
                    groups = g_resp.json().get("groups", g_resp.json() or [])
            except Exception as exc:  # noqa: BLE001
                logger.debug("groups fetch failed: %s", exc)

        return self._build_program(program, groups, url)

    async def _extract_via_scrape(self, handle: str, url: str) -> BountyProgram:
        public_url = f"https://bugcrowd.com/{handle}"
        html = await self._fetch_html(public_url)
        soup = self._parse_html(html)

        program_data: dict[str, Any] = {}
        for script in soup.find_all("script"):
            text = script.string or ""
            if "program" in text.lower() and ("scope" in text.lower() or "bounty" in text.lower()):
                # Bugcrowd embeds JSON in <script>window.__data__ = ...</script>
                for marker in ("window.__INITIAL_STATE__", "window.__PRELOADED_STATE__", "gon ="):
                    if marker in text:
                        m = re.search(re.escape(marker) + r"\s*[=:]?\s*(\{.+?\})\s*;?\s*$", text, re.DOTALL | re.MULTILINE)
                        if m:
                            try:
                                program_data = json.loads(m.group(1))
                                break
                            except json.JSONDecodeError:
                                continue
            if program_data:
                break

        if not program_data:
            program_data = self._heuristic_scrape(soup, handle, url)

        return self._build_program(
            program_data if isinstance(program_data, dict) else {},
            program_data.get("groups", []) if isinstance(program_data, dict) else [],
            url,
        )

    def _heuristic_scrape(self, soup: Any, handle: str, url: str) -> dict[str, Any]:
        title = (soup.title.string.strip() if soup.title and soup.title.string else handle)
        text = soup.get_text(" ", strip=True)
        scope_assets: list[dict[str, Any]] = []
        for el in soup.select("[class*='target'], [class*='scope']"):
            v = el.get_text(" ", strip=True)
            if v and 4 < len(v) < 200:
                scope_assets.append({
                    "name": v,
                    "in_scope": True,
                    "targets": [{"uri": v}],
                })
        return {
            "name": title,
            "code": handle,
            "url": url,
            "groups": scope_assets,
        }

    def _build_program(
        self,
        program: dict[str, Any],
        groups: list[dict[str, Any]],
        source_url: str,
    ) -> BountyProgram:
        handle = program.get("code") or program.get("slug") or self.extract_handle_from_url(source_url) or ""
        name = program.get("name") or program.get("display_name") or handle

        # Parse scope from groups
        in_scope: list[ScopeAsset] = []
        out_of_scope: list[ScopeAsset] = []
        for group in groups:
            group_name = group.get("name", "")
            is_in = bool(group.get("in_scope", True))
            targets = group.get("targets", [])
            for t in targets:
                target = t.get("uri") or t.get("name") or t.get("target", "")
                if not target:
                    continue
                sev = Severity.normalize(t.get("severity", ""))
                asset = ScopeAsset(
                    target=target,
                    asset_type=AssetType.classify(target),
                    in_scope=is_in,
                    max_severity=sev,
                    description=group_name,
                )
                (in_scope if is_in else out_of_scope).append(asset)

        # Parse bounty table
        bounty_table: list[BountyRange] = []
        max_amt: float | None = None
        min_amt: float | None = None
        bounty_ranges = program.get("bounty_range") or {}
        if isinstance(bounty_ranges, dict):
            bounty_table, min_amt, max_amt = self._bounty_table_from_dict(bounty_ranges)
        else:
            # Try nested max_payout
            max_payout = program.get("max_payout")
            try:
                if max_payout:
                    max_amt = float(str(max_payout).replace(",", "").replace("$", ""))
            except (TypeError, ValueError):
                pass

        rules = ProgramRules(
            safe_harbor=program.get("safe_harbor"),
            disclosure_policy=program.get("disclosure_terms") or program.get("disclosure_policy"),
            submission_format="Report via Bugcrowd platform",
            rules_text=program.get("brief") or program.get("description"),
            managed_program=program.get("managed"),
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
            is_private=bool(program.get("private", False)),
            program_type="bug_bounty",
            scope=ProgramScope(in_scope=in_scope, out_of_scope=out_of_scope),
            rules=rules,
            description=program.get("brief") or program.get("description"),
            tags=program.get("tags", []) or [],
            source_url=source_url,  # type: ignore[arg-type]
            extracted_at=self._now(),
            raw_data={"program": program, "groups": groups},
        )

    async def list_programs(self, **kwargs: Any) -> list[BountyProgram]:
        """List public programs. API may return only programs your token has access to."""
        import httpx
        headers = self._auth_headers()
        if not headers:
            raise AuthenticationError(
                "Bugcrowd list_programs requires BUGCROWD_API_KEY",
                platform=self.platform_name,
            )
        results: list[BountyProgram] = []
        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            resp = await client.get(f"{self.api_url}/programs", headers=headers)
            resp.raise_for_status()
            data = resp.json()
            for prog in data.get("programs", []):
                code = prog.get("code") or prog.get("slug")
                if code:
                    try:
                        results.append(await self.extract(f"https://bugcrowd.com/{code}"))
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("Skipping %s: %s", code, exc)
        return results
