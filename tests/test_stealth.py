"""Unit tests for stealth masking + context cloning + solve body forwarding."""

import requests

from auto_captcha_solver import STEALTH_INIT_SCRIPT, apply_stealth, clone_context
from auto_captcha_solver.providers.captchaai import CaptchaAIProvider
from auto_captcha_solver.providers.nopecha import (
    NopechaProvider,
    _normalize_cookies,
    describe_error,
)
from auto_captcha_solver.solver import CaptchaSolver

# ── Cookie normalization (Playwright shape → NopeCHA shape) ───────────


def test_normalize_cookies_empty():
    assert _normalize_cookies(None) == []
    assert _normalize_cookies([]) == []


def test_normalize_cookies_session_cookie():
    pw = [{"name": "sid", "value": "abc", "domain": "example.com", "path": "/", "expires": -1}]
    out = _normalize_cookies(pw)
    assert len(out) == 1
    c = out[0]
    assert c["name"] == "sid"
    assert c["value"] == "abc"
    assert c["session"] is True
    assert "expirationDate" not in c
    assert c["hostOnly"] is True  # non-dot domain → host-only


def test_normalize_cookies_persistent_cookie():
    pw = [
        {
            "name": "token",
            "value": "xyz",
            "domain": ".example.com",
            "path": "/",
            "expires": 9999999999,
            "httpOnly": True,
            "secure": True,
        }
    ]
    out = _normalize_cookies(pw)
    c = out[0]
    assert c["session"] is False
    assert c["expirationDate"] == 9999999999
    assert c["httpOnly"] is True
    assert c["secure"] is True
    assert c["hostOnly"] is False  # leading-dot domain → not host-only


def test_normalize_cookies_skips_incomplete():
    pw = [{"name": "x"}, {"value": "y", "domain": "d"}]  # both missing required fields
    assert _normalize_cookies(pw) == []


# ── NopeCHA body forwarding (mocked network) ──────────────────────────


class _Captured:
    def __init__(self):
        self.body: dict = {}


def _mock_provider(monkeypatch, captured, *, submit_ok=True):
    """Patch NopechaProvider._api to capture the submit body and return a token."""

    def fake_api(self, path, method="GET", body=None):
        if method == "POST":
            captured.body = body
            return (200, {"data": "job-id-123"}) if submit_ok else (403, {"error": 16})
        # GET poll → return solved token immediately
        return (200, {"data": "SOLVED_TOKEN"})

    monkeypatch.setattr(NopechaProvider, "_api", fake_api)


def test_solve_forwards_useragent_and_cookies(monkeypatch):
    captured = _Captured()
    _mock_provider(monkeypatch, captured)
    solver = CaptchaSolver(api_key="k", poll_interval=0.0, max_polls=2, timeout_sec=5.0)

    result = solver.solve(
        "hcaptcha",
        "sitekey-1",
        "https://example.com",
        useragent="Mozilla/5.0 (Macintosh) TestUA",
        cookies=[{"name": "sid", "value": "v", "domain": "example.com", "path": "/"}],
        data={"rqdata": "rq_abc"},
    )

    assert result.success
    assert result.token == "SOLVED_TOKEN"
    assert captured.body["useragent"] == "Mozilla/5.0 (Macintosh) TestUA"
    # NopeCHA docs: cookie is a native array, data a native object.
    assert isinstance(captured.body["cookie"], list)
    assert captured.body["cookie"][0]["name"] == "sid"
    assert isinstance(captured.body["data"], dict)
    assert captured.body["data"] == {"rqdata": "rq_abc"}
    assert captured.body["sitekey"] == "sitekey-1"


def test_solve_omits_optional_fields_when_absent(monkeypatch):
    captured = _Captured()
    _mock_provider(monkeypatch, captured)
    solver = CaptchaSolver(api_key="k", poll_interval=0.0, max_polls=2, timeout_sec=5.0)

    solver.solve("recaptcha2", "sk", "https://example.com")

    assert "useragent" not in captured.body
    assert "cookie" not in captured.body
    assert "data" not in captured.body
    assert "proxy" not in captured.body


def test_turnstile_without_proxy_fails_fast(monkeypatch):
    """NopeCHA's schema marks proxy REQUIRED for turnstile — we fail fast
    with a clear result instead of warning and submitting a doomed job."""
    captured = _Captured()
    _mock_provider(monkeypatch, captured)
    solver = CaptchaSolver(api_key="k", poll_interval=0.0, max_polls=2, timeout_sec=5.0)

    result = solver.solve("turnstile", "sk", "https://example.com")
    assert not result.success
    assert "requires a proxy" in result.error
    # nothing was submitted to the API
    assert not captured.body


def test_turnstile_with_proxy_proceeds(monkeypatch):
    import warnings

    captured = _Captured()
    _mock_provider(monkeypatch, captured)
    solver = CaptchaSolver(
        api_key="k",
        poll_interval=0.0,
        max_polls=2,
        timeout_sec=5.0,
        proxy={"scheme": "http", "host": "1.2.3.4", "port": 8080},
    )

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        result = solver.solve("turnstile", "sk", "https://example.com")
    assert result.success
    assert not any("proxy" in str(x.message).lower() for x in w)
    assert captured.body["proxy"]["host"] == "1.2.3.4"


# ── Error-code mapping + network resilience ──────────────────────────


def test_describe_error_known_codes():
    assert "Out of credit" in describe_error(16)
    assert "Rate limit" in describe_error(11)
    assert "Invalid key" in describe_error(15)


def test_describe_error_unknown_code():
    assert "error 999" in describe_error(999)


def test_submit_network_failure_is_structured(monkeypatch):
    solver = CaptchaSolver(api_key="k")

    def boom(*a, **k):
        raise requests.exceptions.ConnectionError("refused")

    monkeypatch.setattr("auto_captcha_solver.providers.nopecha.requests.request", boom)
    result = solver.solve("hcaptcha", "sk", "https://example.com")
    assert not result.success
    assert "network" in result.error.lower()
    assert "refused" in result.error


def test_poll_retries_on_transient_network_error(monkeypatch):
    calls = {"n": 0}
    solver = CaptchaSolver(api_key="k", poll_interval=0.0, max_polls=5, timeout_sec=5.0)

    def fake_api(self, path, method="GET", body=None):
        calls["n"] += 1
        if method == "POST":
            return 200, {"data": "job-1"}
        # First poll: network glitch; second poll: solved
        if calls["n"] == 2:
            return 0, {"error": "network", "message": "timeout"}
        return 200, {"data": "SOLVED"}

    monkeypatch.setattr(NopechaProvider, "_api", fake_api)
    result = solver.solve("hcaptcha", "sk", "https://example.com")
    assert result.success
    assert result.token == "SOLVED"


def test_captchaai_network_failure_on_submit(monkeypatch):
    provider = CaptchaAIProvider("k")

    def boom(*a, **k):
        raise requests.exceptions.ConnectionError("refused")

    monkeypatch.setattr("auto_captcha_solver.providers.captchaai.requests.post", boom)
    ok, err = provider._submit({"method": "userrecaptcha"})
    assert not ok
    assert "network" in err


# ── Stealth helpers ───────────────────────────────────────────────────


def test_stealth_script_patches_key_signals():
    for marker in ("navigator.webdriver", "window.chrome", "navigator.plugins", "37445"):
        assert marker in STEALTH_INIT_SCRIPT


def test_apply_stealth_registers_init_script():
    calls = {}

    class DummyContext:
        def add_init_script(self, script=None):
            calls["script"] = script

    apply_stealth(DummyContext())
    assert calls["script"] == STEALTH_INIT_SCRIPT


def test_apply_stealth_rejects_non_context():
    class DummyPage:  # no add_init_script
        pass

    try:
        apply_stealth(DummyPage())
    except AttributeError as e:
        assert "add_init_script" in str(e)
    else:
        raise AssertionError("expected AttributeError")


def test_clone_context_reads_ua_and_cookies():
    class DummyContext:
        def cookies(self, url):
            return [{"name": "a", "value": "b", "domain": "d", "path": "/"}]

    class DummyPage:
        url = "https://example.com"
        context = DummyContext()

        def evaluate(self, script):
            return "Mozilla/5.0 CloneUA"

    snap = clone_context(DummyPage())
    assert snap["useragent"] == "Mozilla/5.0 CloneUA"
    assert snap["cookies"][0]["name"] == "a"


def test_clone_context_survives_errors():
    class DummyPage:
        def evaluate(self, script):
            raise RuntimeError("boom")

    snap = clone_context(DummyPage())
    assert snap["useragent"] is None
    assert snap["cookies"] is None
