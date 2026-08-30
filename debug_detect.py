#!/usr/bin/env python3
"""Reproduce the recaptcha3 false positive on the hCaptcha demo page.
Dumps every <script> src + the exact has_v3 expression, then runs detect()."""
import sys
from playwright.sync_api import sync_playwright

HAS_V3 = """() => {
    if (document.querySelector('.g-recaptcha, .g-recaptcha-response, iframe[src*="recaptcha"]')) return false;
    const scripts = document.querySelectorAll('script[src*="recaptcha"]');
    for (const s of scripts) {
        if (s.src.includes('render=')) return true;
    }
    return false;
}"""

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("https://accounts.hcaptcha.com/demo", timeout=60000, wait_until="domcontentloaded")
    page.wait_for_timeout(4000)

    scripts = page.evaluate(
        """() => Array.from(document.querySelectorAll('script')).map(s => ({
            src: s.src || '(inline)',
            has_render: (s.src || '').includes('render='),
            matches_recaptcha_selector: (s.src || '').includes('recaptcha'),
            text_snippet: s.textContent ? s.textContent.slice(0, 120) : '',
        }))"""
    )
    print("=== all <script> tags ===")
    for s in scripts:
        print(f"  src={s['src']!r} render={s['has_render']} recaptcha-selector={s['matches_recaptcha_selector']}")
        if s["text_snippet"]:
            print(f"    inline-text: {s['text_snippet']!r}")

    print("\n=== has_v3 expression result:", page.evaluate(HAS_V3))

    # frame URLs (method 1 of detect)
    print("\n=== frame urls ===")
    for f in page.frames:
        print(f"  {f.url!r}")

    sys.path.insert(0, "src")
    from auto_captcha_solver import CaptchaSolver

    solver = CaptchaSolver(api_key="x", timeout_sec=5)
    print("\n=== detect() ===")
    for cap in solver.detect(page):
        print(f"  {cap['type']} sitekey={cap['sitekey']!r}")
    browser.close()
