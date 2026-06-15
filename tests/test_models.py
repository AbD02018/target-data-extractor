"""Test the public models and serialization round-trip."""

from __future__ import annotations

import json

from target_data_extractor.models import AssetType, BountyProgram, Severity


def test_asset_type_classify_wildcard():
    assert AssetType.classify("*.example.com") == AssetType.WILDCARD


def test_asset_type_classify_domain():
    assert AssetType.classify("example.com") == AssetType.DOMAIN


def test_asset_type_classify_url():
    assert AssetType.classify("https://example.com/api") == AssetType.URL


def test_asset_type_classify_cidr():
    assert AssetType.classify("10.0.0.0/8") == AssetType.CIDR


def test_asset_type_classify_ip():
    assert AssetType.classify("1.2.3.4") == AssetType.IP_ADDRESS


def test_asset_type_classify_smart_contract():
    assert AssetType.classify("0x7d2768dE32b0b80b7a3454c06BdAc94A69DDc7A9") == AssetType.SMART_CONTRACT
    assert AssetType.classify("contract.sol") == AssetType.SMART_CONTRACT


def test_asset_type_classify_other():
    assert AssetType.classify("???") == AssetType.OTHER


def test_severity_normalize_p_levels():
    assert Severity.normalize("p0") == Severity.CRITICAL
    assert Severity.normalize("p1") == Severity.CRITICAL
    assert Severity.normalize("p2") == Severity.HIGH
    assert Severity.normalize("p3") == Severity.MEDIUM
    assert Severity.normalize("p4") == Severity.LOW


def test_severity_normalize_words():
    assert Severity.normalize("Critical") == Severity.CRITICAL
    assert Severity.normalize("HIGH") == Severity.HIGH
    assert Severity.normalize("Medium") == Severity.MEDIUM


def test_severity_normalize_unknown():
    assert Severity.normalize(None) == Severity.UNKNOWN
    assert Severity.normalize("") == Severity.UNKNOWN
    assert Severity.normalize("banana") == Severity.UNKNOWN


def test_program_json_roundtrip(sample_h1_program):
    data = sample_h1_program.model_dump(mode="json")
    j = json.dumps(data)
    parsed = json.loads(j)
    assert parsed["platform"] == "hackerone"
    assert parsed["program_handle"] == "security"
    assert parsed["max_bounty_usd"] == 60000
    # in_scope_count is a property on ProgramScope, not serialized
    p2 = BountyProgram.model_validate(parsed)
    assert p2.program_name == sample_h1_program.program_name
    assert p2.scope.in_scope_count == 2
    assert p2.scope.wildcards[0].target == "*.github.com"


def test_program_invalid_platform_raises():
    from pydantic import ValidationError
    import pytest
    with pytest.raises(ValidationError):
        BountyProgram(
            platform="facebook",  # not supported
            program_handle="x",
            program_name="x",
            program_url="https://example.com",  # type: ignore[arg-type]
        )


def test_program_summary(sample_h1_program):
    s = sample_h1_program.to_summary()
    assert s["platform"] == "hackerone"
    assert s["program"] == "GitHub Security"
    assert s["wildcard_count"] == 1
    assert s["in_scope_count"] == 2


def test_bounty_range_currency_strip():
    from target_data_extractor.models import BountyRange, Severity
    r = BountyRange(severity=Severity.HIGH, min_amount="$1,000", max_amount="$5,000")
    assert r.min_amount == 1000.0
    assert r.max_amount == 5000.0
    assert r.currency == "USD"
