"""Captcha solve provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..types import CaptchaResult


class CaptchaProvider(ABC):
    """Backend that submits captchas and returns solved tokens."""

    name: str = "base"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    @abstractmethod
    def get_credits(self) -> int:
        """Return remaining account balance/credits."""

    @abstractmethod
    def solve(
        self,
        captcha_type: str,
        sitekey: str,
        url: str,
        *,
        poll_interval: float,
        max_polls: int,
        timeout_sec: float,
        proxy: dict[str, Any] | None = None,
        useragent: str | None = None,
        cookies: list[dict[str, Any]] | None = None,
        data: dict[str, Any] | None = None,
    ) -> CaptchaResult:
        """Solve a captcha and return the token.

        Args:
            captcha_type: One of the provider's supported types.
            sitekey: Public site key of the captcha.
            url: URL of the page hosting the captcha.
            poll_interval: Seconds between result polls.
            max_polls: Maximum number of poll attempts.
            timeout_sec: Overall wall-clock budget for the solve.
            proxy: Optional proxy dict (scheme/host/port/username/password).
            useragent: Real browser User-Agent to match the solve context.
            cookies: Browser cookies (Playwright ``context.cookies()`` shape)
                so the solve context matches the presenting browser.
            data: Captcha-type metadata (e.g. reCAPTCHA v3 ``action``/``s``,
                Turnstile ``action``/``cdata``). Ignored by providers that
                don't support it.
        """

    @classmethod
    @abstractmethod
    def supported_types(cls) -> list[str]:
        """Captcha types with stable support on this provider."""

    @classmethod
    @abstractmethod
    def experimental_types(cls) -> list[str]:
        """Captcha types that may be slow or unreliable on this provider."""
