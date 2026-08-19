from __future__ import annotations

"""Release-surface refinements for the packaged WebHost."""

_PRIVATE_PUBLIC_KEYS = {
    "hw_stats", "hardware", "health_config", "metadata_cache", "manifest_cache",
    "status", "runtime_metrics", "process_metrics", "server_install",
    "configuration", "configs", "config_files", "save_path", "save_dir",
    "game_root", "install_dir", "steamcmd_dir",
}

_KID_BADGE = '<span class="dws-audience kid"><svg viewBox="0 0 64 64" aria-hidden="true"><path fill="#63d69c" d="M32 4 54 12v17c0 14-9 25-22 31C19 54 10 43 10 29V12z"/><path fill="#10291f" d="M23 27a5 5 0 1 0 0-10 5 5 0 0 0 0 10m18 0a5 5 0 1 0 0-10 5 5 0 0 0 0 10M20 34c3 9 21 9 24 0l-6-2c-2 5-10 5-12 0z"/></svg>Kid-Friendly</span>'
_ADULT_BADGE = '<span class="dws-audience adult"><svg viewBox="0 0 64 64" aria-hidden="true"><circle cx="32" cy="32" r="28" fill="#bc4949"/><circle cx="32" cy="32" r="22" fill="#201313"/><text x="32" y="40" fill="#fff" font-family="Arial,sans-serif" font-size="22" font-weight="800" text-anchor="middle">18+</text></svg>Adults Only</span>'

_FOOTER = r'''
<footer class="dws-fan-footer"><div class="dws-fan-marks" aria-label="Dragonwilds ecosystem and platform marks"><span class="dws-wordmark">JAGEX</span><span class="dws-wordmark runescape">RuneScape</span><img src="/assets/platforms/xbox.svg" alt="Xbox"><img src="/assets/platforms/playstation.svg" alt="PlayStation"><img src="/assets/platforms/nintendo.svg" alt="Nintendo"><img src="/assets/platforms/steam.svg" alt="Steam"><img src="/assets/platforms/epic.svg" alt="Epic Games"><img src="/assets/platforms/discord.svg" alt="Discord"><img src="/assets/platforms/nexus.svg" alt="Nexus Mods"><img src="/assets/platforms/windows.svg" alt="Windows"><img src="/assets/platforms/linux.svg" alt="Linux"></div><p>Dragonwilds Sync is a free community fan project, made by fans for fans. It is not affiliated with or endorsed by Jagex or the platform holders shown here. RuneScape, RuneScape: Dragonwilds, platform names, trademarks, artwork and other third-party rights remain the property of their respective owners.</p><a class="dws-github-link" href="https://github.com/gh0sted5456-us" target="_blank" rel="noopener" aria-label="Open the Dragonwilds Sync GitHub profile"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 .7a11.3 11.3 0 0 0-3.57 22.02c.57.1.78-.25.78-.55v-2.16c-3.18.7-3.85-1.35-3.85-1.35-.52-1.32-1.27-1.67-1.27-1.67-1.04-.7.08-.7.08-.7 1.15.08 1.75 1.18 1.75 1.18 1.02 1.75 2.68 1.24 3.33.95.1-.74.4-1.24.73-1.53-2.54-.29-5.21-1.27-5.21-5.59 0-1.24.44-2.25 1.18-3.04-.12-.29-.51-1.45.11-3 0 0 .96-.31 3.12 1.16a10.85 10.85 0 0 1 5.68 0C16.02 4.87 17 5.18 17 5.18c.62 1.55.23 2.71.11 3 .73.79 1.18 1.8 1.18 3.04 0 4.33-2.68 5.29-5.23 5.57.41.36.78 1.06.78 2.13v3.25c0 .3.21.66.79.55A11.3 11.3 0 0 0 12 .7Z"/></svg><span>GitHub</span></a></footer>
<style>.dws-fan-footer{width:min(1160px,calc(100% - 34px));margin:22px auto 36px;padding:18px 20px;border-top:1px solid #393323;color:#8f9995;text-align:center;font-size:10px}.dws-fan-marks{display:flex;justify-content:center;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:10px}.dws-fan-marks img{width:24px;height:24px;object-fit:contain}.dws-wordmark{display:inline-grid;place-items:center;min-height:24px;padding:3px 8px;border:1px solid #46504d;border-radius:7px;color:#e6e1d3;font-weight:900;letter-spacing:.06em}.dws-wordmark.runescape{font-family:Georgia,serif;letter-spacing:0;color:#d7b454}.dws-fan-footer p{max-width:900px;margin:0 auto 12px}.dws-github-link{display:inline-flex;align-items:center;gap:7px;color:#d8bd70;text-decoration:none;font-weight:800}.dws-github-link svg{width:22px;height:22px;fill:currentColor}.dws-github-link:hover{color:#fff}</style>
'''

_STYLE = r'''<style>.dws-audience{display:inline-flex;align-items:center;gap:5px;padding:4px 8px;border:1px solid;border-radius:999px;font-size:10px;font-weight:850;letter-spacing:.04em;text-transform:uppercase}.dws-audience svg{width:17px;height:17px;display:block}.dws-audience.kid{color:#8ee8b2;border-color:#2f7450;background:rgba(45,113,78,.14)}.dws-audience.adult{color:#f0a5a5;border-color:#8b4444;background:rgba(130,54,54,.14)}</style>'''

_DETAIL_GUARD = r'''<script>(function(){function prune(){document.querySelectorAll('.all-world-metadata').forEach(function(n){n.remove()});document.querySelectorAll('.detail-actions a').forEach(function(n){if(/metadata json/i.test(n.textContent||''))n.remove()})}prune();new MutationObserver(prune).observe(document.documentElement,{childList:true,subtree:true})})();</script>'''


def _sanitize_public_world(row: dict) -> dict:
    if not isinstance(row, dict): return {}
    clean = {key: value for key, value in row.items() if key not in _PRIVATE_PUBLIC_KEYS}
    stack = clean.get("runtime_stack") if isinstance(clean.get("runtime_stack"), dict) else {}
    sync = stack.get("dragonwilds_sync") if isinstance(stack.get("dragonwilds_sync"), dict) else {}
    if sync:
        clean["sync_version"] = str(sync.get("version") or "")[:40]
        clean["runtime_stack"] = {"dragonwilds_sync": {"version": clean["sync_version"], "channel": str(sync.get("channel") or "")[:40], "protocol": sync.get("protocol")}}
    else: clean.pop("runtime_stack", None)
    return clean


def _decorate(page: bytes, *, public_browser: bool = False, detail: bool = False) -> bytes:
    text = page.decode("utf-8", "replace")
    if public_browser:
        text = text.replace('<a href="/api/v1">API</a>', '')
        text = text.replace('<span class="badge good">🛡 Kid-Friendly</span>', _KID_BADGE)
        text = text.replace('<span class="badge plain">18+ Adults Only</span>', _ADULT_BADGE)
    if detail and "dws-detail-guard" not in text:
        text = text.replace("</body>", '<span id="dws-detail-guard" hidden></span>' + _DETAIL_GUARD + "</body>")
    if "dws-audience" in text: text = text.replace("</head>", _STYLE + "</head>")
    if "dws-fan-footer" not in text: text = text.replace("</body>", _FOOTER + "</body>")
    return text.encode("utf-8")


def install() -> None:
    import directory_web
    if getattr(directory_web, "_DWS_RELEASE_POLISH_INSTALLED", False): return
    directory_web._DWS_RELEASE_POLISH_INSTALLED = True
    original_public, original_detail = directory_web.public_browser_html, directory_web.detail_html
    original_login, original_remote = directory_web.admin_login_html, directory_web.remote_admin_html
    directory_web.public_browser_html = lambda: _decorate(original_public(), public_browser=True)
    directory_web.detail_html = lambda *args, **kwargs: _decorate(original_detail(*args, **kwargs), detail=True)
    directory_web.admin_login_html = lambda *args, **kwargs: _decorate(original_login(*args, **kwargs))
    directory_web.remote_admin_html = lambda *args, **kwargs: _decorate(original_remote(*args, **kwargs))
    import directory_host
    original_catalog_worlds = directory_host.DirectoryHost.catalog_worlds
    def public_catalog_worlds(self): return [_sanitize_public_world(row) for row in original_catalog_worlds(self)]
    directory_host.DirectoryHost.catalog_worlds = public_catalog_worlds
