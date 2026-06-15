"""Test platform auto-detection by URL."""

from __future__ import annotations

import pytest

from target_data_extractor.exceptions import PlatformNotSupportedError
from target_data_extractor.platforms import detect_platform, list_platforms


def test_all_seven_platforms_supported():
    platforms = list_platforms()
    assert set(platforms) == {"hackerone", "bugcrowd", "intigriti", "immunefi", "yeswehack", "bugrap", "hackenproof"}


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://hackerone.com/security", "hackerone"),
        ("https://hackerone.com/github", "hackerone"),
        ("https://www.bugcrowd.com/programs/example", "bugcrowd"),
        ("https://bugcrowd.com/example", "bugcrowd"),
        ("https://www.intigriti.com/researcher/programs/cool", "intigriti"),
        ("https://app.intigriti.com/researcher/programs/cool", "intigriti"),
        ("https://immunefi.com/bounty/aave", "immunefi"),
        ("https://immunefi.com/bug-bounty/aave", "immunefi"),
        ("https://yeswehack.com/programs/coolco", "yeswehack"),
        ("https://www.yeswehack.com/programs/coolco", "yeswehack"),
        ("https://bugrap.io/some-program", "bugrap"),
        ("https://hackenproof.com/programs/some-program", "hackenproof"),
    ],
)
def test_detect_platform(url, expected):
    assert detect_platform(url) == expected


def test_detect_unknown_raises():
    with pytest.raises(PlatformNotSupportedError):
        detect_platform("https://example.com/program")
