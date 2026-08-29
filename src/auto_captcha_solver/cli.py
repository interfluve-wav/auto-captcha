#!/usr/bin/env python3
"""
auto-captcha CLI — solve captchas from the command line.

Usage:
    auto-captcha solve --url https://example.com --key YOUR_KEY
    auto-captcha credits --key YOUR_KEY
    auto-captcha detect --url https://example.com --key YOUR_KEY
    auto-captcha solve --provider captchaai --key YOUR_CAPTCHAAI_KEY --url ...
"""

import argparse
import json
import os
import sys
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .solver import CaptchaSolver


def _add_provider_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--provider",
        choices=["nopecha", "captchaai"],
        default=os.environ.get("CAPTCHA_PROVIDER", "nopecha"),
        help="Solve provider (default: nopecha, or CAPTCHA_PROVIDER env)",
    )
    parser.add_argument(
        "--key",
        default="",
        help="API key (or set NOPECHA_API_KEY / CAPTCHAAI_API_KEY)",
    )


def _add_browser_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Launch headless (default; ignored with --cdp-url)",
    )
    parser.add_argument(
        "--no-headless",
        action="store_false",
        dest="headless",
        help="Launch with a visible browser (ignored with --cdp-url)",
    )
    parser.add_argument(
        "--cdp-url",
        default=os.environ.get("CAPTCHA_CDP_URL", "").strip() or None,
        help=(
            "Drive a remote/hosted browser over CDP instead of launching one "
            "(Browserless: https://<token>.browserless.io?token=*** Steel: its "
            "wss:// CDP endpoint). Or set CAPTCHA_CDP_URL."
        ),
    )
    parser.add_argument(
        "--cdp-header",
        action="append",
        default=[],
        metavar="KEY:VALUE",
        help=(
            "Extra header sent with the CDP handshake (repeatable). "
            "Browserless: --cdp-header Authorization:Bearer <token>"
        ),
    )


def _browser_headers(args) -> dict[str, str] | None:
    headers: dict[str, str] = {}
    for item in getattr(args, "cdp_header", []) or []:
        if ":" in item:
            k, v = item.split(":", 1)
            headers[k.strip()] = v.strip()
        else:
            raise SystemExit(f"--cdp-header must be KEY:VALUE, got: {item!r}")
    return headers or None


def _open_browser(pw, args, solver: "CaptchaSolver"):
    """Open the browser for a CLI run: connect over CDP when --cdp-url is set,
    otherwise launch locally (honoring --headless). Returns (browser, context,
    page). In CDP mode the solver's proxy is the only egress knob, so a
    Turnstile solve needs --cdp-url's browser egress IP to match the proxy IP."""
    cdp_url = getattr(args, "cdp_url", None)
    headers = _browser_headers(args)
    if cdp_url:
        browser = pw.chromium.connect_over_cdp(cdp_url, headers=headers or None)
    else:
        launch: dict[str, Any] = {"headless": args.headless, "args": ["--no-sandbox"]}
        if solver.proxy:
            scheme = solver.proxy.get("scheme", "http")
            host = solver.proxy.get("host")
            port = solver.proxy.get("port")
            if host and port:
                launch["proxy"] = {
                    "server": f"{scheme}://{host}:{port}",
                    "username": solver.proxy.get("username", ""),
                    "password": solver.proxy.get("password", ""),
                }
        browser = pw.chromium.launch(**launch)
    context = browser.new_context()
    from auto_captcha_solver import apply_stealth

    apply_stealth(context)
    return browser, context, context.new_page()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="auto-captcha",
        description="Universal captcha solver for Playwright automation",
    )
    sub = parser.add_subparsers(dest="command")

    solve_p = sub.add_parser("solve", help="Solve captchas on a URL")
    solve_p.add_argument("--url", required=True, help="Page URL with captcha")
    _add_provider_args(solve_p)
    _add_browser_args(solve_p)
    solve_p.add_argument("--timeout", type=float, default=120, help="Solve timeout in seconds")

    detect_p = sub.add_parser("detect", help="Detect captchas without solving")
    detect_p.add_argument("--url", required=True, help="Page URL")
    _add_provider_args(detect_p)
    _add_browser_args(detect_p)

    credits_p = sub.add_parser("credits", help="Check provider credit balance")
    _add_provider_args(credits_p)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    from auto_captcha_solver import CaptchaSolver
    from auto_captcha_solver.providers import resolve_api_key
    from auto_captcha_solver.types import sanitize_detect_results

    api_key = resolve_api_key(args.provider, args.key)
    if not api_key:
        print(
            f"Error: API key required for provider '{args.provider}'. "
            "Set NOPECHA_API_KEY or CAPTCHAAI_API_KEY, or pass --key",
            file=sys.stderr,
        )
        sys.exit(1)

    solver = CaptchaSolver(api_key=api_key, provider=args.provider)

    if args.command == "credits":
        credits = solver.get_credits()
        print(json.dumps({"provider": args.provider, "credits": credits}))

    elif args.command == "detect":
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser, context, page = _open_browser(p, args, solver)
            page.goto(args.url, timeout=30000)
            time.sleep(3)
            captchas = sanitize_detect_results(solver.detect(page))
            context.close()
            browser.close()
        print(json.dumps(captchas, indent=2, default=str))

    elif args.command == "solve":
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser, context, page = _open_browser(p, args, solver)
            page.goto(args.url, timeout=30000)
            time.sleep(3)
            if hasattr(args, "timeout"):
                solver.timeout_sec = args.timeout
            results = solver.auto_solve(page)
            context.close()
            browser.close()

        output = []
        for r in results:
            output.append(
                {
                    "provider": args.provider,
                    "type": r.captcha_type,
                    "success": r.success,
                    "token": r.token[:50] + "..." if len(r.token) > 50 else r.token,
                    "error": r.error,
                    "attempts": r.attempts,
                    "elapsed_sec": r.elapsed_sec,
                }
            )
        print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
