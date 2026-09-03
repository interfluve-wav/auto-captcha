#!/usr/bin/env python3
"""Benchmark: time a live solve for every captcha type the solver supports.

OPT-IN ONLY — spends real NopeCHA credits (~23) and hits live demo pages.

Usage:
    set -a && source .env && set +a && .venv/bin/python benchmark_all_types.py
"""
import json
import os
import sys
import time

# Reuse the e2e runner's proxy builder so the sticky session is identical.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from e2e_solve_test import proxy_from_env  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402
from playwright.sync_api import TimeoutError as PWTimeout  # noqa: E402

from auto_captcha_solver import (  # noqa: E402
    CaptchaSolver,
    apply_stealth,
    auto_solve_page,
    check_proxy_egress,
)

# (label, demo_url, expected_captcha_type, est_credits)
TARGETS = [
    ("hCaptcha v2",  "https://accounts.hcaptcha.com/demo",                                "hcaptcha",   1),
    ("reCAPTCHA v2", "https://www.google.com/recaptcha/api2/demo",                        "recaptcha2", 1),
    ("reCAPTCHA v3", "https://recaptcha-demo.appspot.com/recaptcha-v3-request-scores.php", "recaptcha3", 20),
    ("Turnstile",    "https://2captcha.com/demo/cloudflare-turnstile",                    "turnstile",  1),
]

# Published human solve-time norms (seconds).
HUMAN_NORMS = {
    "hcaptcha":   (8, 12),  # image grid selection
    "recaptcha2": (9, 15),  # image grid, sometimes 2 rounds
    "recaptcha3": (0, 0),   # invisible — no human interaction, score-based
    "turnstile":  (1, 2),   # single checkbox click, often zero interaction
}


def goto_resilient(page, url, widget_wait_ms=6000):
    """Navigate, tolerating long-lived demo pages that never fire domcontentloaded.

    Falls back to `commit` (navigation committed, HTML streaming) + a fixed wait
    for the widget to render — the documented pattern for Turnstile/reCAPTCHA
    pages that hold connections open.
    """
    try:
        page.goto(url, timeout=120000, wait_until="domcontentloaded")
        return
    except PWTimeout:
        pass
    # Retry with `commit`: fires as soon as the navigation commits, before load.
    page.goto(url, timeout=120000, wait_until="commit")
    page.wait_for_timeout(widget_wait_ms)


def main() -> int:
    key = os.environ.get("NOPECHA_API_KEY", "").strip()
    if not key:
        print("FAIL: NOPECHA_API_KEY not set.")
        return 2

    proxy = proxy_from_env()
    if not proxy:
        print("WARN: no proxy configured — Turnstile will fail (IP binding).")
    else:
        try:
            info = check_proxy_egress(proxy)
            print(f"Proxy preflight OK — egress {info['ip']} ({info['country']})")
        except RuntimeError as exc:
            print(f"Proxy preflight FAILED — {exc}")

    sess = os.environ.get("NOVADA_SESSION", "?")
    print(f"\nBenchmarking {len(TARGETS)} captcha types on sticky session {sess} "
          f"— same egress IP for all.\n")

    pw_proxy = None
    if proxy:
        pw_proxy = {
            "server": f"{proxy['scheme']}://{proxy['host']}:{proxy['port']}",
        }
        if proxy.get("username"):
            pw_proxy["username"] = proxy["username"]
            pw_proxy["password"] = proxy.get("password", "")

    solver = CaptchaSolver(
        api_key=key,
        timeout_sec=300.0,
        max_polls=60,
        proxy=proxy,
    )

    rows = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, proxy=pw_proxy)
        for label, url, ctype, credits in TARGETS:
            print(f"--- {label} ({ctype}) ---")
            print(f"    target: {url}")
            t0 = time.monotonic()
            ok = False
            solve_s = None
            polls = None
            err = None
            try:
                context = browser.new_context()
                apply_stealth(context)
                page = context.new_page()
                goto_resilient(page, url)
                report = auto_solve_page(
                    page, solver,
                    max_wait_sec=45,
                    humanize=True,
                    retries=1,
                    click_checkbox=True,
                )
                page.screenshot(path=f"/tmp/bench_{ctype}.png", full_page=True)
                context.close()

                match = next((r for r in report.results if r.captcha_type == ctype), None)
                if match is None and report.results:
                    match = report.results[0]
                ok = bool(match and match.success)
                solve_s = match.elapsed_sec if match else None
                polls = match.attempts if match else None
                err = match.error if match and not match.success else (
                    "no captcha detected" if not report.results else None)
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
            wall = time.monotonic() - t0

            h_lo, h_hi = HUMAN_NORMS.get(ctype, (None, None))
            human_str = (f"{h_lo}-{h_hi}s" if h_hi else "0s (invisible)") if h_lo is not None else "?"
            rows.append({
                "type": ctype, "label": label, "success": ok,
                "solve_sec": round(solve_s, 1) if solve_s is not None else None,
                "wall_sec": round(wall, 1), "polls": polls, "error": err,
                "est_credits": credits, "human_norm_sec": human_str,
            })
            status = "PASS" if ok else f"FAIL ({err})"
            ss = f"{solve_s:.1f}s" if solve_s is not None else "-"
            print(f"    {status} — solve {ss}, wall {wall:.1f}s, {polls} polls\n")
        browser.close()

    # summary table
    print("=" * 80)
    print(f"{'Type':<14} {'Result':<8} {'Solver':>8} {'Wall':>8} {'Polls':>6}  {'Human norm':>12}")
    print("-" * 80)
    for r in rows:
        res = "PASS" if r["success"] else "FAIL"
        solve = f"{r['solve_sec']:.1f}s" if r["solve_sec"] is not None else "-"
        wall = f"{r['wall_sec']:.1f}s"
        polls = str(r["polls"]) if r["polls"] is not None else "-"
        print(f"{r['label']:<14} {res:<8} {solve:>8} {wall:>8} {polls:>6}  {r['human_norm_sec']:>12}")
    print("=" * 80)

    out = "/tmp/captcha_benchmark.json"
    with open(out, "w") as f:
        json.dump(rows, f, indent=2)
    print(f"\nRaw results -> {out}")

    return 0 if all(r["success"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
