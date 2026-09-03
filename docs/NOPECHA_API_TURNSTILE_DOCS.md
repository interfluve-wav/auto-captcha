# NopeCHA API — Turnstile Token Solve: Authoritative Reference

Compiled 2026-08-29 from official NopeCHA documentation and the official client
source. Purpose: fix Cloudflare Turnstile token solves in
`src/auto_captcha_solver/providers/nopecha.py` (was returning error 10
"Invalid request" on submit).

## Primary sources

| Source | URL |
| --- | --- |
| Current v1 API reference (authoritative) | https://nopecha.com/api-reference/ |
| Legacy Token docs (flat `/token/` endpoint) | https://developers.nopecha.com/token/turnstile/ |
| Proxy formatting guide | https://developers.nopecha.com/formatting/proxy/ |
| Cookie formatting guide | https://developers.nopecha.com/formatting/cookie/ |
| Welcome page: pricing, credit usage, speed table | https://developers.nopecha.com/ |
| Token quickstart | https://developers.nopecha.com/guides/token/ |
| Pricing / plans | https://nopecha.com/pricing |
| Official Python client source | https://github.com/NopeCHALLC/nopecha-python (`src/nopecha/api/_base.py`, `types.py`) |
| Official example scripts | https://github.com/NopeCHALLC/nopecha-scripts |
| Error-10 real-world issue | https://github.com/NopeCHALLC/nopecha-extension/issues/109 |

---

## 1. Turnstile token endpoint (submit + poll)

**Submit** — `POST https://api.nopecha.com/v1/token/turnstile`
Source: https://nopecha.com/api-reference/#postTurnstileToken

Auth: header `Authorization: Basic <API_KEY>` (raw key as Basic username) **or**
`key` query parameter. Request body (field → required?):

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `sitekey` | string | **yes** | Public Turnstile sitekey |
| `url` | string | **yes** | URL of the page containing the Turnstile |
| `proxy` | object | **yes (turnstile only)** | see §2 |
| `cookie` | array of objects | no | see §7 |
| `useragent` | string | no | "User-Agent to use when solving the CAPTCHA" (field name is `useragent`) |
| `data` | object | no | `action` (data-action attr), `cdata` (cdata metadata) |

**Verbatim example body from the docs** (curl/Python/JS examples all identical):

```json
{
  "sitekey": "0x4AAAAAAABBBBCCCCDDDDEEEEFFFGGGHH",
  "url": "https://example.com/login",
  "proxy": {
    "scheme": "http",
    "host": "proxy.example.com",
    "port": 8080,
    "username": "proxyuser",
    "password": "proxypass"
  },
  "data": {
    "action": "login",
    "cdata": "customer-metadata"
  }
}
```

Response 200:

```json
{
  "data": "2xuttwekei7birwsfhh3lr97oqovzm0r9u23yz03uhr2u560l2rocrmanb7etf9k"
}
```

(`data` is the **job id**.)

**Poll** — `GET https://api.nopecha.com/v1/token/turnstile?id=<JOB_ID>`
Source: https://nopecha.com/api-reference/#getTurnstileToken

While incomplete → `{"error": 14, "message": "Incomplete job"}` (retry; docs
recommend 500 ms wait). When solved →

```json
{
  "data": "0.zLH9XGqT34J7GO1PEPKgHeYwO38CvXgGVZ6tVfl9eyZg5GvV7mTZGbBl"
}
```

### Legacy v0 endpoint (for reference / older docs)
Source: https://developers.nopecha.com/token/turnstile/ and the official Python
client (`APIClient.solve_raw` posts to `https://api.nopecha.com/token/`).
The flat endpoint requires a `type` field in the body:

```json
{
    "key": "MY_NOPECHA_KEY",
    "type": "turnstile",
    "sitekey": "0x4AAAAAAAA-1LUipBaoBpsG",
    "url": "https://nopecha.com/demo/turnstile"
}
```

Poll: `GET https://api.nopecha.com/token/?key=MY_NOPECHA_KEY&id=0n8mly8iy4R0aD0`.
A bad/missing `type` here returns error 10 with `type: "Invalid type"` (see
https://github.com/NopeCHALLC/nopecha-extension/issues/109). Our provider uses
the per-endpoint v1 API, which has **no** `type` field in the body.

## 2. Proxy object format (exact)

Sources: https://nopecha.com/api-reference/ (turnstile section) and
https://developers.nopecha.com/formatting/proxy/

`proxy` is an **object**, never a plain string:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `scheme` | string | yes | `"http"` \| `"https"` \| `"socks4"` \| `"socks5"` |
| `host` | string | yes | Proxy host or IP address (IPv4/IPv6) — no scheme prefix, no port |
| `port` | integer **or string** | yes | Port number |
| `username` | string | no | "Currently only supported for `http` and `https` proxy schemes" |
| `password` | string | no | "Currently only supported for `http` and `https` proxy schemes" |

Verbatim constraint from the docs:
> "Proxy authentication is not supported for `socks4` and `socks5`, and the
> `username` and `password` fields will be ignored for these schemes."

And from the proxy guide: "We currently do not support proxy authentication by
IP origin."

Verbatim example (proxy guide, hcaptcha but identical shape):

```javascript
'proxy': {
    'scheme': 'http',
    'host': '1.1.1.1',
    'port': '8000',
    'username': 'nopechauser',
    'password': 'hunter7'
}
```

**Residential proxies:** use `scheme: "http"` (or `https`) with the provider's
username/password. To pin one IP across solve + submit, embed a sticky session
id in the username (pattern documented in our own README, e.g. Novada's
`USERNAME-zone-res-session-job42` on `super.novada.pro:7777`), and send the
**same** proxy to NopeCHA and to the browser submitting the token.

Note: the official Python client's `types.py` `Proxy` TypedDict is stale
(`{type, host, port, login, password}`); every current NopeCHA doc example
uses `scheme`/`username`/`password`. Use the documented field names.

## 3. Error code table (complete)

Source: https://nopecha.com/api-reference/ (error section), cross-checked with
`ErrorCode` in https://github.com/NopeCHALLC/nopecha-python (`types.py`).

| App code | HTTP | Default message | Meaning |
| --- | --- | --- | --- |
| 9 | 500 | "Unknown error" | Internal server error — check request and retry |
| 10 | 400 | "Invalid request" | Request body/query invalid; `type` field describes the nature of the error |
| 11 | 429 | "Rate limit reached" | Per-endpoint rate limit hit for this API key; slow down |
| 12 | 403 | "Banned IP" | "Free Tier Ineligible" — IP ineligible for Free plan; use trusted IP or paid plan |
| 13 | — | (no message documented) | `NoJob` in the Python client's `ErrorCode` enum; not on the reference page |
| 14 | 409 | "Incomplete job" | Job not done yet; recommended wait before retrying is **500 ms** |
| 15 | 401 | "Invalid key" | API key invalid |
| 16 | 403 | "Out of credit" | Key has run out of credit |
| 17 | 400 | "Update required" | Reserved, never used |
| 18 | 402 | "Feature unavailable for current plan" | Feature not on current plan; upgrade required |

Every error body has the shape:

```json
{
  "message": "Invalid request",
  "code": 10,
  "type": "string or null"
}
```

(Note: the client-side library maps `error` → `code`; e.g. the legacy examples
show `{"error": 14, "message": "Incomplete job"}`.)

### What triggers 10 "Invalid request" on turnstile submit

Docs: "Request is invalid. Check the request body and query parameters for
errors. **If the `type` field is present in this error response, it will
describe the nature of the error.**"

So the response carries a diagnostic `type` string — e.g. the real-world case
in https://github.com/NopeCHALLC/nopecha-extension/issues/109:

```json
{
    "error": 10,
    "message": "Invalid request",
    "type": "Invalid type"
}
```

That was the legacy flat endpoint rejecting an invalid `type` value. On
`/v1/token/turnstile` the same mechanism means: **log `type` from the error
body to see exactly what failed.** Likely concrete triggers on our submit:

1. `proxy` missing or malformed — it is **Required** for turnstile; a string
   proxy, or wrong field names (`type`/`login` vs `scheme`/`username`), or
   missing `host`/`port`, all make the body invalid.
2. Missing/blank `sitekey` or `url`.
3. `port` as a non-numeric string.
4. Unknown/extra top-level fields (e.g. sending `type` to a v1 per-endpoint).

**Action:** our provider currently drops `type` — capture it in
`describe_error`/error strings.

## 4. Is a proxy REQUIRED for turnstile?

**Yes.** Source: https://nopecha.com/api-reference/#postTurnstileToken — the
`proxy` field is marked **Required** in the request schema, with:

> "In most cases, the IP address of the Turnstile solver must match that of
> the client submitting it, otherwise the token will be invalidated by
> Cloudflare and the IP addresses involved will be soft-blocked. As such, a
> proxy is required for Turnstile token jobs. To avoid issues, ensure that the
> same proxy is used when submitting the token."

(Older page https://developers.nopecha.com/token/turnstile/ is softer: "we
suggest providing the proxy parameter … some sites will check that the IP used
to solve the challenge matches the IP used to submit the token." The current v1
schema is authoritative: required.)

### Turnstile-specific caveats / timing

- Our repo README marks Turnstile "⚠️ Experimental — NopeCHA queue may be
  slow": "Experimental types work through NopeCHA's queue system (5–10 minute
  wait, requires proxy in production)."
  (https://github.com/interfluve-wav/auto-captcha-solver — repo README; the
  5–10 min wait is observed queue behavior, not a figure published by NopeCHA.)
- Official cost/speed table (Jan 2025, enterprise quarterly): Turnstile token
  **5 s** nominal speed.
  (https://developers.nopecha.com/#cost-and-speed-breakdown)
- Token API in general: "May be detected on some sites"
  (https://developers.nopecha.com/guides/token/)
- Practical: poll with a 5–10+ minute budget; our default 25 polls × 4 s =
  100 s is too short for turnstile.

## 5. Request-shape differences: hcaptcha / recaptcha2 / recaptcha3 / turnstile

Source: https://nopecha.com/api-reference/ (all four token sections)

Common to all v1 token endpoints: `key` (optional), `sitekey` (required),
`url` (required), `proxy` (optional object — **except turnstile: required**),
`cookie` (optional array), `useragent` (optional), `data` (optional object).

| Type | Endpoint | `data` fields | Other |
| --- | --- | --- | --- |
| hcaptcha | `/v1/token/hcaptcha` | `rqdata` | proxy optional |
| recaptcha2 | `/v1/token/recaptcha2` | `theme` ("light"/"dark"), `s` | top-level `enterprise` (bool, optional); proxy optional |
| recaptcha3 | `/v1/token/recaptcha3` | `action`, `theme`, `s` | top-level `enterprise` (bool, optional); proxy optional |
| turnstile | `/v1/token/turnstile` | `action`, `cdata` | **no** `enterprise` field; **proxy required** |

Verbatim recaptcha2 example body:

```json
{
  "sitekey": "6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI",
  "url": "https://example.com/login",
  "data": {
    "theme": "dark",
    "s": "DATA_S_VALUE"
  },
  "enterprise": false
}
```

Verbatim recaptcha3 example body:

```json
{
  "sitekey": "6Lc_aX0UAAAAAB1c2DEFghiJKLmNoPQRStuVwxYz",
  "url": "https://example.com/login",
  "data": {
    "action": "login",
    "theme": "light",
    "s": "DATA_S_VALUE"
  },
  "enterprise": true
}
```

Verbatim hcaptcha example body:

```json
{
  "sitekey": "58366d97-3e8c-4b57-a679-4a41c8423be3",
  "url": "https://nopecha.com/captcha/hcaptcha",
  "data": {
    "rqdata": "rq_1vwJRRRVSkhKVE1DQ29CRU1qdldDRFB6enE2..."
  }
}
```

The official Python client's turnstile body additionally supports
`data.chlPageData` (not in the api-reference page):
https://raw.githubusercontent.com/NopeCHALLC/nopecha-python/main/src/nopecha/api/_base.py

```python
body: TurnstileTokenRequest = {
    "type": "turnstile",
    "sitekey": sitekey,
    "url": url,
    "proxy": proxy,
    "useragent": useragent,
    "data": {
        "action": action,
        "cdata": cdata,
        "chlPageData": challenge_page_data,
    },
}
```

The client also sends `Authorization: Bearer <key>` (vs `Basic` in the v1
reference examples) and injects `key` into the body + query for the legacy
`/token/` route. Both header styles are seen in official sources; the v1
reference examples use `Basic`.

## 6. Rate limits and credit pricing

### Rate limits
No numeric per-endpoint limits are published.
Source: https://nopecha.com/api-reference/#429_RateLimited

- Code 11 / HTTP 429: "Rate limit for this endpoint has been reached for the
  API key. Slow down the request rate to avoid this error."
- The plan "determines … the rate at which you can request our API"
  (https://developers.nopecha.com/#credit-system-for-subscriptions) with
  concurrent-connection caps: Starter 2+, Basic 8+, Professional 16+,
  Enterprise 64+ (https://nopecha.com/pricing).
- The official Python client backs off on 429/5xx: exponential throttle for
  POST (max 10 attempts), linear throttle for GET polling (max 120 attempts).
  (https://raw.githubusercontent.com/NopeCHALLC/nopecha-python/main/src/nopecha/api/_base.py)

### Credit usage per captcha type
Source: https://developers.nopecha.com/#credit-usage-by-captcha

| Job | Credits |
| --- | --- |
| Turnstile **token** | 1 |
| hCaptcha **token** | 10 |
| reCAPTCHA v2 **token** | 20 |
| reCAPTCHA v3 **token** | 20 |
| All recognition jobs (hcaptcha, recaptcha, funcaptcha, geetest, lemin, text, awscaptcha) | 1 each |

"All free and paid credits are received every 23 hours."

### Plans
Source: https://nopecha.com/pricing

| Plan | Solves/day | Monthly | Quarterly |
| --- | --- | --- | --- |
| Starter | 2,000 | $4.99 | $9.99 |
| Basic | 20,000 | $19.99 | $39.99 |
| Professional | 80,000 | $49.99 | $99.99 |
| Enterprise | 200,000 | $99.99 | $199.99 |

Cost/speed table (Jan 2025, quarterly enterprise plan),
https://developers.nopecha.com/#cost-and-speed-breakdown:
Turnstile token 90,000/$1 @ 5 s; reCAPTCHA token 4,500/$1 @ 60 s;
hCaptcha token 18,000/$1 @ 15 s.

Free tier: 100 solves/day, "excluding non-residential IP addresses"
(https://developers.nopecha.com/#is-it-free).

## 7. Cookie object format (reference)

Source: https://developers.nopecha.com/formatting/cookie/

`cookie` is an **array** of objects; required keys per cookie: `name`,
`value`, `domain`, `path`, `hostOnly` (bool), `httpOnly` (bool), `secure`
(bool), `session` (bool); optional `expirationDate` (unix seconds; omit for
session cookies). Our `_normalize_cookies()` already matches this.

Verbatim example:

```javascript
'cookie': [
    {
        'name': 'nopechacookie0',
        'value': 'hello world!',
        'domain': 'nopecha.com',
        'path': '/demo/hcaptcha',
        'hostOnly': true,
        'httpOnly': true,
        'secure': true,
        'session': false,
        'expirationDate': 1670023021
    }
]
```

## 8. Diagnosis: why we got error 10 on turnstile submit

Given the docs, the submit body our provider builds
(`{sitekey, url, proxy?, useragent?, cookie?, data?}`) matches the v1 schema
in shape. The prime suspects, in order:

1. **`proxy` was not sent** (it is optional in our `solve()` and defaults to
   `None`) → missing a **required** field on the turnstile endpoint → 400
   "Invalid request". The v1 reference is explicit that a proxy is required
   for turnstile.
2. **Proxy dict shape** — a string proxy, `type`/`login` keys (stale client
   shape), or missing `host`/`port` → invalid object → 400.
3. **`type` field in the response is dropped** by our error handling, so we
   can't see NopeCHA's own diagnosis (e.g. `type: "Invalid type"` /
   `type: "Invalid proxy"`).
4. Account-side (would surface as 12/16/18, not 10, but rule out first):
   banned IP, out of credit, feature not on plan.

## 9. Concrete fixes for `src/auto_captcha_solver/providers/nopecha.py`

1. Force a full proxy object for turnstile: `{scheme, host, port, username,
   password}` with `port` as int and `host` a bare IP/hostname. Refuse to
   submit turnstile without it (or make the caller pass it explicitly).
2. Only `http`/`https` schemes carry credentials — warn if `username`/
   `password` are set with `socks4`/`socks5` (NopeCHA silently ignores them).
   For residential proxies, use `http` + session-pinned username.
3. Capture and include the error body's `type` field in reported errors.
4. Give turnstile a long poll budget (≥5–10 min; e.g. 60 polls × 5 s or
   timeout_sec ≥ 600) while keeping error 14 → continue semantics.
5. Do not add a `type` field to v1 per-endpoint bodies; send only documented
   fields (turnstile: sitekey, url, proxy, cookie, useragent,
   data{action, cdata}).
6. Ensure the same sticky residential proxy is used by the solving side and
   the submitting side (IP match), per the docs' IP-match warning.
