"""Test base platform utilities (URL parsing, handle extraction)."""

from __future__ import annotations

import pytest

from target_data_extractor.platforms.base import BasePlatform


def test_matches_url_substring():
    class FakePlatform(BasePlatform):
        platform_name = "fake"
        hostnames = ["example.com"]

    assert FakePlatform.matches_url("https://example.com/foo")
    assert FakePlatform.matches_url("https://www.example.com/foo")
    assert not FakePlatform.matches_url("https://other.com/foo")


def test_matches_url_garbage():
    class FakePlatform(BasePlatform):
        platform_name = "fake"
        hostnames = ["example.com"]

    assert not FakePlatform.matches_url("not a url")


def test_extract_handle_simple():
    class FakePlatform(BasePlatform):
        platform_name = "fake"
        hostnames = ["example.com"]

    assert FakePlatform.extract_handle_from_url("https://example.com/security") == "security"


def test_extract_handle_with_prefix():
    class FakePlatform(BasePlatform):
        platform_name = "fake"
        hostnames = ["example.com"]

    assert FakePlatform.extract_handle_from_url("https://example.com/researcher/programs/foo") == "foo"
    assert FakePlatform.extract_handle_from_url("https://example.com/programs/foo") == "foo"


def test_extract_handle_empty():
    class FakePlatform(BasePlatform):
        platform_name = "fake"
        hostnames = ["example.com"]

    assert FakePlatform.extract_handle_from_url("https://example.com/") is None
    assert FakePlatform.extract_handle_from_url("https://example.com") is None


def test_bounty_table_from_dict(sample_h1_program):
    from target_data_extractor.models import Severity
    # Create a minimal concrete subclass to bypass ABC
    class _Stub(BasePlatform):
        platform_name = "stub"
        hostnames = ["stub.test"]
        async def extract(self, url, **kw):  # noqa: ARG002
            raise NotImplementedError
    extractor = _Stub.__new__(_Stub)  # bypass __init__
    table, min_a, max_a = extractor._bounty_table_from_dict(
        {
            "critical": 50000,
            "high": {"min": 10000, "max": 30000},
            "medium": [3000, 5000, 7000],
        }
    )
    assert len(table) == 3
    assert max_a == 50000
    assert min_a == 3000
    severities = {b.severity for b in table}
    assert Severity.CRITICAL in severities
    assert Severity.HIGH in severities
    assert Severity.MEDIUM in severities
