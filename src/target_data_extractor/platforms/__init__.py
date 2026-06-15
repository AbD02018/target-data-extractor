"""Platform extractors and auto-detection by URL."""

from __future__ import annotations

from urllib.parse import urlparse

from target_data_extractor.exceptions import PlatformNotSupportedError
from target_data_extractor.platforms.base import BasePlatform
from target_data_extractor.platforms.bugcrowd import BugcrowdPlatform
from target_data_extractor.platforms.bugrap import BugrapPlatform
from target_data_extractor.platforms.hackenproof import HackenProofPlatform
from target_data_extractor.platforms.hackerone import HackerOnePlatform
from target_data_extractor.platforms.immunefi import ImmunefiPlatform
from target_data_extractor.platforms.intigriti import IntigritiPlatform
from target_data_extractor.platforms.yeswehack import YesWeHackPlatform

__all__ = [
    "BasePlatform",
    "HackerOnePlatform",
    "BugcrowdPlatform",
    "IntigritiPlatform",
    "ImmunefiPlatform",
    "YesWeHackPlatform",
    "BugrapPlatform",
    "HackenProofPlatform",
    "detect_platform",
    "get_platform",
    "list_platforms",
]


# Registry: instantiate once, reuse across calls
_REGISTRY: dict[str, type[BasePlatform]] = {
    "hackerone": HackerOnePlatform,
    "bugcrowd": BugcrowdPlatform,
    "intigriti": IntigritiPlatform,
    "immunefi": ImmunefiPlatform,
    "yeswehack": YesWeHackPlatform,
    "bugrap": BugrapPlatform,
    "hackenproof": HackenProofPlatform,
}


def list_platforms() -> list[str]:
    """Return all supported platform names."""
    return sorted(_REGISTRY.keys())


def detect_platform(url: str) -> str:
    """Detect which platform a URL belongs to.

    Returns the platform name (e.g. "hackerone") or raises PlatformNotSupportedError.
    """
    try:
        host = urlparse(url).netloc.lower()
    except Exception as exc:
        raise PlatformNotSupportedError(url) from exc

    for name, cls in _REGISTRY.items():
        if any(h in host for h in cls.hostnames):
            return name

    raise PlatformNotSupportedError(url, supported=list_platforms())


def get_platform(name: str, *, bypass: object | None = None) -> BasePlatform:
    """Get a platform extractor instance by name (e.g. "hackerone")."""
    name = name.strip().lower()
    if name not in _REGISTRY:
        raise PlatformNotSupportedError(
            f"Unknown platform {name!r}",
            supported=list_platforms(),
        )
    cls = _REGISTRY[name]
    if bypass is not None:
        return cls(bypass=bypass)  # type: ignore[arg-type]
    return cls()
