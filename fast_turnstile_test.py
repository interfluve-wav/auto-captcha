#!/usr/bin/env python3
"""Fast Turnstile solve — pre-fetched sitekey, no browser warmup.

Skips the ~2–3 min Playwright/proxy warmup by using a known sitekey.
NopeCHA still queues (experimental), but we poll fast with 1s interval.
"""
import os
import time
import requests

API_KEY = os.environ["NOPECHA_API_KEY"]
SITEKEY = "3x00000000000000000000FF"  # pre-fetched from 2captcha demo
URL = "https://2captcha.com/demo/cloudflare-turnstile"

# Novada sticky proxy (from .env)
NOVADA_HOST = os.environ["NOVADA_HOST"]
NOVADA_PORT = os.environ["NOVADA_PORT"]
NOVADA_USER = os.environ["NOVADA_USER"]
NOVADA_PASS = os.environ["NOVADA_PASS"]

def solve():
    # Build proxy string for NopeCHA (they expect host:port:user:pass format)
    proxy_str = f"{NOVADA_HOST}:{NOVADA_PORT}:{NOVADA_USER}:{NOVADA_PASS}"
    
    body = {
        "sitekey": SITEKEY,
        "url": URL,
        "proxy": {
            "scheme": "http",
            "host": NOVADA_HOST,
            "port": int(NOVADA_PORT),
            "username": NOVADA_USER,
            "password": NOVADA_PASS,
        },
        "useragent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
    }
    
    print(f"Submitting to NopeCHA (sitekey={SITEKEY[:12]}...)")
    r = requests.post(
        "https://api.nopecha.com/v1/token/turnstile",
        json=body,
        headers={"Content-Type": "application/json", "Authorization": f"Basic {API_KEY}"},
        timeout=30,
    )
    print(f"Submit status: {r.status_code}")
    resp = r.json()
    print(f"Submit response: {resp}")
    
    if resp.get("error"):
        print(f"Error: {resp}")
        return None
    
    job_id = resp["data"]
    print(f"Job ID: {job_id}")
    
    # Poll fast (1s interval, 60s timeout)
    for i in range(60):
        time.sleep(1)
        r = requests.get(
            f"https://api.nopecha.com/v1/token/turnstile?id={job_id}",
            headers={"Authorization": f"Basic {API_KEY}"},
            timeout=30,
        )
        result = r.json()
        if result.get("data"):
            print(f"SOLVED in {i+1}s: {result['data'][:50]}...")
            return result["data"]
        if result.get("error") and result["error"] != 14:  # 14 = incomplete job, keep polling
            print(f"Poll error: {result}")
            return None
        if i % 10 == 0:
            print(f"Polling... {i}s elapsed")
    
    print("Timeout after 60s")
    return None

if __name__ == "__main__":
    token = solve()
    if token:
        print(f"\nToken: {token[:80]}...")
    else:
        print("\nNo token returned")
