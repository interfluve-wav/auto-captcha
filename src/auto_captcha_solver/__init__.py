"""auto-captcha: Universal captcha solver for Playwright automation."""

from .autopilot import (
    AutoSolveReport,
    auto_solve_page,
    auto_solve_url,
    round_robin_rotator,
    wait_for_captchas,
)
from .solver import CaptchaSolver
from .stealth import STEALTH_INIT_SCRIPT, apply_stealth, clone_context
from .types import CaptchaResult
from .wrapper import SmartPage, smart_page

__version__ = "0.1.6"
__all__ = [
    "CaptchaSolver",
    "CaptchaResult",
    "SmartPage",
    "smart_page",
    "apply_stealth",
    "clone_context",
    "STEALTH_INIT_SCRIPT",
    "AutoSolveReport",
    "auto_solve_page",
    "auto_solve_url",
    "wait_for_captchas",
    "round_robin_rotator",
]
