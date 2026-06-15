"""Immunefi platform extractor (Web3 / smart contract focused).

No public program-scope API. The /bounties/ JSON endpoint returns the listing
of programs, but detailed scope is on the program page. We scrape + parse.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from target_data_extractor.exceptions import ParseError
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


class ImmunefiPlatform(BasePlatform):
    platform_name = "immunefi"
    hostnames = ["immunefi.com"]
    requires_auth = False

    BASE_URL = "https://immunefi.com"
    API_BOUNTIES = "https://immunefi.com/bounties.json"

    async def extract(self, url: str, **kwargs: Any) -> BountyProgram:
        handle = self.extract_handle_from_url(url)
        if not handle:
            raise ParseError(f"Could not extract project handle from URL: {url}", platform=self.platform_name)
        # URL pattern: https://immunefi.com/bounty/<handle>/  OR  /bug-bounty/<handle>/
        candidates = [
            f"{self.BASE_URL}/bounty/{handle}/",
            f"{self.BASE_URL}/bug-bounty/{handle}/",
            url,
        ]
        html = ""
        for u in candidates:
            try:
                html = await self._fetch_html(u)
                if html and len(html) > 1500:
                    break
            except Exception as exc:  # noqa: BLE001
                logger.debug("immunefi fetch %s failed: %s", u, exc)
        if not html:
            raise ParseError(f"Could not fetch Immunefi page for {handle}", platform=self.platform_name)

        soup = self._parse_html(html)
        data = self._extract_state(soup)
        return self._build_program(data, handle, url)

    def _extract_state(self, soup: Any) -> dict[str, Any]:
        for script in soup.find_all("script"):
            text = script.string or ""
            for marker in ("__NEXT_DATA__", "window.__PRELOADED_STATE__", "window.__INITIAL_STATE__"):
                if marker in text:
                    m = re.search(re.escape(marker) + r"\s*[=:]\s*(\{.+?\});?\s*$", text, re.DOTALL)
                    if m:
                        try:
                            return json.loads(m.group(1))
                        except json.JSONDecodeError:
                            continue
        return {}

    def _build_program(self, data: dict[str, Any], handle: str, source_url: str) -> BountyProgram:
        def deep_get(d: Any, *keys: str) -> Any:
            cur = d
            for k in keys:
                if isinstance(cur, dict):
                    cur = cur.get(k)
                else:
                    return None
            return cur

        # Immunefi shape: { props: { pageProps: { bounty: {...} } } }
        bounty = (
            deep_get(data, "props", "pageProps", "bounty")
            or deep_get(data, "props", "pageProps", "project")
            or deep_get(data, "bounty")
            or {}
        )
        name = bounty.get("name") or bounty.get("project_name") or handle
        description = bounty.get("description") or bounty.get("brief") or bounty.get("overview")

        # Smart contract / asset scope
        in_scope: list[ScopeAsset] = []
        out_of_scope: list[ScopeAsset] = []
        assets = (
            bounty.get("assets", [])
            or bounty.get("smart_contracts", [])
            or deep_get(bounty, "scope", "assets")
            or []
        )
        for a in assets:
            if not isinstance(a, dict):
                continue
            target = a.get("url") or a.get("address") or a.get("name", "")
            is_in = bool(a.get("inScope", True))
            sev = Severity.normalize(a.get("maxSeverity", ""))
            asset = ScopeAsset(
                target=target,
                asset_type=AssetType.classify(target) if not a.get("address") else AssetType.SMART_CONTRACT,
                in_scope=is_in,
                max_severity=sev,
                description=a.get("description"),
            )
            (in_scope if is_in else out_of_scope).append(asset)

        # Immunefi max reward is the headline figure
        max_amt: float | None = None
        max_reward = bounty.get("max_reward") or bounty.get("maxBounty") or bounty.get("reward_max")
        try:
            if max_reward:
                max_amt = float(str(max_reward).replace(",", "").replace("$", ""))
        except (TypeError, ValueError):
            pass

        bounty_table: list[BountyRange] = []
        if max_amt is not None:
            bounty_table.append(BountyRange(severity=Severity.CRITICAL, min_amount=None, max_amount=max_amt))

        rules = ProgramRules(
            safe_harbor=bounty.get("safeHarbor"),
            disclosure_policy=bounty.get("disclosurePolicy") or "Immunefi standard KYC + disclosure",
            requires_kyc=True,
            submission_format="Report via Immunefi platform",
            rules_text=description,
        )

        return BountyProgram(
            platform=self.platform_name,
            program_handle=handle,
            program_name=name,
            program_url=source_url,  # type: ignore[arg-type]
            bounty_table=bounty_table,
            max_bounty_usd=max_amt,
            min_bounty_usd=None,
            is_paid=bool(bounty_table),
            is_private=False,
            program_type="smart_contract",
            scope=ProgramScope(in_scope=in_scope, out_of_scope=out_of_scope),
            rules=rules,
            description=description,
            tags=bounty.get("tags", []) or [],
            source_url=source_url,  # type: ignore[arg-type]
            extracted_at=self._now(),
            raw_data=data,
        )

    async def list_programs(self, **kwargs: Any) -> list[BountyProgram]:
        """List all Immunefi bug bounties from the public JSON endpoint."""
        try:
            resp = await self.bypass.get(self.API_BOUNTIES)
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Immunefi list fetch failed: %s", exc)
            return []
        results: list[BountyProgram] = []
        items = payload if isinstance(payload, list) else payload.get("bounties", [])
        for item in items:
            if not isinstance(item, dict):
                continue
            slug = item.get("slug") or item.get("project_slug") or item.get("name", "").lower().replace(" ", "-")
            if slug:
                try:
                    results.append(await self.extract(f"{self.BASE_URL}/bounty/{slug}/"))
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Skipping immunefi program %s: %s", slug, exc)
        return results
