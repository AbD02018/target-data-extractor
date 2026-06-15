"""Intigriti platform extractor.

Intigriti has no public program-scope API. Researcher personal access tokens are
available (https://app.intigriti.com/researcher/personal-access-tokens) but those
do not expose public program data.

This extractor uses a hybrid approach:
  1. Try the public API endpoints (researcher-facing, if a token is provided).
  2. Fall back to scraping the public program page with the bypass client.
"""

from __future__ import annotations

import json
import logging
import os
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


class IntigritiPlatform(BasePlatform):
    platform_name = "intigriti"
    hostnames = ["intigriti.com", "intigriti.io"]
    requires_auth = False  # Scrape works without auth; API is optional

    def __init__(self, *, api_token: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.api_token = (
            api_token
            or os.environ.get("INTIGRITI_API_TOKEN")
            or os.environ.get("INTIGRITI_TOKEN")
        )
        self.api_url = "https://api.intigriti.com"
        self.public_url = "https://www.intigriti.com"

    async def extract(self, url: str, **kwargs: Any) -> BountyProgram:
        handle = self.extract_handle_from_url(url)
        if not handle:
            raise ParseError(f"Could not extract program handle from URL: {url}", platform=self.platform_name)
        # Always go through scrape (Intigriti has no public program-scope API)
        return await self._extract_via_scrape(handle, url)

    async def _extract_via_scrape(self, handle: str, url: str) -> BountyProgram:
        # Intigriti's public program URL pattern:
        # https://www.intigriti.com/researcher/programs/<company>/<handle>/detail
        # https://app.intigriti.com/researcher/programs/<handle>
        candidates = [
            f"{self.public_url}/researcher/programs/{handle}/detail",
            f"https://app.intigriti.com/researcher/programs/{handle}/detail",
            url,
        ]
        html = ""
        last_err: Exception | None = None
        for u in candidates:
            try:
                html = await self._fetch_html(u)
                if html and len(html) > 2000:
                    break
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                continue
        if not html:
            raise ParseError(
                f"Could not fetch Intigriti program page (last error: {last_err})",
                platform=self.platform_name,
            )

        soup = self._parse_html(html)
        program_data = self._extract_json_state(soup)
        return self._build_program(program_data, handle, url)

    def _extract_json_state(self, soup: Any) -> dict[str, Any]:
        """Intigriti hydrates with __NEXT_DATA__ or Nuxt payload."""
        for script in soup.find_all("script"):
            text = script.string or ""
            for marker in ("__NEXT_DATA__", "window.__NUXT__", "window.__PRELOADED_STATE__"):
                if marker in text:
                    m = re.search(re.escape(marker) + r"\s*[=:]\s*(\{.+?\})\s*;?\s*$", text, re.DOTALL)
                    if m:
                        try:
                            return json.loads(m.group(1))
                        except json.JSONDecodeError:
                            continue
        return {}

    def _build_program(self, data: dict[str, Any], handle: str, source_url: str) -> BountyProgram:
        # Intigriti data shape (heuristic; the JSON state can be deep)
        name = (
            data.get("name")
            or (data.get("program", {}) or {}).get("name")
            or handle
        )
        # Walk deep paths Intigriti uses
        def deep_get(d: Any, *keys: str) -> Any:
            for k in keys:
                if isinstance(d, dict):
                    d = d.get(k)
                else:
                    return None
            return d

        program_obj = deep_get(data, "props", "pageProps", "program") or deep_get(data, "program") or data
        if isinstance(program_obj, dict):
            name = program_obj.get("name") or program_obj.get("companyName") or name
            handle = program_obj.get("handle") or program_obj.get("slug") or handle
            description = program_obj.get("description") or program_obj.get("brief")
            tags = program_obj.get("tags", []) or []
            max_bounty = program_obj.get("maxBounty") or program_obj.get("max_bounty")
            min_bounty = program_obj.get("minBounty") or program_obj.get("min_bounty")
            is_paid = bool(program_obj.get("bounty") or program_obj.get("offersBounty"))
            is_private = bool(program_obj.get("private") or program_obj.get("isPrivate"))
        else:
            description = None
            tags = []
            max_bounty = None
            min_bounty = None
            is_paid = False
            is_private = False

        # Parse scope: Intigriti stores domains/targets in a structured array
        in_scope: list[ScopeAsset] = []
        out_of_scope: list[ScopeAsset] = []
        domains_data = deep_get(data, "props", "pageProps", "domains") or deep_get(program_obj, "domains") or []
        if isinstance(domains_data, list):
            for d in domains_data:
                if not isinstance(d, dict):
                    continue
                endpoint = d.get("endpoint") or d.get("host") or d.get("url") or d.get("name", "")
                is_in = bool(d.get("inScope", True))
                sev = Severity.normalize(d.get("maxSeverity", ""))
                asset = ScopeAsset(
                    target=endpoint,
                    asset_type=AssetType.classify(endpoint),
                    in_scope=is_in,
                    max_severity=sev,
                    description=d.get("description"),
                )
                (in_scope if is_in else out_of_scope).append(asset)

        # Build bounty table from max_bounty (Intigriti often shows range)
        bounty_table: list[BountyRange] = []
        try:
            if max_bounty is not None:
                max_amt = float(str(max_bounty).replace(",", "").replace("€", "").replace("$", ""))
                bounty_table.append(BountyRange(severity=Severity.CRITICAL, min_amount=None, max_amount=max_amt))
            else:
                max_amt = None
        except (TypeError, ValueError):
            max_amt = None
        try:
            min_amt = float(str(min_bounty).replace(",", "").replace("€", "").replace("$", "")) if min_bounty else None
        except (TypeError, ValueError):
            min_amt = None

        rules = ProgramRules(
            safe_harbor=deep_get(program_obj, "safeHarbor") if isinstance(program_obj, dict) else None,
            disclosure_policy=deep_get(program_obj, "disclosurePolicy") if isinstance(program_obj, dict) else None,
            submission_format="Report via Intigriti platform",
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
            is_paid=is_paid,
            is_private=is_private,
            program_type="bug_bounty",
            scope=ProgramScope(in_scope=in_scope, out_of_scope=out_of_scope),
            rules=rules,
            description=description,
            tags=tags if isinstance(tags, list) else [],
            source_url=source_url,  # type: ignore[arg-type]
            extracted_at=self._now(),
            raw_data=data,
        )
