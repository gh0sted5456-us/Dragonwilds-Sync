from __future__ import annotations

"""One-shot RC2 patcher for hands-on release testing feedback.

This script intentionally performs narrow, asserted edits against the current
release-candidate tree.  It exists so the large V2 renderer/service files can be
updated atomically in GitHub Actions without replacing them through the API.
"""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        if new in text:
            return text
        raise RuntimeError(f"RC2 patch marker missing: {label}")
    return text.replace(old, new, 1)


def patch_profile_store() -> None:
    path = "backend/profile_store.py"
    text = read(path)
    text = text.replace('"defender_review_enabled": True,', '"defender_review_enabled": False,')
    text = text.replace('"remote_admin": {"enabled": True, "users": [],', '"remote_admin": {"enabled": False, "users": [],')
    if '"communities": [],' not in text:
        text = replace_once(text, '            "integrations": default_integrations(),\n', '            "integrations": default_integrations(),\n            "communities": [],\n', "community state default")
    write(path, text)


def patch_local_world() -> None:
    path = "backend/local_world.py"
    text = read(path)
    text = text.replace('from security_scanner import defender_scan\n', '')
    if 'DELETED_SAVES_PATH' not in text:
        text = replace_once(text, 'PRIVATE_PROFILES_DIR = WORLD_PROFILE_ROOT\n', '''PRIVATE_PROFILES_DIR = WORLD_PROFILE_ROOT
DELETED_SAVES_PATH = WORLD_PROFILE_ROOT / ".deleted-saves.json"


def _deleted_save_tombstones() -> dict:
    value = read_json(DELETED_SAVES_PATH, {"version": 1, "saves": {}})
    saves = value.get("saves") if isinstance(value, dict) else None
    return dict(saves) if isinstance(saves, dict) else {}


def _write_deleted_save_tombstones(saves: dict) -> None:
    write_json(DELETED_SAVES_PATH, {"version": 1, "updated_at": time.time(), "saves": saves})


def _save_tombstone_key(path: Path) -> str:
    try:
        return str(path.resolve()).replace("\\\\", "/").casefold()
    except OSError:
        return str(path).replace("\\\\", "/").casefold()
''', "save deletion tombstones")
    if 'deleted_saves = _deleted_save_tombstones()' not in text:
        text = replace_once(text, '    discovered = []\n    newly_created = []\n', '    discovered = []\n    newly_created = []\n    deleted_saves = _deleted_save_tombstones()\n    deleted_saves_changed = False\n', "load deletion tombstones")
        text = replace_once(text, '            pid = _save_profile_id(save_path)\n', '''            tombstone_key = _save_tombstone_key(save_path)
            tombstone = deleted_saves.get(tombstone_key)
            if isinstance(tombstone, dict):
                same_revision = (abs(float(tombstone.get("mtime") or 0) - float(stat.st_mtime)) < 0.001
                                 and int(tombstone.get("size") or -1) == int(stat.st_size))
                if same_revision:
                    continue
                deleted_saves.pop(tombstone_key, None)
                deleted_saves_changed = True
            pid = _save_profile_id(save_path)
''', "skip deleted save revision")
        text = replace_once(text, '    return discovered\n\n\ndef list_profiles()', '    if deleted_saves_changed:\n        _write_deleted_save_tombstones(deleted_saves)\n    return discovered\n\n\ndef list_profiles()', "persist changed tombstones")
    if 'tombstones = _deleted_save_tombstones()' not in text:
        text = replace_once(text, '''    if pid == SINGLEPLAYER_ID:
        raise ValueError("The baseline SinglePlayer profile cannot be deleted; rename or archive it instead.")
    root = _profile_root(pid)
''', '''    if pid == SINGLEPLAYER_ID:
        raise ValueError("The baseline SinglePlayer profile cannot be deleted; rename or archive it instead.")
    profile = read_json(_profile_file(pid), {})
    save_path = Path(str(profile.get("save_path") or "")) if profile.get("auto_detected") and profile.get("save_path") else None
    if save_path is not None and save_path.is_file():
        try:
            stat = save_path.stat()
            tombstones = _deleted_save_tombstones()
            tombstones[_save_tombstone_key(save_path)] = {
                "path": str(save_path), "mtime": float(stat.st_mtime), "size": int(stat.st_size),
                "profile_id": pid, "deleted_at": time.time(),
            }
            _write_deleted_save_tombstones(tombstones)
        except OSError:
            pass
    root = _profile_root(pid)
''', "record save tombstone")
    write(path, text)


def patch_directory_host() -> None:
    path = "backend/directory_host.py"
    text = read(path)
    text = text.replace('"""Serve only the five bundled, presentation-only platform marks."""', '"""Serve the bundled colored platform/community marks used by the public catalog."""')
    old = '''    allowed = {"steam", "epic", "nintendo", "playstation", "xbox"}
    key = str(name or "").casefold().removesuffix(".svg")
    if key not in allowed:
        return b""
    bundle_root = getattr(sys, "_MEIPASS", "")
    candidates = []
    if bundle_root:
        candidates.append(Path(bundle_root) / "renderer" / "assets" / "platforms" / f"{'epicgames' if key == 'epic' else key}.svg")
        candidates.append(Path(bundle_root) / "platforms" / f"{'epicgames' if key == 'epic' else key}.svg")
    candidates.append(Path(__file__).resolve().parent.parent / "renderer" / "assets" / "platforms" / f"{'epicgames' if key == 'epic' else key}.svg")
'''
    new = '''    aliases = {"epic": "epicgames", "nexus": "nexusmods", "psn": "playstation"}
    allowed = {"steam", "epic", "epicgames", "nintendo", "playstation", "psn", "xbox", "discord", "nexus", "nexusmods", "windows", "linux"}
    key = str(name or "").casefold().removesuffix(".svg")
    if key not in allowed:
        return b""
    filename = aliases.get(key, key) + ".svg"
    bundle_root = getattr(sys, "_MEIPASS", "")
    candidates = []
    if bundle_root:
        candidates.append(Path(bundle_root) / "renderer" / "assets" / "platforms" / filename)
        candidates.append(Path(bundle_root) / "platforms" / filename)
    candidates.append(Path(__file__).resolve().parent.parent / "renderer" / "assets" / "platforms" / filename)
'''
    if old in text:
        text = text.replace(old, new, 1)
    elif 'aliases = {"epic": "epicgames"' not in text:
        raise RuntimeError("RC2 platform icon marker missing")
    text = text.replace('"remote_admin": {"enabled": True, "users": [],', '"remote_admin": {"enabled": False, "users": [],')
    text = text.replace('"enabled": bool(incoming_remote.get("enabled", True)),', '"enabled": bool(incoming_remote.get("enabled", False)),')
    text = text.replace('remote_enabled = bool((controller.config.get("remote_admin") or {}).get("enabled", True))', 'remote_enabled = bool((controller.config.get("remote_admin") or {}).get("enabled", False))')
    text = text.replace('self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True, name="Dragonwilds-World-Directory")', 'self.thread = threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True, name="Dragonwilds-World-Directory")')
    text = text.replace('mapping_thread.join(timeout=2.0)', 'mapping_thread.join(timeout=0.15)')
    if '"directory_sources":' not in text[text.find('def _catalog_row'):text.find('def catalog_worlds')]:
        marker = '            "source": source, "source_label": "Dragonwilds Sync" if sync_ready else ("LobbySup public observation" if source == "lobbysup-public" else "Dragonwilds public discovery"),\n'
        addition = '''            "host_os": str(row.get("host_os") or status.get("host_os") or "other")[:24].casefold(),
            "server_os_badge": row.get("server_os_badge") if isinstance(row.get("server_os_badge"), dict) else {},
            "directory_sources": list((row.get("public_discovery") or {}).get("directory_sources") or row.get("directory_sources") or [])[:20],
'''
        text = replace_once(text, marker, addition + marker, "catalog community/OS metadata")
    write(path, text)


def patch_server_systems() -> None:
    path = "backend/server_systems.py"
    text = read(path)
    # Defender remains import-compatible for historical V2 tests, but active mod
    # install/update paths no longer invoke Windows Defender or gate installs on it.
    pattern = re.compile(r'def review_with_defender\(.*?\n(?=def |class |\n\n[A-Z_]+\s*=)', re.S)
    match = pattern.search(text)
    if match and 'Defender integration retired in RC2' not in match.group(0):
        replacement = '''def review_with_defender(path: str, label: str = "content") -> dict:
    """Compatibility no-op: Defender integration retired in RC2.

    Archive path validation, hashes, staging and rollback remain launcher-owned;
    OS antivirus products can continue scanning files normally outside Sync.
    """
    return {"available": False, "enabled": False, "blocked": False, "skipped": True,
            "reason": "Defender integration retired in RC2", "path": str(path or ""), "label": str(label or "content")}


'''
        text = text[:match.start()] + replacement + text[match.end():]
    text = text.replace('            if lower == "mods.txt":\n                continue\n', '            if lower in {"mods.txt", "rsdwtools"}:\n                continue\n')
    write(path, text)


def patch_service() -> None:
    path = "backend/dragonwilds_service.py"
    text = read(path)
    text = text.replace('set_defender_review_enabled(bool((state.get("application") or {}).get("defender_review_enabled", True)))', 'set_defender_review_enabled(False)')
    if 'method == "application.communities.settings"' not in text:
        marker = '    if method == "application.recommended_mods.refresh":\n'
        block = '''    if method in {"application.communities.list", "application.communities.settings"}:
        application = state.setdefault("application", {})
        communities = list(application.get("communities") or [])
        if method == "application.communities.settings":
            incoming = params.get("communities")
            if not isinstance(incoming, list):
                raise ValueError("Communities must be a list")
            normalized = []
            seen = set()
            for raw in incoming[:50]:
                if not isinstance(raw, dict):
                    continue
                name = str(raw.get("name") or "Community").strip()[:120] or "Community"
                cid = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(raw.get("id") or name).strip()).strip("-.").casefold()[:72] or secrets.token_hex(6)
                if cid in seen:
                    continue
                seen.add(cid)
                def clean_url(value):
                    url = str(value or "").strip()[:2048]
                    if not url:
                        return ""
                    parsed = urllib.parse.urlparse(url)
                    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
                        raise ValueError(f"Community {name} contains an invalid HTTP(S) URL")
                    return url
                normalized.append({
                    "id": cid, "name": name, "enabled": raw.get("enabled", True) is not False,
                    "worlds_url": clean_url(raw.get("worlds_url") or raw.get("directory_url")),
                    "recommendations_url": clean_url(raw.get("recommendations_url") or raw.get("mods_url")),
                    "website_url": clean_url(raw.get("website_url")),
                    "icon_url": clean_url(raw.get("icon_url")),
                })
            communities = normalized
            application["communities"] = communities
            recommendation_cfg = application.setdefault("recommended_mods", {})
            recommendation_cfg["community_sources"] = [
                {"id": f"community:{row['id']}", "community_id": row["id"], "name": row["name"],
                 "url": row["recommendations_url"], "enabled": row["enabled"]}
                for row in communities if row.get("recommendations_url")
            ]
            discovery_cfg = application.setdefault("world_discovery", {})
            existing = [row for row in (discovery_cfg.get("directory_sources") or [])
                        if isinstance(row, dict) and not str(row.get("id") or "").startswith("community:")]
            existing.extend({
                "id": f"community:{row['id']}", "community_id": row["id"], "name": row["name"],
                "url": row["worlds_url"], "enabled": row["enabled"], "publish_enabled": False,
                "priority": 200,
            } for row in communities if row.get("worlds_url"))
            discovery_cfg["directory_sources"] = existing
            save_state(state)
        return {"communities": communities, "state": public_state(state)}

    if method == "network.default_router":
        gateway = ""
        try:
            if sys.platform.startswith("win"):
                result = run_hidden(["route", "print", "-4", "0.0.0.0"], capture_output=True, text=True, timeout=4)
                for line in (result.stdout or "").splitlines():
                    found = re.match(r"^\\s*0\\.0\\.0\\.0\\s+0\\.0\\.0\\.0\\s+(\\S+)", line)
                    if found:
                        gateway = found.group(1); break
            else:
                result = run_hidden(["ip", "route", "show", "default"], capture_output=True, text=True, timeout=4)
                found = re.search(r"\\bdefault\\s+via\\s+(\\S+)", result.stdout or "")
                if found: gateway = found.group(1)
        except Exception:
            gateway = ""
        if not gateway:
            raise RuntimeError("The default router/gateway could not be detected on this machine.")
        return {"gateway": gateway, "url": f"http://{gateway}/"}

'''
        text = replace_once(text, marker, block + marker, "community/default-router RPC")
    # Make the historical explicit Defender scan RPC a compatibility no-op if present.
    text = re.sub(r'(if method == "server\.maintenance\.defender_scan":\n)(\s+)(?:.*?)(?=\n\s{4}if method == )', lambda m: m.group(1) + m.group(2) + 'return {"available": False, "enabled": False, "blocked": False, "skipped": True, "reason": "Defender integration retired"}\n', text, count=1, flags=re.S)
    write(path, text)


def patch_renderer_app() -> None:
    path = "renderer/app.js"
    text = read(path)
    text = text.replace("const PLATFORM_LOGOS = {steam:'steam.svg',epic:'epicgames.svg',xbox:'xbox.svg',playstation:'playstation.svg',nintendo:'nintendo.svg',discord:'discord.svg',nexus:'nexusmods.svg'};",
                        "const PLATFORM_LOGOS = {steam:'steam.svg',epic:'epicgames.svg',xbox:'xbox.svg',playstation:'playstation.svg',nintendo:'nintendo.svg',discord:'discord.svg',nexus:'nexusmods.svg',windows:'windows.svg',linux:'linux.svg'};")
    # Visible terminology only; internal route id remains integrations for V2 compatibility.
    text = text.replace("integrations:'Integrations'", "integrations:'Community'")
    text = text.replace('>Open UniFi ↗</button>', '>Open Default Router Homepage</button>')
    text = text.replace('data-open-external="https://unifi.ui.com/"', 'id="open-default-router-home" data-router-home="1"')
    text = text.replace('Manual router forwarding · recommended for UniFi', 'Manual router forwarding')
    text = text.replace('Defender review, and RSDW cache.', 'runtime validation, and RSDW cache.')
    # Remove the built-in changelog block; release-polish supplies the only GitHub-fed changelog.
    text = re.sub(r'\s*<section class="settings-section about-section"><div class="panel-header"><div><h2>Changelog</h2>.*?</section>', '', text, count=1, flags=re.S)
    # Remove the visible Defender settings section while leaving legacy RPC compatibility dormant.
    text = re.sub(r'\s*<section class="settings-section"><h2>Microsoft Defender Review</h2>.*?</section>', '', text, count=1, flags=re.S)
    write(path, text)


def patch_directory_web() -> None:
    path = "backend/directory_web.py"
    text = read(path)
    old = "function platformBadges(w){const c=w.platform_compatibility||{},defs=[['steam','Steam'],['epic','Epic Games'],['nintendo','Nintendo'],['playstation','PlayStation'],['xbox','Xbox']];return `<div class=\"platforms\">${defs.filter(([key])=>c[key]===true).map(([key,label])=>`<img src=\"/assets/platforms/${key}.svg\" title=\"${esc(label)} compatible\" alt=\"${esc(label)}\">`).join('')}</div>`}"
    new = "function platformBadges(w){const c=w.platform_compatibility||{},defs=[['steam','Steam'],['epic','Epic Games'],['nintendo','Nintendo'],['playstation','PlayStation'],['xbox','Xbox']];const os=String(w.host_os||'').toLowerCase(),host=os==='windows'?[['windows','Windows Server']]:os==='linux'?[['linux','Linux Server']]:[];return `<div class=\"platforms\">${host.concat(defs.filter(([key])=>c[key]===true)).map(([key,label])=>`<img src=\"/assets/platforms/${key}.svg\" title=\"${esc(label)}\" alt=\"${esc(label)}\">`).join('')}</div>`}"
    if old in text:
        text = text.replace(old, new, 1)
    if 'function communitySourceBadges(w)' not in text:
        text = replace_once(text, "function syncTags(w){return [...new Set([...(w.sync_tags||(w.sync_ready?w.tags||[]:[]))].filter(Boolean))].slice(0,6)}\n", "function syncTags(w){return [...new Set([...(w.sync_tags||(w.sync_ready?w.tags||[]:[]))].filter(Boolean))].slice(0,6)}\nfunction communitySourceBadges(w){const rows=w.directory_sources||[];if(!rows.length)return '';return `<span class=\"community-sources\">${rows.slice(0,2).map(r=>`<span title=\"Shared by ${esc(r.name||'Community')}\">${esc(r.name||'Community')}</span>`).join('')}${rows.length>2?`<span>+${rows.length-2}</span>`:''}</span>`}\n", "web community source badges")
        text = text.replace('${identityBadges(w)}${sync?', '${identityBadges(w)}${communitySourceBadges(w)}${sync?', 1)
    write(path, text)


def patch_web_release_polish() -> None:
    path = "backend/web_release_polish.py"
    text = read(path)
    # Footer uses the colored SVG artwork directly, with no boxed backgrounds or forced-white filters.
    text = text.replace('<img src="/assets/platforms/epic.svg" alt="Epic Games">', '<img src="/assets/platforms/epic.svg" alt="Epic Games"><img src="/assets/platforms/discord.svg" alt="Discord"><img src="/assets/platforms/nexus.svg" alt="Nexus Mods"><img src="/assets/platforms/windows.svg" alt="Windows"><img src="/assets/platforms/linux.svg" alt="Linux">')
    text = re.sub(r'\.dws-fan-marks img\{[^}]+\}', '.dws-fan-marks img{width:24px;height:24px;object-fit:contain}', text, count=1)
    text = re.sub(r'\.dws-fan-marks img\[alt="Xbox"\].*?\.dws-wordmark\{', '.dws-wordmark{', text, count=1)
    write(path, text)


def patch_runtime_and_build_contract() -> None:
    build_path = "scripts/build_windows.ps1"
    text = read(build_path)
    if "resources\\RSDWTools-baseline.zip' 'Bundled RSDWTools bridge baseline'" not in text:
        text = replace_once(text, "    Test-RequiredFile 'resources\\RuneSchema-core-latest.zip' 'Bundled RuneSchema core'\n", "    Test-RequiredFile 'resources\\RuneSchema-core-latest.zip' 'Bundled RuneSchema core'\n    Test-RequiredFile 'resources\\RSDWTools-baseline.zip' 'Bundled RSDWTools bridge baseline'\n", "RSDWTools build requirement")
    text = text.replace("Fail-Build 'Portable package still contains the removed RSDWTools UE4SS mod.'", "Fail-Build 'UE4SS core archive unexpectedly contains RSDWTools; the launcher-owned RSDWTools baseline must remain independently updateable.'")
    write(build_path, text)

    test_path = "backend/test_build_contract.py"
    test = read(test_path)
    test = test.replace('    assert "Portable package still contains the removed RSDWTools UE4SS mod" in text\n', '    assert "resources\\\\RSDWTools-baseline.zip" in text\n    assert "Bundled RSDWTools bridge baseline" in text\n')
    write(test_path, test)


def write_colored_icons() -> None:
    icon_dir = ROOT / "renderer" / "assets" / "platforms"
    icon_dir.mkdir(parents=True, exist_ok=True)
    colors = {
        "steam.svg": "#66C0F4", "discord.svg": "#5865F2", "nexusmods.svg": "#DA8E35",
        "epicgames.svg": "#F2F2F2", "nintendo.svg": "#E60012", "xbox.svg": "#107C10",
        "playstation.svg": "#0070D1",
    }
    for name, color in colors.items():
        path = icon_dir / name
        text = path.read_text(encoding="utf-8")
        text = re.sub(r'fill="(?:#(?:000000|000|111111)|black)"', f'fill="{color}"', text, flags=re.I)
        if 'fill=' not in text:
            text = text.replace('<svg ', f'<svg fill="{color}" ', 1)
        else:
            text = text.replace('fill="currentColor"', f'fill="{color}"')
        path.write_text(text, encoding="utf-8")
    (icon_dir / "windows.svg").write_text('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" aria-label="Windows"><path fill="#0078D4" d="M5 10 29 6v24H5V10Zm28-5 26-4v29H33V5ZM5 34h24v24L5 54V34Zm28 0h26v29l-26-4V34Z"/></svg>''', encoding="utf-8")
    (icon_dir / "linux.svg").write_text('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" aria-label="Linux"><path fill="#F5C542" d="M19 50c2-7 5-11 7-14-2-5-1-14 1-20 1-4 4-7 7-7s6 3 7 7c2 6 3 15 1 20 3 4 6 9 7 14l-9 6-7-5-7 5-7-6Z"/><path fill="#202124" d="M27 17c1-6 3-10 7-10s6 4 7 10c1 5-1 9-7 9s-8-4-7-9Z"/><ellipse cx="31" cy="16" rx="2" ry="3" fill="#fff"/><ellipse cx="37" cy="16" rx="2" ry="3" fill="#fff"/><circle cx="31" cy="17" r="1"/><circle cx="37" cy="17" r="1"/><path fill="#F28C28" d="m29 22 5-3 5 3-5 4z"/><path fill="#fff" d="M25 39c2 6 5 10 9 10s7-4 9-10c-2-4-5-6-9-6s-7 2-9 6Z"/></svg>''', encoding="utf-8")


def write_rc2_renderer() -> None:
    write("renderer/release-rc2.css", r'''/* RC2 hands-on testing refinements */
.sidebar,.sidebar *,aside.sidebar,aside.sidebar *{transition-duration:.08s!important;animation-duration:.08s!important}
.platform-logo,.platforms img,.dws-fan-marks img{background:transparent!important;border:0!important;box-shadow:none!important;outline:0!important;filter:none!important;padding:0!important;object-fit:contain}
.world-platform-badge,.world-community-badge,.world-audience-badge,.community-source-chip{border:0!important;box-shadow:none!important;outline:0!important}
.community-source-chips,.community-sources{display:inline-flex;align-items:center;gap:4px;flex-wrap:wrap}.community-source-chip,.community-sources>span{padding:2px 6px;border-radius:999px;background:color-mix(in srgb,var(--gold,#d4b069) 12%,transparent);color:var(--gold,#d4b069);font-size:9px;font-weight:750;white-space:nowrap}
.rc2-community-list{display:grid;gap:8px}.rc2-community-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:center;padding:12px 14px;border:1px solid var(--border);border-radius:12px;background:var(--panel)}.rc2-community-row small{display:block;color:var(--muted);margin-top:3px}.rc2-community-actions{display:flex;gap:6px;align-items:center}.rc2-community-form{display:grid;grid-template-columns:minmax(150px,.7fr) minmax(220px,1fr) minmax(220px,1fr) auto;gap:8px;margin-top:12px}.rc2-community-form input{min-width:0}.rc2-remote-jump{margin:10px 0;display:flex;justify-content:flex-end}.rc2-retired{display:none!important}@media(max-width:900px){.rc2-community-form{grid-template-columns:1fr}.rc2-community-row{grid-template-columns:1fr}}
''')
    write("renderer/release-rc2.js", r'''(() => {
  'use strict';
  const api=window.dragonwilds;
  let cache=null, fetched=0, busy=false;
  const esc=(v)=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  async function appState(force=false){if(!api?.invoke)return cache||{};if(!force&&cache&&Date.now()-fetched<3000)return cache;try{cache=await api.invoke('state.get',{});fetched=Date.now()}catch(_){}return cache||{}}
  function renameCommunity(root=document){const button=root.querySelector('[data-settings-tab="integrations"]');if(button){[...button.childNodes].filter(n=>n.nodeType===Node.TEXT_NODE).forEach(n=>{if(/integrations/i.test(n.textContent||''))n.textContent=(n.textContent||'').replace(/Integrations/ig,'Community')});button.querySelectorAll('span,strong,div').forEach(n=>{if(/^integrations$/i.test((n.textContent||'').trim()))n.textContent='Community'});button.title='Community';button.setAttribute('aria-label','Community')}}
  function retireHeavyWindows(root=document){root.querySelectorAll('[id^="detach-"],[data-detach-route],[data-open-detached]').forEach(n=>n.classList.add('rc2-retired'));root.querySelectorAll('button').forEach(n=>{if(/^open in window$/i.test((n.textContent||'').trim()))n.classList.add('rc2-retired')})}
  function removeDefender(root=document){root.querySelectorAll('section,.settings-section,.identity-box,.detail-section').forEach(section=>{const text=(section.textContent||'').toLowerCase();if(text.includes('microsoft defender')||/^\s*(server|client) defender\b/.test(text))section.classList.add('rc2-retired')})}
  function singleGithubChangelog(root=document){root.querySelectorAll('.settings-section').forEach(section=>{if(section.id==='github-release-changelog')return;const h=[...section.querySelectorAll('h2,h3')].find(x=>/^changelog$/i.test((x.textContent||'').trim()));if(h)section.classList.add('rc2-retired')})}
  async function openRouter(event){event.preventDefault();event.stopPropagation();event.stopImmediatePropagation();try{const r=await api.invoke('network.default_router',{});if(r?.url)await api.openExternal(r.url)}catch(e){alert(`Default router could not be opened: ${e.message||e}`)}}
  function fixRouter(root=document){root.querySelectorAll('[data-router-home],a[href*="unifi.ui.com"],button[data-open-external*="unifi.ui.com"]').forEach(node=>{node.textContent='Open Default Router Homepage';node.removeAttribute('data-open-external');node.removeAttribute('href');if(node.dataset.rc2Router!=='1'){node.dataset.rc2Router='1';node.addEventListener('click',openRouter,true)}})}
  function combineServerManagement(root=document){const settings=root.querySelector('[data-webhost-tab="settings"]');if(settings)settings.textContent='Website, Networking & Remote Access';root.querySelectorAll('[data-webhost-tab="remote"]').forEach(b=>b.classList.add('rc2-retired'));const panel=[...root.querySelectorAll('.webhost-authority')].find(n=>/server users/i.test(n.querySelector('h3')?.textContent||''));if(panel){const h=panel.querySelector('h3');if(h)h.textContent='Remote Users & Permissions';const add=panel.querySelector('#add-webhost-user');if(add){add.textContent='+ Add Remote User';add.title='Create credentials and assign permissions for one hosted World'}const section=panel.closest('.settings-section');if(section&&!section.querySelector('.rc2-remote-jump')){const jump=document.createElement('div');jump.className='rc2-remote-jump';jump.innerHTML='<button class="btn primary compact-btn" data-jump-remote-users>Manage Remote Users & Permissions</button>';section.insertBefore(jump,section.children[1]||null);jump.querySelector('button').onclick=()=>panel.scrollIntoView({behavior:'smooth',block:'start'})}}}
  function allWorlds(s){return [...(s?.client?.worlds||[]),...(s?.client?.discovered_worlds||[]),...(s?.client?.directory_worlds||[]),...(s?.client?.private_worlds||[]),...(s?.server_profiles||[])]}
  async function annotateCommunities(root=document){const cards=[...root.querySelectorAll('[data-world-id]')].filter(c=>!c.dataset.rc2Communities);if(!cards.length)return;const s=await appState();const map=new Map(allWorlds(s).map(w=>[String(w.id||''),w]));cards.forEach(card=>{card.dataset.rc2Communities='1';const world=map.get(String(card.dataset.worldId||''));const sources=world?.public_discovery?.directory_sources||world?.directory_sources||[];if(!sources.length)return;const host=card.querySelector('.world-tag-row,.tag-groups,.world-badges,.world-list-tags,.world-copy')||card;const chips=document.createElement('span');chips.className='community-source-chips';chips.title='Community lists that shared this same verified World';chips.innerHTML=sources.slice(0,2).map(x=>`<span class="community-source-chip">${esc(x.name||'Community')}</span>`).join('')+(sources.length>2?`<span class="community-source-chip">+${sources.length-2}</span>`:'');host.appendChild(chips)})}
  async function renderCommunity(root=document){const active=root.querySelector('[data-settings-tab="integrations"].active');if(!active)return;const note=root.querySelector('.settings-page-note');const page=note?.parentElement;if(!page||page.querySelector('#rc2-community'))return;const s=await appState(true);const rows=s?.application?.communities||[];[...page.children].forEach(child=>{if(child!==note&&!child.classList.contains('settings-subnav'))child.classList.add('rc2-retired')});const section=document.createElement('section');section.id='rc2-community';section.className='settings-section';const list=rows.length?rows.map(row=>`<div class="rc2-community-row" data-community-id="${esc(row.id)}"><div><strong>${esc(row.name||'Community')}</strong><small>${row.worlds_url?'World list · ':''}${row.recommendations_url?'Recommended Mods · ':''}${row.website_url?'Website':''}</small><small>${esc(row.worlds_url||'')}${row.worlds_url&&row.recommendations_url?' · ':''}${esc(row.recommendations_url||'')}</small></div><div class="rc2-community-actions"><span class="status-pill ${row.enabled===false?'unknown':'online'}">${row.enabled===false?'PAUSED':'ENABLED'}</span><button class="btn ghost compact-btn" data-community-toggle="${esc(row.id)}">${row.enabled===false?'Enable':'Pause'}</button><button class="btn danger compact-btn" data-community-remove="${esc(row.id)}">Remove</button></div></div>`).join(''):'<div class="empty-state">No communities added yet. A community can contribute a World directory, Recommended Mods feed, or both.</div>';section.innerHTML=`<div class="panel-header"><div><h2>Community</h2><span class="panel-subtitle">Subscribe to communities you are part of. Their World directories are fingerprint-deduplicated; if several communities advertise the same World, Dragonwilds Sync shows one World with multiple community identifiers.</span></div><button class="btn primary" data-community-refresh>Refresh Community Content</button></div><div class="rc2-community-list">${list}</div><div class="rc2-community-form"><input class="field" data-community-name placeholder="Community name"><input class="field" data-community-worlds placeholder="World directory URL (optional)"><input class="field" data-community-mods placeholder="Recommended Mods JSON URL (optional)"><button class="btn primary" data-community-add>Add Community</button></div><div class="identity-box"><strong>Community subscriptions are data sources, not accounts</strong><p>They can supply public World listings and Recommended Mods. Dragonwilds Sync still verifies compatible World fingerprints and keeps duplicate community sightings attached to one World card.</p></div>`;page.appendChild(section);
    const save=async(next)=>{if(busy)return;busy=true;try{const out=await api.invoke('application.communities.settings',{communities:next});cache=out.state||cache;fetched=Date.now();await Promise.allSettled([api.invoke('application.recommended_mods.refresh',{}),api.invoke('world.directory.refresh',{})]);cache=null;section.remove();renderCommunity(root)}finally{busy=false}};
    section.querySelector('[data-community-add]').onclick=()=>{const name=section.querySelector('[data-community-name]').value.trim(),worlds=section.querySelector('[data-community-worlds]').value.trim(),mods=section.querySelector('[data-community-mods]').value.trim();if(!name||(!worlds&&!mods))return;save([...rows,{name,worlds_url:worlds,recommendations_url:mods,enabled:true}])};section.querySelectorAll('[data-community-remove]').forEach(b=>b.onclick=()=>save(rows.filter(r=>String(r.id)!==String(b.dataset.communityRemove))));section.querySelectorAll('[data-community-toggle]').forEach(b=>b.onclick=()=>save(rows.map(r=>String(r.id)===String(b.dataset.communityToggle)?{...r,enabled:r.enabled===false}:r)));section.querySelector('[data-community-refresh]').onclick=async()=>{await Promise.allSettled([api.invoke('application.recommended_mods.refresh',{}),api.invoke('world.directory.refresh',{})]);cache=null;section.remove();renderCommunity(root)}}
  function smoothIcons(root=document){root.querySelectorAll('.platform-logo,.platforms img').forEach(img=>{img.style.filter='none';img.style.background='transparent';img.style.border='0';img.style.boxShadow='none'})}
  function enhance(){renameCommunity();retireHeavyWindows();removeDefender();singleGithubChangelog();fixRouter();combineServerManagement();smoothIcons();void renderCommunity();void annotateCommunities()}
  let scheduled=false;const schedule=()=>{if(scheduled)return;scheduled=true;requestAnimationFrame(()=>{scheduled=false;enhance()})};
  document.addEventListener('click',e=>{if(e.target.closest('[data-settings-tab],[data-route]')){cache=null;setTimeout(schedule,20)}},true);
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',schedule,{once:true});else schedule();
  new MutationObserver(schedule).observe(document.documentElement,{childList:true,subtree:true});
})();
''')


def patch_index_and_package() -> None:
    index_path = "renderer/index.html"
    index = read(index_path)
    if 'release-rc2.css' not in index:
        index = index.replace('<link rel="stylesheet" href="release-overrides.css?v=1.0.0-rc-presentation-1" />', '<link rel="stylesheet" href="release-overrides.css?v=1.0.0-rc-presentation-1" />\n  <link rel="stylesheet" href="release-rc2.css?v=2.0.0-rc2" />')
    if 'release-rc2.js' not in index:
        index = index.replace('<script src="upstream-sources.js?v=1.0.0-upstream-registry-1"></script>', '<script src="upstream-sources.js?v=1.0.0-upstream-registry-1"></script>\n  <script src="release-rc2.js?v=2.0.0-rc2"></script>')
    write(index_path, index)
    package_path = "package.json"
    package = read(package_path)
    package = package.replace('node --check renderer/release-world-version.js &&', 'node --check renderer/release-world-version.js && node --check renderer/release-rc2.js &&')
    write(package_path, package)


def write_test() -> None:
    write("backend/test_rc2_feedback.py", r'''from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent

def main():
    profile=(ROOT/'backend/profile_store.py').read_text(encoding='utf-8')
    local=(ROOT/'backend/local_world.py').read_text(encoding='utf-8')
    host=(ROOT/'backend/directory_host.py').read_text(encoding='utf-8')
    systems=(ROOT/'backend/server_systems.py').read_text(encoding='utf-8')
    service=(ROOT/'backend/dragonwilds_service.py').read_text(encoding='utf-8')
    app=(ROOT/'renderer/app.js').read_text(encoding='utf-8')
    rc2=(ROOT/'renderer/release-rc2.js').read_text(encoding='utf-8')
    assert '"server_mode_enabled": False' in profile
    assert '"remote_admin": {"enabled": False' in profile
    assert '"communities": []' in profile
    assert 'DELETED_SAVES_PATH' in local and '_write_deleted_save_tombstones' in local
    assert 'ensure_rsdwtools_baseline(layout.ue4ss_mods_dir)' in systems
    assert 'lower in {"mods.txt", "rsdwtools"}' in systems
    assert 'Defender integration retired in RC2' in systems
    for name in ('discord','nexus','windows','linux'):
        assert name in host
    assert 'poll_interval": 0.05' in host
    assert 'method == "application.communities.settings"' in service
    assert 'method == "network.default_router"' in service
    assert 'unifi.ui.com' not in app
    assert 'Open Default Router Homepage' in app
    assert 'Microsoft Defender Review' not in app
    assert 'Website, Networking & Remote Access' in rc2
    assert 'Community' in rc2 and 'directory_sources' in rc2
    assert (ROOT/'renderer/assets/platforms/windows.svg').is_file()
    assert (ROOT/'renderer/assets/platforms/linux.svg').is_file()
    print('RC2 testing feedback contract passed')

if __name__=='__main__': main()
''')
    runner_path = "scripts/run_backend_tests.cjs"
    runner = read(runner_path)
    if "backend/test_rc2_feedback.py" not in runner:
        runner = runner.replace("  'backend/test_build_contract.py',\n", "  'backend/test_build_contract.py',\n  'backend/test_rc2_feedback.py',\n")
    write(runner_path, runner)


def main() -> None:
    patch_profile_store()
    patch_local_world()
    patch_directory_host()
    patch_server_systems()
    patch_service()
    patch_renderer_app()
    patch_directory_web()
    patch_web_release_polish()
    patch_runtime_and_build_contract()
    write_colored_icons()
    write_rc2_renderer()
    patch_index_and_package()
    write_test()
    print("RC2 testing feedback patches applied")


if __name__ == "__main__":
    main()
