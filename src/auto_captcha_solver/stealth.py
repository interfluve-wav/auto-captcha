"""Fingerprint masking + browser context-cloning helpers.

These are the "look human" building blocks that complement the token solve:

- :func:`apply_stealth` injects an init script that patches the in-page leaks a
  vanilla headless Chromium exposes (``navigator.webdriver``, missing
  ``window.chrome``, empty ``navigator.plugins``, odd ``navigator.languages``,
  the SwiftShader WebGL vendor string). It works on a Playwright *context* so
  every page/frame inherits it.

- :func:`clone_context` reads the live browser's real User-Agent and cookies so
  the same identity can be forwarded to the solve provider, keeping the token's
  mint context aligned with the browser that presents it.

Note on the ``Runtime.enable`` CDP leak: that fires below the JavaScript layer
and cannot be closed from an init script. If you need it closed, drive the
browser with `patchright <https://github.com/Kaliiiiiiiiii-Vinyzu/patchright-python>`_
(a drop-in Playwright fork) — ``apply_stealth`` stacks cleanly on top of it.
"""

from __future__ import annotations

from typing import Any

__all__ = ["apply_stealth", "clone_context", "STEALTH_INIT_SCRIPT"]


# Patches the in-page signals a vanilla headless Chromium leaks. Kept as one
# self-contained script so it can be registered via add_init_script (runs before
# any page script on every navigation and in every frame).
STEALTH_INIT_SCRIPT = r"""
(() => {
  // 1. navigator.webdriver -> undefined (not just false)
  try {
    Object.defineProperty(Navigator.prototype, 'webdriver', {
      get: () => undefined,
      configurable: true,
    });
  } catch (e) {}

  // 2. window.chrome shim (absent in headless)
  try {
    if (!window.chrome) {
      window.chrome = { runtime: {}, app: { isInstalled: false } };
    }
  } catch (e) {}

  // 3. navigator.plugins / mimeTypes non-empty (headless reports 0)
  try {
    if (navigator.plugins.length === 0) {
      const fake = [
        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
        { name: 'Native Client', filename: 'internal-nacl-plugin' },
      ];
      Object.defineProperty(navigator, 'plugins', {
        get: () => fake,
        configurable: true,
      });
    }
  } catch (e) {}

  // 4. navigator.languages sane default (headless can report [])
  try {
    if (!navigator.languages || navigator.languages.length === 0) {
      Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en'],
        configurable: true,
      });
    }
  } catch (e) {}

  // 5. WebGL vendor/renderer spoof (SwiftShader gives away headless)
  try {
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function (p) {
      // UNMASKED_VENDOR_WEBGL
      if (p === 37445) return 'Intel Inc.';
      // UNMASKED_RENDERER_WEBGL
      if (p === 37446) return 'Intel Iris OpenGL Engine';
      return getParameter.call(this, p);
    };
    if (typeof WebGL2RenderingContext !== 'undefined') {
      const getParameter2 = WebGL2RenderingContext.prototype.getParameter;
      WebGL2RenderingContext.prototype.getParameter = function (p) {
        if (p === 37445) return 'Intel Inc.';
        if (p === 37446) return 'Intel Iris OpenGL Engine';
        return getParameter2.call(this, p);
      };
    }
  } catch (e) {}

  // 6. permissions query for 'notifications' should mirror real Chrome
  try {
    const orig = window.navigator.permissions && window.navigator.permissions.query;
    if (orig) {
      window.navigator.permissions.query = (params) =>
        params && params.name === 'notifications'
          ? Promise.resolve({ state: Notification.permission })
          : orig(params);
    }
  } catch (e) {}
})();
"""


def apply_stealth(context: Any) -> None:
    """Register the fingerprint-masking init script on a Playwright context.

    Call once, right after ``browser.new_context(...)`` and before creating
    pages. Every page and sub-frame in the context inherits the patches on each
    navigation.

    Args:
        context: A Playwright ``BrowserContext`` (sync or async). For async, the
            returned coroutine from ``add_init_script`` is awaited internally by
            Playwright's sync bridge; if you use the async API, call
            ``await context.add_init_script(STEALTH_INIT_SCRIPT)`` yourself.

    Raises:
        AttributeError: if ``context`` has no ``add_init_script`` method.
    """
    add = getattr(context, "add_init_script", None)
    if add is None:
        raise AttributeError(
            "apply_stealth expects a Playwright BrowserContext with "
            "add_init_script(); got a "
            f"{type(context).__name__}. Pass browser.new_context(), not a page."
        )
    add(script=STEALTH_INIT_SCRIPT)


def clone_context(page: Any) -> dict[str, Any]:
    """Snapshot the live browser identity to forward to a solve provider.

    Returns a dict with ``useragent`` (str | None) and ``cookies`` (list | None)
    read from the page and its browser context, suitable to splat into
    :meth:`CaptchaSolver.solve` or to inspect directly.

    Args:
        page: A Playwright ``Page``.

    Returns:
        ``{"useragent": <str|None>, "cookies": <list[dict]|None>}``.
    """
    useragent: str | None = None
    cookies: list[dict[str, Any]] | None = None
    try:
        ua = page.evaluate("() => navigator.userAgent")
        useragent = str(ua) if ua else None
    except Exception:
        useragent = None
    try:
        ctx = getattr(page, "context", None)
        if ctx is not None:
            got = ctx.cookies(page.url)
            cookies = list(got) if got else None
    except Exception:
        cookies = None
    return {"useragent": useragent, "cookies": cookies}
