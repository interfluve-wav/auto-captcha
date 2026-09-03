#!/usr/bin/env python3
"""Live CDP proof: launch a real headless Chrome with remote debugging, then
drive it through auto_solve_url(cdp_url=...) — proves the new CDP path works
against a real browser, not just unit fakes.

Usage: .venv/bin/python cdp_live_check.py
Exits 0 if CDP connect + goto + report all succeed.
"""
import glob
import os
import signal
import subprocess
import sys
import time
import urllib.request

PORT = 19222
PROFILE = "/tmp/cdp-test-profile"


def find_chrome() -> str:
    candidates = glob.glob(
        os.path.expanduser("~/Library/Caches/ms-playwright/chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium")
    )
    if candidates:
        return candidates[0]
    mac = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if os.path.exists(mac):
        return mac
    sys.exit("No Chrome/Chromium found")


def wait_cdp(timeout=20) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def main() -> int:
    chrome = find_chrome()
    print(f"chrome: {chrome}")
    proc = subprocess.Popen(
        [
            chrome,
            "--headless=new",
            f"--remote-debugging-port={PORT}",
            f"--user-data-dir={PROFILE}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-gpu",
            "--window-size=1280,900",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        if not wait_cdp():
            print("FAIL: CDP endpoint never came up")
            return 1
        print(f"CDP up: http://127.0.0.1:{PORT}")
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=3) as r:
            ver = r.read().decode()[:120]
        print(f"browser: {ver}")

        from auto_captcha_solver import auto_solve_url

        report = auto_solve_url(
            "https://example.com",
            api_key="dummy-not-used-no-captcha-here",
            cdp_url=f"http://127.0.0.1:{PORT}",
            max_wait_sec=3.0,
            humanize=False,
            stealth=True,
            screenshot_path="/tmp/cdp_check.png",
        )
        print(f"browser_mode: {report.browser_mode}")
        print(f"summary: {report.summary}")
        print(f"page_title: {report.page_title!r}")
        print(f"elapsed: {report.elapsed_sec:.1f}s")
        print(f"screenshot: {os.path.exists('/tmp/cdp_check.png')}")
        ok = report.browser_mode == "cdp" and report.page_title
        print("CDP LIVE CHECK:", "PASS" if ok else "FAIL")
        return 0 if ok else 1
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        print(f"chrome stopped (was pid {proc.pid})")


if __name__ == "__main__":
    sys.exit(main())
