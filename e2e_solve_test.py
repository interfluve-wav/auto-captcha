#!/usr/bin/env python3
"""OPT-IN live end-to-end solve runner — only run when explicitly requested.

This script spends real NopeCHA credits and hits live demo pages. It is NOT part
of the default pytest suite on purpose.

Usage:
    source .env && .venv/bin/python e2e_solve_test.py [url]
    # optional URL argument; defaults to the hCaptcha demo page
"""
import os
import sys
from typing import Any

from auto_captcha_solver import auto_solve_url

DEFAULT_URL = "https://accounts.hcaptcha.com/demo"


def proxy_from_env() -> dict[str, Any] | None:
    """Build a proxy dict from NOVADA_* env vars if all required ones are set.

    NOVADA_HOST/PORT required; USER/PASS optional (auth). For ROTATING pools,
    set NOVADA_SESSION to any short id (no hyphens, <=8 chars) to enable a
    sticky session (same IP up to 120 min) — REQUIRED for Turnstile, where the
    solver's exit IP must equal the browser's for the whole solve. The sticky
    username is built as USERNAME-zone-<region>-<session_id> (Novada auth
    delimiter is '-', so the session id must not contain hyphens). A dedicated
    single-IP host needs no session suffix — leave NOVADA_SESSION unset.
    """
    host = os.environ.get("NOVADA_HOST", "").strip()
    port = os.environ.get("NOVADA_PORT", "").strip()
    if not (host and port):
        return None
    proxy: dict[str, Any] = {
        "scheme": os.environ.get("NOVADA_SCHEME", "http").strip() or "http",
        "host": host,
        "port": int(port),
    }
    user = os.environ.get("NOVADA_USER", "").strip()
    password = os.environ.get("NOVADA_PASS", "").strip()
    if user:
        session = os.environ.get("NOVADA_SESSION", "").strip()
        if session and "-zone-" not in user:
            # Build the sticky-session username: USERNAME-zone-<region>-<id>.
            # Region defaults to "na" (North America) unless the username or
            # NOVADA_REGION already carries a zone.
            region = os.environ.get("NOVADA_REGION", "na").strip() or "na"
            clean_session = session.replace("-", "")[:8]
            proxy["username"] = f"{user}-zone-{region}-{clean_session}"
            print(f"Sticky session enabled (id {clean_session}, region {region})")
        else:
            proxy["username"] = user
    if password:
        proxy["password"] = password
    print(f"Proxy enabled: {proxy['scheme']}://{host}:{port} (creds withheld)")
    return proxy


def main() -> int:
    key = os.environ.get("NOPECHA_API_KEY", "").strip()
    if not key:
        print("FAIL: NOPECHA_API_KEY not set. 'source .env' first.")
        return 2
    print(f"API key loaded ({len(key)} chars) — value withheld")

    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    proxy = proxy_from_env()

    # Turnstile sits in NopeCHA's slow experimental queue — give it room.
    solver_kwargs = {"timeout_sec": 300.0, "max_polls": 60}

    report = auto_solve_url(
        url,
        api_key=key,
        headless=True,
        stealth=True,
        proxy=proxy,
        humanize=True,
        retries=1,
        max_wait_sec=45,
        solver_kwargs=solver_kwargs,
        screenshot_path="/tmp/e2e_last.png",
    )

    print(f"\n{report.summary}")
    ok = [r for r in report.results if r.success]
    for r in report.results:
        status = "PASS" if r.success else f"FAIL: {r.error}"
        print(f"  {r.captcha_type}: {status} ({r.elapsed_sec:.1f}s, {r.attempts} polls)")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
