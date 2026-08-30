#!/usr/bin/env python3
"""OPT-IN live end-to-end solve runner — only run when explicitly requested.

This script spends real NopeCHA credits and hits live demo pages. It is NOT part
of the default pytest suite on purpose.

Usage:
    source .env && .venv/bin/python e2e_solve_test.py [url]
    # optional URL argument; defaults to the hCaptcha demo page
"""
import os
import re
import sys
from typing import Any

from auto_captcha_solver import auto_solve_url

DEFAULT_URL = "https://accounts.hcaptcha.com/demo"

# Novada auth delimiter is '-', so no segment value may contain a hyphen.
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")


def _sticky_username(base_user: str, zone: str, region: str, session: str, sess_time: int) -> str:
    """Build a Novada sticky-session username.

    Grammar (developer.novada.com, rotating residential → session-type):
        USERNAME-zone-<zone>[-region-XX][-city-CITY]-session-<id>[-sessTime-<N>]

    - ``zone``  is the PRODUCT zone: ``res`` (residential), ``isp``, ``dcp``,
      ``mob``. NOT a region — the ``.na.`` in an account host is the host's
      region and never appears in the username.
    - ``region`` is an optional 2-letter country code (``us`` etc.).
    - ``session`` must be alphanumeric/underscore, no hyphens, <= 64 chars.
    - ``sessTime`` is the TTL in minutes (default 5 for res, max 120). Set to
      the max when the browser outlives a short session (a rotated IP breaks
      the captcha token's IP binding).
    """
    parts = [base_user, f"zone-{zone}"]
    if region:
        parts.append(f"region-{region}")
    if session:
        parts.append(f"session-{session}")
        parts.append(f"sessTime-{sess_time}")
    return "-".join(parts)


def proxy_from_env() -> dict[str, Any] | None:
    """Build a proxy dict from NOVADA_* env vars if all required ones are set.

    NOVADA_HOST/PORT required; USER/PASS optional (auth). For a ROTATING
    residential pool, set NOVADA_SESSION to any id (alphanumeric, no hyphens)
    to enable a sticky session (same IP for the whole run) — REQUIRED for
    Turnstile, where the solver's exit IP must equal the browser's. The
    sticky username is built as
    ``USERNAME-zone-<zone>[-region-XX]-session-<id>-sessTime-<N>``.

    A dedicated single-IP host (or a non-residential setup) needs no session
    suffix — leave NOVADA_SESSION unset and the username is passed through.

    Env: NOVADA_HOST, NOVADA_PORT, NOVADA_USER, NOVADA_PASS, NOVADA_SCHEME,
         NOVADA_ZONE (default res), NOVADA_REGION (2-letter, e.g. us),
         NOVADA_SESSION (id), NOVADA_SESS_TIME (default 120, max 120).
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
        if session:
            # Validate the session id against Novada's documented charset.
            clean = session.replace("-", "")
            if not _SESSION_ID_RE.match(clean):
                raise SystemExit(
                    "NOVADA_SESSION must be letters/numbers/underscore only "
                    f"(no hyphens), max 64 chars. Got: {session!r}"
                )
            zone = os.environ.get("NOVADA_ZONE", "res").strip() or "res"
            region = os.environ.get("NOVADA_REGION", "").strip()
            try:
                sess_time = int(os.environ.get("NOVADA_SESS_TIME", "120").strip() or 120)
            except ValueError:
                sess_time = 120
            sess_time = max(1, min(sess_time, 120))
            proxy["username"] = _sticky_username(user, zone, region, clean, sess_time)
            print(
                f"Sticky session enabled (zone={zone}, region={region or 'any'}, "
                f"id={clean}, ttl={sess_time}min)"
            )
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
