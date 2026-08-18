from __future__ import annotations

"""Small release-surface wrapper for the packaged WebHost.

Keeping this outside directory_web.py makes the presentation patch easy to
remove or evolve while preserving the existing API and admin implementation.
"""

import html

GITHUB_PROFILE = "https://github.com/gh0sted5456-us"

_FOOTER = r'''
<footer class="dws-fan-footer">
  <div class="dws-fan-marks" aria-label="Dragonwilds ecosystem and platform marks">
    <span class="dws-wordmark jagex">JAGEX</span>
    <span class="dws-wordmark runescape">RuneScape</span>
    <img src="/assets/platforms/xbox.svg" alt="Xbox" title="Xbox">
    <img src="/assets/platforms/playstation.svg" alt="PlayStation" title="PlayStation">
    <img src="/assets/platforms/nintendo.svg" alt="Nintendo" title="Nintendo">
    <img src="/assets/platforms/steam.svg" alt="Steam" title="Steam">
    <img src="/assets/platforms/epic.svg" alt="Epic Games" title="Epic Games">
  </div>
  <p>Dragonwilds Sync is a free community fan project, made by fans for fans. It is not affiliated with or endorsed by Jagex or the platform holders shown here. RuneScape, RuneScape: Dragonwilds, platform names, trademarks, artwork and other third-party rights remain the property of their respective owners.</p>
  <a class="dws-github-link" href="https://github.com/gh0sted5456-us" target="_blank" rel="noopener" aria-label="Open the Dragonwilds Sync GitHub profile" title="Dragonwilds Sync on GitHub">
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 .7a11.3 11.3 0 0 0-3.57 22.02c.57.1.78-.25.78-.55v-2.16c-3.18.7-3.85-1.35-3.85-1.35-.52-1.32-1.27-1.67-1.27-1.67-1.04-.7.08-.7.08-.7 1.15.08 1.75 1.18 1.75 1.18 1.02 1.75 2.68 1.24 3.33.95.1-.74.4-1.24.73-1.53-2.54-.29-5.21-1.27-5.21-5.59 0-1.24.44-2.25 1.18-3.04-.12-.29-.51-1.45.11-3 0 0 .96-.31 3.12 1.16a10.85 10.85 0 0 1 5.68 0C16.02 4.87 17 5.18 17 5.18c.62 1.55.23 2.71.11 3 .73.79 1.18 1.8 1.18 3.04 0 4.33-2.68 5.29-5.23 5.57.41.36.78 1.06.78 2.13v3.25c0 .3.21.66.79.55A11.3 11.3 0 0 0 12 .7Z"/></svg>
    <span>GitHub</span>
  </a>
</footer>
<style>
.dws-fan-footer{width:min(1160px,calc(100% - 34px));margin:22px auto 36px;padding:18px 20px;border-top:1px solid #393323;color:#8f9995;text-align:center;font-size:10px}.dws-fan-marks{display:flex;justify-content:center;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:10px}.dws-fan-marks img{width:24px;height:24px;padding:4px;border-radius:7px;object-fit:contain;filter:brightness(0) invert(1)}.dws-fan-marks img[alt="Xbox"]{background:#107c10}.dws-fan-marks img[alt="PlayStation"]{background:#0070d1}.dws-fan-marks img[alt="Nintendo"]{background:#e60012}.dws-fan-marks img[alt="Steam"]{background:#1b9fff}.dws-fan-marks img[alt="Epic Games"]{background:#444}.dws-wordmark{display:inline-grid;place-items:center;min-height:24px;padding:3px 8px;border:1px solid #46504d;border-radius:7px;color:#e6e1d3;font-weight:900;letter-spacing:.06em}.dws-wordmark.runescape{font-family:Georgia,serif;letter-spacing:0;color:#d7b454}.dws-fan-footer p{max-width:900px;margin:0 auto 12px}.dws-github-link{display:inline-flex;align-items:center;gap:7px;color:#d8bd70;text-decoration:none;font-weight:800}.dws-github-link svg{width:22px;height:22px;fill:currentColor}.dws-github-link:hover{color:#fff}
</style>
'''


def _decorate(page: bytes, *, public_browser: bool = False) -> bytes:
    text = page.decode("utf-8", "replace")
    if public_browser:
        # API remains available at /api/v1, but the public chrome no longer
        # advertises a raw developer endpoint beside the normal Worlds tab.
        text = text.replace('<a href="/api/v1">API</a>', '')
    if "dws-fan-footer" not in text:
        text = text.replace("</body>", _FOOTER + "</body>")
    return text.encode("utf-8")


def install() -> None:
    import directory_web

    if getattr(directory_web, "_DWS_RELEASE_POLISH_INSTALLED", False):
        return
    directory_web._DWS_RELEASE_POLISH_INSTALLED = True

    original_public = directory_web.public_browser_html
    original_detail = directory_web.detail_html
    original_login = directory_web.admin_login_html
    original_remote = directory_web.remote_admin_html

    directory_web.public_browser_html = lambda: _decorate(original_public(), public_browser=True)
    directory_web.detail_html = lambda *args, **kwargs: _decorate(original_detail(*args, **kwargs))
    directory_web.admin_login_html = lambda *args, **kwargs: _decorate(original_login(*args, **kwargs))
    directory_web.remote_admin_html = lambda *args, **kwargs: _decorate(original_remote(*args, **kwargs))
