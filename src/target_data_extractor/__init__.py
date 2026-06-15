"""target-data-extractor: Bug bounty program data extractor across 7 platforms."""

from target_data_extractor.models import (
    AssetType,
    BountyProgram,
    BountyRange,
    ProgramRules,
    ProgramScope,
    ScopeAsset,
    Severity,
)
from target_data_extractor.platforms import (
    BugcrowdPlatform,
    BugrapPlatform,
    HackenProofPlatform,
    HackerOnePlatform,
    ImmunefiPlatform,
    IntigritiPlatform,
    YesWeHackPlatform,
    detect_platform,
    get_platform,
)
from target_data_extractor.exceptions import (
    AntiBotError,
    AuthenticationError,
    ExtractorError,
    NetworkError,
    ParseError,
    PlatformNotSupportedError,
    RateLimitError,
)

__version__ = "0.1.0"
__all__ = [
    # Models
    "AssetType",
    "BountyProgram",
    "BountyRange",
    "ProgramRules",
    "ProgramScope",
    "ScopeAsset",
    "Severity",
    # Platform extractors
    "HackerOnePlatform",
    "BugcrowdPlatform",
    "IntigritiPlatform",
    "ImmunefiPlatform",
    "YesWeHackPlatform",
    "BugrapPlatform",
    "HackenProofPlatform",
    "detect_platform",
    "get_platform",
    # Exceptions
    "ExtractorError",
    "PlatformNotSupportedError",
    "NetworkError",
    "ParseError",
    "AuthenticationError",
    "RateLimitError",
    "AntiBotError",
]
