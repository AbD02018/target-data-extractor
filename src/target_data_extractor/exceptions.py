"""Custom exception hierarchy for target-data-extractor."""

from __future__ import annotations


class ExtractorError(Exception):
    """Base exception for all extractor errors."""

    def __init__(self, message: str, *, platform: str | None = None, url: str | None = None) -> None:
        self.platform = platform
        self.url = url
        super().__init__(self._format(message))

    def _format(self, message: str) -> str:
        parts = [message]
        if self.platform:
            parts.append(f"[platform={self.platform}]")
        if self.url:
            parts.append(f"[url={self.url}]")
        return " ".join(parts)


class PlatformNotSupportedError(ExtractorError):
    """URL does not match any known bug bounty platform."""

    def __init__(self, url: str, supported: list[str] | None = None) -> None:
        self.supported = supported or []
        msg = f"URL does not match any known platform"
        if self.supported:
            msg += f" (supported: {', '.join(self.supported)})"
        super().__init__(msg, url=url)


class NetworkError(ExtractorError):
    """Network-level failure (DNS, TCP, timeout, connection reset)."""


class AuthenticationError(ExtractorError):
    """API token invalid, missing, or expired."""


class RateLimitError(ExtractorError):
    """Platform rate-limited the request."""

    def __init__(self, message: str, *, retry_after: int | None = None, **kwargs: object) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class AntiBotError(ExtractorError):
    """Anti-bot challenge (Cloudflare/DataDome/Turnstile) could not be bypassed."""


class ParseError(ExtractorError):
    """HTML/JSON response could not be parsed into expected schema."""
