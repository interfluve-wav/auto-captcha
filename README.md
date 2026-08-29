# auto-captcha — Universal Captcha Solver for Playwright

![Python](https://img.shields.io/pypi/pyversions/auto-captcha)
![PyPI version](https://img.shields.io/pypi/v/auto-captcha)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-blue)
![Hermes Skill](https://img.shields.io/badge/Hermes-Skill-gold)

Drop-in captcha bypass for Playwright browser automation. Detects hCaptcha, reCAPTCHA v2/v3, and Cloudflare Turnstile, solves them via the NopeCHA Token API, and injects tokens automatically — so your automation scripts never stall.

```
Your script → page loads → captcha detected → NopeCHA API → token injected → continue
```

## Quick Start

```bash
pip install auto-captcha
python -m playwright install chromium
```

```python
from auto_captcha_solver import smart_page

with smart_page(api_key="your-nopecha-key") as page:
    page.goto("https://protected-site.com")
    page.fill("#email", "user@example.com")
    page.click("#submit")  # captcha auto-solved → form submits
```

## Why This Exists

Browser automation hits captcha walls. Existing solutions either require manual intervention or brittle image-to-text heuristics. **auto-captcha** uses a commercial token API (NopeCHA) that actually solves the challenge server-side — it's the same API powering many production captcha-bypass automation tools.

**Features:**
- **Automatic detection** — scans frames and DOM for hCaptcha, reCAPTCHA v2/v3, Turnstile
- **Zero-config wrapper** — `smart_page()` context manager handles everything
- **Fine-grained control** — `CaptchaSolver` class exposes detect/solve/inject separately
- **MCP server included** — use from Claude Code, Cursor, or any MCP-compatible agent
- **CLI tool** — solve or detect from the command line
- **Playwright CLI compatibility** — works alongside `playwright-cli` workflows

> **Note:** Requires a NopeCHA API key (free tier available). See https://nopecha.com

## Installation

### Core Package

```bash
pip install auto-captcha
```

### With Playwright (recommended)

```bash
pip install auto-captcha[playwright]
python -m playwright install chromium
```

Or install separately:

```bash
pip install playwright
python -m playwright install
```

## Three Ways to Use

### 1. `smart_page()` — Context Manager (easiest)

Manages browser lifecycle and auto-solves on navigation/click events.

```python
from auto_captcha_solver import smart_page

with smart_page(api_key="your-key") as page:
    page.goto("https://example.com")
    page.fill("#email", "user@test.com")
    page.click("#submit")  # auto-solved
    print(page.captcha_log)  # [{'type': 'hcaptcha', 'status': 'solved'}]
```

**Options:**
- `headless=False` — see the browser
- `wait_after_load=3.0` — delay before solving (site-dependent)

### 2. `SmartPage` — Wrap an Existing Page

Use when you already have a Playwright page/browser instance:

```python
from auto_captcha_solver import SmartPage
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
browser = pw.chromium.launch(headless=True)
raw_page = browser.new_page()
page = SmartPage(raw_page, api_key="your-key")

page.goto("https://site.com")  # captchas auto-solved
page.fill("#input", "value")
page.click("#submit")
browser.close()
pw.stop()
```

### 3. `CaptchaSolver` — Full Control

Detect, solve, and inject manually:

```python
from auto_captcha_solver import CaptchaSolver

solver = CaptchaSolver(api_key="your-key")

# Detect all captchas on the page
captchas = solver.detect(page)
# → [{'type': 'hcaptcha', 'sitekey': 'abc123', 'url': 'https://...'}]

# Solve one
result = solver.solve(captcha_type="hcaptcha", sitekey="abc123", url=page.url)
if result.success:
    # Inject into page
    solver.inject(page, "hcaptcha", result.token)
```

## Stealth & Context Cloning

Token solves are minted server-side by the provider, so the token's *context*
(IP, User-Agent, cookies) must match the browser that presents it — otherwise
anti-bot systems (especially Cloudflare Turnstile) invalidate it on submit.

**`apply_stealth(context)`** masks the in-page fingerprint leaks a vanilla
headless Chromium exposes (`navigator.webdriver`, missing `window.chrome`,
empty `navigator.plugins`, SwiftShader WebGL vendor). Call it once on the
`BrowserContext`, before creating pages:

```python
from auto_captcha_solver import CaptchaSolver, apply_stealth
with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context()   # or use your real profile
    apply_stealth(context)            # mask fingerprint
    page = context.new_page()
    solver = CaptchaSolver(api_key="your-key")
    results = solver.auto_solve(page) # UA + cookies cloned automatically
```

**`clone_context(page)`** snapshots the browser's real User-Agent and cookies so
you can forward them to `solve()`:

```python
from auto_captcha_solver import clone_context
ctx = clone_context(page)  # {"useragent": str|None, "cookies": list|None}
result = solver.solve("hcaptcha", sitekey, page.url, **ctx)
```

- `auto_solve(..., clone_context=True)` (default) forwards the live UA + cookies
  and reads `data-action`/`data-cdata` off the widget for reCAPTCHA v3 /
  Turnstile metadata.
- **Turnstile requires a proxy** whose IP matches the client's — `solve()`
  emits a warning if you call it without `proxy=...`.
- The `Runtime.enable` CDP leak (below the JS layer) is closed only by driving
  the browser with [Patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright-python)
  — a drop-in Playwright fork. `apply_stealth` stacks cleanly on top of it.

## Turnkey Auto-Solve (Autopilot)

`auto_solve_*` helpers wrap the full detect → solve → inject pipeline into a
single call. They wait for captchas that render late, clone the browser context,
and support proxy rotation.

```python
from auto_captcha_solver import auto_solve_url

report = auto_solve_url(
    "https://some-login-form.com",
    api_key="your-key",
    stealth=True,          # mask headless fingerprint
    proxy={"scheme": "http", "host": "your-residential-ip", "port": 7777},
)
print(report.summary)   # "https://... — hcaptcha:OK"
print(report.solved)    # True
```

**Rotating proxies** (e.g. Novada) — pass a pool; one proxy is picked per session
and used for BOTH browser egress and the solve request, so the token IP always
matches the browser IP (required for token validity):

```python
from auto_captcha_solver import auto_solve_url, round_robin_rotator

proxies = [
    {"scheme": "http", "host": "p1.novada.example", "port": 7777, "username": "u", "password": "p"},
    {"scheme": "http", "host": "p2.novada.example", "port": 7777, "username": "u", "password": "p"},
]
report = auto_solve_url("https://site.com", api_key="k", proxy_pool=proxies)
```

**Remote / hosted browsers** (Browserless, Steel, or any CDP endpoint) — pass
`cdp_url` to drive an existing browser instead of launching one. The function
opens a fresh context on the remote browser, solves, and closes that context
without killing the remote session:

```python
from auto_captcha_solver import auto_solve_url

report = auto_solve_url(
    "https://site.com",
    api_key="your-key",
    cdp_url="https://<token>.browserless.io?token=***",   # or wss:// Steel endpoint
    # connect_kwargs={"headers": {"Authorization": "Bearer <token>"}},  # if needed
    # proxy={"scheme": "http", "host": "remote-egress-ip", "port": 7777},
    #   ↑ forward the remote browser's egress IP to the solver — the token's IP
    #     must match the client IP or Turnstile/reCAPTCHA v3 will invalidate it.
)
```

In CDP mode the browser's egress is fixed by the host (you can't re-route it),
so match it with `proxy` for the solve request. Local mode does this
automatically: `proxy` drives both the launched browser and the solver.

Wire it into a page you already own with `auto_solve_page(page, solver)` — it
polls for late-rendering widgets (safer than waiting for `networkidle`, which
Turnstile pages never reach) and solves every challenge on it.

## CLI Usage

```bash
# Check credits
auto-captcha credits --key $NOPECHA_API_KEY

# Detect only (don't solve)
auto-captcha detect --url https://example.com

# Auto-solve
auto-captcha solve --url https://example.com --key $NOPECHA_API_KEY

# Drive a remote/hosted browser over CDP (Browserless / Steel)
auto-captcha solve --url https://example.com --cdp-url "https://<token>.browserless.io?token=***"
auto-captcha detect --url https://example.com --cdp-url "wss://steel-endpoint" --cdp-header "Authorization: Bearer <token>"
```

Results are printed as formatted JSON.

## MCP Server

Exposes captcha solving as MCP tools for AI agents (Claude Code, Cursor, etc.):

```bash
# Set env var
export NOPECHA_API_KEY="your-key"

# Run as MCP server
python -m auto_captcha_solver.mcp_server
```

Then register in your client config:

```json
{
  "mcpServers": {
    "auto-captcha": {
      "command": "python",
      "args": ["-m", "auto_captcha_solver.mcp_server"],
      "env": {"NOPECHA_API_KEY": "your-key"}
    }
  }
}
```

**Available tools:**
- `captcha_detect` — scan a URL for captchas
- `captcha_solve` — detect and solve
- `captcha_credits` — check API credit balance

## Architecture

```
┌──────────────────┐
│  Your script     │
│  (Playwright)    │
└────────┬─────────┘
         │ calls page.goto() / click()
         ▼
┌──────────────────┐
│   SmartPage      │  ← Detects navigation/click events
│   (wrapper)      │  → Waits → Calls detect() after each action
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  CaptchaSolver   │  ← DOM + frame inspection
│  - detect()      │  → extracts sitekeys
│  - solve()       │  → calls NopeCHA API
│  - inject()      │  → posts token into page callbacks
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  NopeCHA API     │  ← Cloud solver (5–60s)
│  token endpoint  │
└──────────────────┘
```

## Supported Captcha Types

| Type | Status | Notes |
|------|--------|-------|
| hCaptcha | ✅ Stable | checkbox + invisible |
| reCAPTCHA v2 | ✅ Stable | checkbox |
| reCAPTCHA v3 | ✅ Stable | score-based, invisible |
| Cloudflare Turnstile | ⚠️ Experimental | NopeCHA queue may be slow |

Experimental types work through NopeCHA's queue system (5–10 minute wait, requires proxy in production).

## Performance

- **Detection**: < 100ms (DOM scan)
- **Solving time**: 5–60 seconds (API-dependent)
- **API credits**: ~1–5 credits per solve (varies by captcha type & NopeCHA plan)

## Production: Proxies & Sticky Sessions

Solving captchas is only one part of stable long-term scraping. Modern sites cross-validate **IP identity**, **persistent cookies**, and **request behavior** as a single risk signal. Even when every challenge is solved successfully, an unstable request pipeline will keep triggering anti-bot restrictions.

For crawlers that run for hours or days, pair this library with **residential proxies that support sticky sessions**:

- **Rotate between sessions** — assign each browser context or worker its own proxy endpoint so traffic is spread across IPs.
- **Keep the same IP within a session** — after a captcha is solved, all follow-up requests (navigation, XHR, cookies) must leave from the same IP that earned the token.
- **Match proxy on both sides** — configure the same sticky proxy for Playwright *and* for the NopeCHA solve request so the token and subsequent page loads share one identity.

```python
from playwright.sync_api import sync_playwright
from auto_captcha_solver import CaptchaSolver

# Same sticky residential proxy for browser traffic and token API
proxy = {
    "scheme": "http",
    "host": "gate.provider.com",
    "port": 7777,
    "username": "user-session-abc123",  # session id pins the IP
    "password": "secret",
}

playwright_proxy = {
    "server": f"http://{proxy['host']}:{proxy['port']}",
    "username": proxy["username"],
    "password": proxy["password"],
}

solver = CaptchaSolver(api_key="your-key", proxy=proxy)

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=False, proxy=playwright_proxy)
    page = browser.new_page()
    page.goto("https://cloudflare-heavy-site.com")
    solver.auto_solve(page)  # token solved from the same IP as the browser
```

**Practical tips:**

- One sticky session per browser context — do not rotate mid-crawl after a solve.
- Reuse cookies/storage for the lifetime of that session; discard the context when you rotate IPs.
- For Cloudflare-heavy targets (e.g. SERP crawling), residential sticky proxies noticeably reduce repeat challenges compared to captcha solving alone.

> Residential providers with session pinning work well with this pattern. For example, [Novada](https://developer.novada.com/novada/proxies/rotating-residential-proxy/session-type) pins an IP by appending `session-{id}` to the proxy username (e.g. `USERNAME-zone-res-session-job42:PASSWORD` on `super.novada.pro:7777`). Any provider that supports sticky sessions and HTTP proxy auth is fine — the key is keeping browser and solver traffic on the same IP.

## Configuration

`CaptchaSolver` constructor arguments:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `api_key` | **required** | NopeCHA API key |
| `poll_interval` | `4.0` | Seconds between solve status polls |
| `max_polls` | `25` | Maximum polling attempts |
| `timeout_sec` | `120.0` | Overall timeout before giving up |
| `proxy` | `None` | Optional proxy dict for NopeCHA requests |

## License

MIT — see [LICENSE](LICENSE) for details.

## Credits

- Built by [Suhaas Chitturi](https://github.com/interfluve-wav)
- API powered by [NopeCHA](https://nopecha.com)
- Diagram assets: Mermaid / Excalidraw
