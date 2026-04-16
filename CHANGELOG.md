# Changelog

## 0.1.2 (2026-04-16)

- Add: reCAPTCHA v3 Token API support
- Add: Cloudflare Turnstile Token API support
- Add: `solver.supported_types()` — returns ['hcaptcha', 'recaptcha2', 'recaptcha3', 'turnstile']
- Fix: detection no longer false-positives across captcha types
- Fix: reCAPTCHA v3 detection requires `render=` param in script src

## 0.1.1 (2026-04-16)

- Fix: hCaptcha sitekey extraction from iframe URL fragments
- Fix: detect hCaptcha when iframes are cross-origin

## 0.1.0 (2026-04-16)

Initial release.

- CaptchaSolver core class — detect, solve, inject
- SmartPage wrapper with transparent auto-solve
- `smart_page()` context manager
- CLI tool: `auto-captcha {solve,detect,credits}`
- MCP server for AI agent integration
- Hermes skill descriptor
- Supports hCaptcha (checkbox + enterprise) and reCAPTCHA v2
- NopeCHA API integration with polling and timeout
