"""Shared fixtures and test config for target-data-extractor."""

from __future__ import annotations

import pytest

from target_data_extractor.models import (
    AssetType,
    BountyProgram,
    BountyRange,
    ProgramRules,
    ProgramScope,
    ScopeAsset,
    Severity,
)


@pytest.fixture
def sample_h1_program() -> BountyProgram:
    return BountyProgram(
        platform="hackerone",
        program_handle="security",
        program_name="GitHub Security",
        program_url="https://hackerone.com/security",  # type: ignore[arg-type]
        bounty_table=[
            BountyRange(severity=Severity.CRITICAL, min_amount=30000, max_amount=60000),
            BountyRange(severity=Severity.HIGH, min_amount=10000, max_amount=30000),
            BountyRange(severity=Severity.MEDIUM, min_amount=3000, max_amount=10000),
            BountyRange(severity=Severity.LOW, min_amount=500, max_amount=3000),
        ],
        max_bounty_usd=60000,
        min_bounty_usd=500,
        is_paid=True,
        is_private=False,
        program_type="bug_bounty",
        scope=ProgramScope(
            in_scope=[
                ScopeAsset(target="*.github.com", asset_type=AssetType.WILDCARD, in_scope=True, max_severity=Severity.CRITICAL),
                ScopeAsset(target="github.com", asset_type=AssetType.DOMAIN, in_scope=True),
            ],
            out_of_scope=[
                ScopeAsset(target="status.github.com", asset_type=AssetType.DOMAIN, in_scope=False),
            ],
        ),
        rules=ProgramRules(safe_harbor=True, disclosure_policy="Coordinated disclosure"),
        description="Bug bounty program for github.com",
        tags=["web", "open-source"],
        source_url="https://hackerone.com/security",  # type: ignore[arg-type]
    )


@pytest.fixture
def sample_immunefi_program() -> BountyProgram:
    return BountyProgram(
        platform="immunefi",
        program_handle="aave",
        program_name="Aave",
        program_url="https://immunefi.com/bounty/aave/",  # type: ignore[arg-type]
        bounty_table=[BountyRange(severity=Severity.CRITICAL, min_amount=None, max_amount=250000)],
        max_bounty_usd=250000,
        is_paid=True,
        program_type="smart_contract",
        scope=ProgramScope(
            in_scope=[
                ScopeAsset(
                    target="0x7d2768dE32b0b80b7a3454c06BdAc94A69DDc7A9",
                    asset_type=AssetType.SMART_CONTRACT,
                    in_scope=True,
                    max_severity=Severity.CRITICAL,
                ),
            ],
        ),
        rules=ProgramRules(requires_kyc=True, safe_harbor=True),
        source_url="https://immunefi.com/bounty/aave/",  # type: ignore[arg-type]
    )
