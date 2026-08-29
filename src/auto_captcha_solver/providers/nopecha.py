"""NopeCHA Token API provider."""

from __future__ import annotations

import time
from typing import Any

import requests

from ..types import CaptchaResult
from .base import CaptchaProvider

TOKEN_ENDPOINTS = {
    "hcaptcha": "/v1/token/hcaptcha",
    "recaptcha2": "/v1/token/recaptcha2",
    "recaptcha3": "/v1/token/recaptcha3",
}

# Experimental — NopeCHA queue extremely slow (5-10+ min), needs proxy
EXPERIMENTAL_ENDPOINTS = {
    "turnstile": "/v1/token/turnstile",
}

# Error codes documented at https://nopecha.com/api-reference (error section)
ERROR_MESSAGES = {
    9: "Unknown error",
    10: "Invalid request",
    11: "Rate limit reached",
    12: "Banned IP (free tier ineligible)",
    14: "Incomplete job",
    15: "Invalid key",
    16: "Out of credit",
    17: "Update required",
    18: "Feature unavailable for current plan",
}


def describe_error(code: Any, message: str | None = None) -> str:
    """Human-readable description for a NopeCHA error code."""
    known = ERROR_MESSAGES.get(code)
    detail = f" ({message})" if message else ""
    return f"{known or f'error {code}'}{detail}"


def _normalize_cookies(
    cookies: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Convert Playwright ``context.cookies()`` output to NopeCHA cookie shape.

    NopeCHA requires name/value/domain/path plus explicit boolean flags
    (hostOnly/httpOnly/secure/session). Playwright supplies most of these;
    we fill sane defaults and derive the ones it omits so the solve context
    matches the presenting browser.
    """
    if not cookies:
        return []
    out: list[dict[str, Any]] = []
    for c in cookies:
        name = c.get("name")
        value = c.get("value")
        domain = c.get("domain")
        if name is None or value is None or not domain:
            continue
        expires = c.get("expires", c.get("expirationDate", -1))
        # Playwright uses -1 for session cookies; NopeCHA marks them via `session`.
        is_session = expires in (-1, None) or (isinstance(expires, (int, float)) and expires < 0)
        entry: dict[str, Any] = {
            "name": str(name),
            "value": str(value),
            "domain": str(domain),
            "path": str(c.get("path", "/")),
            # host-only when the domain is not a leading-dot wildcard cookie
            "hostOnly": bool(c.get("hostOnly", not str(domain).startswith("."))),
            "httpOnly": bool(c.get("httpOnly", False)),
            "secure": bool(c.get("secure", False)),
            "session": bool(c.get("session", is_session)),
        }
        if not entry["session"] and isinstance(expires, (int, float)) and expires > 0:
            entry["expirationDate"] = int(expires)
        out.append(entry)
    return out


class NopechaProvider(CaptchaProvider):
    name = "nopecha"
    BASE_URL = "https://api.nopecha.com"

    def __init__(self, api_key: str):
        super().__init__(api_key)

    def _api(
        self, path: str, method: str = "GET", body: dict[str, Any] | None = None
    ) -> tuple[int, dict[str, Any]]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Basic {self.api_key}",
        }
        try:
            response = requests.request(
                method,
                f"{self.BASE_URL}{path}",
                headers=headers,
                json=body,
                timeout=30,
            )
        except requests.exceptions.RequestException as exc:
            # Network-level failure (timeout, DNS, connection) — surface it as a
            # structured failure instead of crashing the caller.
            return 0, {"error": "network", "message": str(exc)}
        try:
            return response.status_code, response.json()
        except Exception:
            return response.status_code, {"error": "invalid_json"}

    def get_credits(self) -> int:
        status, data = self._api("/v1/status")
        if status == 200:
            return int(data.get("credit", 0))
        return 0

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
        start = time.time()
        endpoint = TOKEN_ENDPOINTS.get(captcha_type) or EXPERIMENTAL_ENDPOINTS.get(captcha_type)
        if not endpoint:
            supported = list(TOKEN_ENDPOINTS.keys()) + list(EXPERIMENTAL_ENDPOINTS.keys())
            return CaptchaResult(
                success=False,
                captcha_type=captcha_type,
                error=f"unsupported type: {captcha_type}. Supported: {supported}",
                elapsed_sec=time.time() - start,
            )

        body: dict[str, Any] = {"sitekey": sitekey, "url": url}
        if proxy:
            body["proxy"] = proxy
        if useragent:
            body["useragent"] = useragent
        normalized_cookies = _normalize_cookies(cookies)
        if normalized_cookies:
            body["cookie"] = normalized_cookies
        if data:
            body["data"] = data

        status, resp = self._api(endpoint, "POST", body)
        if status != 200 or not resp.get("data"):
            if resp.get("error") == "network":
                error = f"submit failed (network): {resp.get('message', '')}"
            else:
                error = f"submit failed: {describe_error(resp.get('error'), resp.get('message'))}"
            return CaptchaResult(
                success=False,
                captcha_type=captcha_type,
                error=error,
                elapsed_sec=time.time() - start,
            )

        job_id = resp["data"]
        for attempt in range(max_polls):
            if time.time() - start > timeout_sec:
                break

            time.sleep(poll_interval)
            status, result = self._api(f"{endpoint}?id={job_id}")

            err = result.get("error")
            if err == 14:
                continue
            if err == "network":
                # Transient network glitch during polling — try again (bounded
                # by max_polls / timeout_sec).
                continue
            if err:
                return CaptchaResult(
                    success=False,
                    captcha_type=captcha_type,
                    error=describe_error(err, result.get("message")),
                    attempts=attempt + 1,
                    elapsed_sec=time.time() - start,
                )
            if result.get("data"):
                token = result["data"]
                if isinstance(token, list):
                    token = token[0]
                return CaptchaResult(
                    success=True,
                    captcha_type=captcha_type,
                    token=str(token),
                    attempts=attempt + 1,
                    elapsed_sec=time.time() - start,
                )

        return CaptchaResult(
            success=False,
            captcha_type=captcha_type,
            error=f"timeout after {timeout_sec:.0f}s",
            attempts=max_polls,
            elapsed_sec=time.time() - start,
        )

    @classmethod
    def supported_types(cls) -> list[str]:
        return list(TOKEN_ENDPOINTS.keys())

    @classmethod
    def experimental_types(cls) -> list[str]:
        return list(EXPERIMENTAL_ENDPOINTS.keys())
