"""Base platform extractor.

All platform extractors inherit from `BasePlatform` and implement:
  - `platform_name: str`  (e.g. "hackerone")
  - `hostnames: list[str]` (e.g. ["hackerone.com"])
  - `async def extract(url: str, **kwargs) -> BountyProgram`
  - optional: `async def list_programs(**kwargs) -> list[BountyProgram]`
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, ClassVar
from urllib.parse import urlparse

from target_data_extractor.bypass import BypassClient, BypassConfig
from target_data_extractor.exceptions import NetworkError, ParseError
from target_data_extractor.models import BountyProgram, BountyRange, Severity

logger = logging.getLogger(__name__)


class BasePlatform(ABC):
    """Abstract base for all 7 platform extractors."""

    platform_name: ClassVar[str] = ""
    hostnames: ClassVar[list[str]] = []
    requires_auth: ClassVar[bool] = False

    def __init__(self, bypass: BypassClient | None = None, config: BypassConfig | None = None) -> None:
        self.config = config or BypassConfig()
        self.bypass = bypass or BypassClient(self.config)

    @classmethod
    def matches_url(cls, url: str) -> bool:
        """Return True if this extractor can handle the given URL."""
        try:
            host = urlparse(url).netloc.lower()
        except Exception:
            return False
        return any(h in host for h in cls.hostnames)

    @classmethod
    def extract_handle_from_url(cls, url: str) -> str | None:
        """Extract the program handle/slug from a URL. Strips common generic prefixes."""
        try:
            path = urlparse(url).path.strip("/")
            if not path:
                return None
            parts = [p for p in path.split("/") if p]
            if not parts:
                return None
            # Generic platform prefixes to skip (Intigriti has 2 levels: researcher/programs/)
            generic_prefixes = {
                "researcher", "researchers",
                "programs", "program", "bounties", "bounty",
                "find", "p", "external", "b",
            }
            # Skip ALL leading generic prefixes, not just the first one
            while len(parts) > 1 and parts[0].lower() in generic_prefixes:
                parts = parts[1:]
            return parts[0]
        except Exception:
            return None

    @abstractmethod
    async def extract(self, url: str, **kwargs: Any) -> BountyProgram:
        """Extract program data from the given URL. Must be implemented per platform."""
        raise NotImplementedError

    async def list_programs(self, **kwargs: Any) -> list[BountyProgram]:  # noqa: ARG002
        """List public programs. Optional; default raises NotImplementedError."""
        raise NotImplementedError(f"{self.platform_name} does not support listing public programs")

    # --- shared helpers used by subclasses ---

    def _now(self) -> datetime:
        return datetime.utcnow()

    def _bounty_table_from_dict(self, data: Any) -> tuple[list[BountyRange], float | None, float | None]:
        """Parse common bounty table shapes into a normalized form."""
        table: list[BountyRange] = []
        max_amt: float | None = None
        min_amt: float | None = None
        if not isinstance(data, dict):
            return table, min_amt, max_amt
        for sev_key, val in data.items():
            sev = Severity.normalize(str(sev_key))
            if isinstance(val, (int, float)):
                lo = hi = float(val)
            elif isinstance(val, dict):
                lo = val.get("min") or val.get("min_amount")
                hi = val.get("max") or val.get("max_amount")
            elif isinstance(val, (list, tuple)) and val:
                nums: list[float] = []
                for item in val:
                    if isinstance(item, (int, float)):
                        nums.append(float(item))
                if nums:
                    lo = min(nums)
                    hi = max(nums)
                else:
                    continue
            else:
                continue
            table.append(BountyRange(severity=sev, min_amount=lo, max_amount=hi))
            if hi is not None and (max_amt is None or hi > max_amt):
                max_amt = hi
            if lo is not None and (min_amt is None or lo < min_amt):
                min_amt = lo
        return table, min_amt, max_amt

    async def _fetch_html(self, url: str, **kwargs: Any) -> str:
        """Fetch HTML using the bypass client."""
        try:
            resp = await self.bypass.get(url, **kwargs)
        except NetworkError as exc:
            raise NetworkError(f"Failed to fetch {url}: {exc}", url=url, platform=self.platform_name) from exc
        if resp.is_blocked:
            from target_data_extractor.exceptions import AntiBotError
            raise AntiBotError(
                f"Bypass strategies returned a block page for {url!r} (strategy={resp.strategy_used})",
                url=url,
                platform=self.platform_name,
            )
        return resp.text

    def _parse_html(self, html: str, parser: str = "lxml") -> Any:
        """Parse HTML using BeautifulSoup with the given parser."""
        try:
            from bs4 import BeautifulSoup
            return BeautifulSoup(html, parser)
        except Exception as exc:
            raise ParseError(f"Failed to parse HTML: {exc}", platform=self.platform_name) from exc
