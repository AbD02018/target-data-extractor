"""Pydantic data models for normalized bug bounty program data.

The output schema is the **same** for all 7 platforms. Each platform extractor
parses its native response and produces a `BountyProgram` instance, so consumers
never have to deal with platform-specific shapes.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class AssetType(str, Enum):
    """Type of in-scope asset."""

    DOMAIN = "domain"
    WILDCARD = "wildcard"
    URL = "url"
    IP_ADDRESS = "ip"
    IP_RANGE = "ip_range"
    CIDR = "cidr"
    ANDROID_APP = "android_app"
    IOS_APP = "ios_app"
    MOBILE_APP = "mobile_app"
    SOURCE_CODE = "source_code"
    BINARY = "binary"
    DOCKER_IMAGE = "docker_image"
    SMART_CONTRACT = "smart_contract"
    EXECUTABLE = "executable"
    OTHER = "other"

    @classmethod
    def classify(cls, raw: str) -> "AssetType":
        """Best-effort classification from a free-form asset string."""
        s = raw.strip().lower()
        if s.startswith("*."):
            return cls.WILDCARD
        if s.startswith(("http://", "https://")):
            return cls.URL
        if "/" in s and all(p.isdigit() for p in s.split("/")[0].split(".")):
            return cls.CIDR
        if "-" in s and all(p.isdigit() for p in s.split("-")[0].split(".")):
            return cls.IP_RANGE
        if all(p.isdigit() for p in s.split(".")) and len(s.split(".")) == 4:
            return cls.IP_ADDRESS
        if s.endswith(".sol") or "smart contract" in s or "0x" in s and len(s) == 42:
            return cls.SMART_CONTRACT
        if s.endswith(".apk") or "android" in s:
            return cls.ANDROID_APP
        if s.endswith(".ipa") or "ios" in s:
            return cls.IOS_APP
        if "." in s:
            return cls.DOMAIN
        return cls.OTHER


class Severity(str, Enum):
    """Vulnerability severity tiers (best-effort normalization)."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"
    UNKNOWN = "unknown"

    @classmethod
    def normalize(cls, raw: str | None) -> "Severity":
        if not raw:
            return cls.UNKNOWN
        s = raw.strip().lower()
        if s.startswith("crit"):
            return cls.CRITICAL
        if s.startswith("high") or s == "h":
            return cls.HIGH
        if s.startswith("med") or s == "m":
            return cls.MEDIUM
        if s.startswith("low") or s == "l":
            return cls.LOW
        if s in ("p0", "p1", "p2", "p3", "p4", "p5"):
            p0_p1 = {"p0", "p1"}
            p2 = {"p2"}
            p3 = {"p3"}
            p4 = {"p4"}
            p5 = {"p5"}
            if s in p0_p1:
                return cls.CRITICAL
            if s in p2:
                return cls.HIGH
            if s in p3:
                return cls.MEDIUM
            if s in p4:
                return cls.LOW
            if s in p5:
                return cls.NONE
        return cls.UNKNOWN


class ScopeAsset(BaseModel):
    """A single in-scope or out-of-scope asset."""

    model_config = ConfigDict(frozen=False, extra="ignore")

    target: str = Field(..., description="The asset identifier (domain, URL, repo, etc.)")
    asset_type: AssetType = Field(..., description="Classified asset type")
    in_scope: bool = Field(default=True, description="True if in-scope, False if out-of-scope")
    max_severity: Severity = Field(default=Severity.UNKNOWN)
    description: str | None = None
    tags: list[str] = Field(default_factory=list)


class BountyRange(BaseModel):
    """Bounty range for a given severity tier (currency in USD)."""

    severity: Severity
    min_amount: float | None = None
    max_amount: float | None = None
    currency: str = "USD"

    @field_validator("min_amount", "max_amount", mode="before")
    @classmethod
    def _coerce_float(cls, v: Any) -> float | None:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            v = v.replace(",", "").replace("$", "").strip()
        try:
            return float(v)
        except (TypeError, ValueError):
            return None


class ProgramRules(BaseModel):
    """Program rules and submission requirements."""

    model_config = ConfigDict(extra="ignore")

    safe_harbor: bool | None = None
    disclosure_policy: str | None = None
    requires_2fa: bool | None = None
    requires_kyc: bool | None = None
    requires_nda: bool | None = None
    response_time_sla: str | None = None
    submission_format: str | None = None
    rules_text: str | None = None
    prohibited_activities: list[str] = Field(default_factory=list)
    rewards_for_duplicate: bool | None = None
    paid_program: bool | None = None
    managed_program: bool | None = None


class ProgramScope(BaseModel):
    """Structured scope: in-scope and out-of-scope assets."""

    model_config = ConfigDict(extra="ignore")

    in_scope: list[ScopeAsset] = Field(default_factory=list)
    out_of_scope: list[ScopeAsset] = Field(default_factory=list)

    @property
    def in_scope_count(self) -> int:
        return len(self.in_scope)

    @property
    def out_of_scope_count(self) -> int:
        return len(self.out_of_scope)

    @property
    def wildcards(self) -> list[ScopeAsset]:
        return [a for a in self.in_scope if a.asset_type == AssetType.WILDCARD]

    @property
    def domains(self) -> list[ScopeAsset]:
        return [a for a in self.in_scope if a.asset_type == AssetType.DOMAIN]

    @property
    def smart_contracts(self) -> list[ScopeAsset]:
        return [a for a in self.in_scope if a.asset_type == AssetType.SMART_CONTRACT]


class BountyProgram(BaseModel):
    """Normalized bug bounty program data. Identical schema across all 7 platforms."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    # Identity
    platform: str = Field(..., description="hackerone | bugcrowd | intigriti | immunefi | yeswehack | bugrap | hackenproof")
    program_handle: str = Field(..., description="URL-safe program identifier (slug)")
    program_name: str = Field(..., description="Display name of the program")
    program_url: HttpUrl = Field(..., description="Canonical URL on the platform")

    # Bounty & program type
    bounty_table: list[BountyRange] = Field(default_factory=list)
    max_bounty_usd: float | None = None
    min_bounty_usd: float | None = None
    is_paid: bool = False
    is_private: bool = False
    program_type: str | None = None  # web2 | web3 | mobile | smart_contract | bug_bounty | vrp

    # Scope
    scope: ProgramScope = Field(default_factory=ProgramScope)

    # Rules
    rules: ProgramRules = Field(default_factory=ProgramRules)

    # Meta
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    submission_count: int | None = None
    resolved_count: int | None = None
    launch_date: datetime | None = None
    last_updated: datetime | None = None

    # Source tracking
    source_url: HttpUrl | None = None
    extracted_at: datetime = Field(default_factory=lambda: datetime.utcnow())
    extractor_version: str = "0.1.0"
    raw_data: dict[str, Any] | None = Field(default=None, description="Original platform response (debugging)")

    @field_validator("platform", mode="before")
    @classmethod
    def _validate_platform(cls, v: str) -> str:
        valid = {"hackerone", "bugcrowd", "intigriti", "immunefi", "yeswehack", "bugrap", "hackenproof"}
        v = v.strip().lower()
        if v not in valid:
            raise ValueError(f"platform must be one of {valid}, got {v!r}")
        return v

    def to_summary(self) -> dict[str, Any]:
        """Compact summary dict for quick display."""
        return {
            "platform": self.platform,
            "program": self.program_name,
            "handle": self.program_handle,
            "url": str(self.program_url),
            "is_paid": self.is_paid,
            "is_private": self.is_private,
            "max_bounty_usd": self.max_bounty_usd,
            "in_scope_count": self.scope.in_scope_count,
            "out_of_scope_count": self.scope.out_of_scope_count,
            "wildcard_count": len(self.scope.wildcards),
            "smart_contract_count": len(self.scope.smart_contracts),
        }
