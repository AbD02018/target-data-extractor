"""Bugrap platform extractor (smaller, public-only).

Bugrap is a public bug bounty platform. No public API documented. We scrape the
public program page at bugrap.io/<handle>.
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


class BugrapPlatform(BasePlatform):
    platform_name = "bugrap"
    hostnames = ["bugrap.io"]
    requires_auth = False

    BASE_URL = "https://bugrap.io"

    async def extract(self, url: str, **kwargs: Any) -> BountyProgram:
        handle = self.extract_handle_from_url(url)
        if not handle:
            raise ParseError(f"Could not extract program handle from URL: {url}", platform=self.platform_name)
        candidates = [
            f"{self.BASE_URL}/{handle}",
            f"{self.BASE_URL}/programs/{handle}",
            url,
        ]
        html = ""
        for u in candidates:
            try:
                html = await self._fetch_html(u)
                if html and len(html) > 1000:
                    break
            except Exception as exc:  # noqa: BLE001
                logger.debug("bugrap fetch %s failed: %s", u, exc)
        if not html:
            raise ParseError(f"Could not fetch Bugrap page for {handle}", platform=self.platform_name)
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

        program = (
            deep_get(data, "props", "pageProps", "program")
            or deep_get(data, "program")
            or data
        )
        if not isinstance(program, dict):
            program = {}

        name = program.get("name") or program.get("title") or handle
        description = program.get("description") or program.get("brief")

        in_scope: list[ScopeAsset] = []
        out_of_scope: list[ScopeAsset] = []
        targets = (
            program.get("targets", [])
            or program.get("scope", [])
            or deep_get(program, "scope", "targets")
            or []
        )
        for t in targets if isinstance(targets, list) else []:
            if not isinstance(t, dict):
                continue
            target = t.get("target") or t.get("url") or t.get("host") or t.get("name", "")
            is_in = bool(t.get("in_scope", True))
            sev = Severity.normalize(t.get("max_severity", ""))
            asset = ScopeAsset(
                target=target,
                asset_type=AssetType.classify(target),
                in_scope=is_in,
                max_severity=sev,
                description=t.get("description"),
            )
            (in_scope if is_in else out_of_scope).append(asset)

        max_amt: float | None = None
        min_amt: float | None = None
        bounty_table: list[BountyRange] = []
        rewards = program.get("rewards") or program.get("bounty") or {}
        if isinstance(rewards, dict):
            bounty_table, min_amt, max_amt = self._bounty_table_from_dict(rewards)
        try:
            if not max_amt:
                raw_max = program.get("max_reward") or program.get("maxBounty")
                if raw_max:
                    max_amt = float(str(raw_max).replace(",", "").replace("$", ""))
                    bounty_table.append(BountyRange(severity=Severity.CRITICAL, min_amount=None, max_amount=max_amt))
        except (TypeError, ValueError):
            pass

        rules = ProgramRules(
            safe_harbor=program.get("safe_harbor"),
            submission_format="Report via Bugrap platform",
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
            raw_data=data,
        )
