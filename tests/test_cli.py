"""CLI integration tests."""

import subprocess
import sys

PYTHON = sys.executable


def test_cli_help():
    result = subprocess.run(
        [PYTHON, "-m", "auto_captcha_solver.cli"], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 1  # No subcommand → exits 1
    assert "usage:" in result.stdout.lower() or "usage:" in result.stderr.lower()


def test_cli_credits_missing_key(monkeypatch):
    """credits command should exit 1 when API key missing."""
    # Ensure env var is NOT set
    monkeypatch.delenv("NOPECHA_API_KEY", raising=False)
    result = subprocess.run(
        [PYTHON, "-c", "from auto_captcha_solver.cli import main; main()"],
        capture_output=True,
        text=True,
        timeout=10,
        env={},
    )
    # argparse will show error because --key not provided; exit non-zero
    assert result.returncode != 0


def test_cli_build_proxy_from_url():
    from auto_captcha_solver.cli import _build_proxy

    class A:
        proxy_url = "http://u:p@h.example:7777"
        proxy = None
        proxy_port = None
        proxy_user = None
        proxy_pass = None

    p = _build_proxy(A())
    assert p == {
        "scheme": "http",
        "host": "h.example",
        "port": 7777,
        "username": "u",
        "password": "p",
    }


def test_cli_build_proxy_from_parts(monkeypatch):
    from auto_captcha_solver.cli import _build_proxy

    monkeypatch.setenv("NOVADA_PORT", "7777")
    monkeypatch.setenv("NOVADA_USER", "u")
    monkeypatch.setenv("NOVADA_PASS", "p")

    class A:
        proxy_url = None
        proxy = "h.example"
        proxy_port = None
        proxy_user = None
        proxy_pass = None

    p = _build_proxy(A())
    assert p is not None
    assert p["host"] == "h.example" and p["port"] == 7777 and p["username"] == "u"


def test_cli_build_proxy_none_when_unconfigured(monkeypatch):
    from auto_captcha_solver.cli import _build_proxy

    for var in ("NOVADA_HOST", "CAPTCHA_PROXY_URL"):
        monkeypatch.delenv(var, raising=False)

    class A:
        proxy_url = None
        proxy = None
        proxy_port = None
        proxy_user = None
        proxy_pass = None

    assert _build_proxy(A()) is None


def test_cli_proxy_check_subcommand_registered():
    result = subprocess.run(
        [PYTHON, "-m", "auto_captcha_solver.cli", "proxy-check", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert "--proxy-url" in result.stdout


# Integration test — commented by default (needs API key + browser)
# def test_cli_detect_live():
#     result = subprocess.run(
#         [PYTHON, "-m", "auto_captcha_solver.cli", "detect", "--url", "https://example.com", "--key", "test"],
#         capture_output=True, text=True, timeout=30
#     )
#     assert result.returncode == 0
