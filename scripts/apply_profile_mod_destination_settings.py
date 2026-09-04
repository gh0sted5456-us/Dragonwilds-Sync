from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(path: str, old: str, new: str, label: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    write(path, text.replace(old, new, 1))


def patch_function(path: str, name: str, transform) -> None:
    text = read(path)
    match = re.search(rf"^def {re.escape(name)}\(.*?(?=^def |\Z)", text, flags=re.M | re.S)
    if not match:
        raise RuntimeError(f"{path}: function {name} not found")
    old = match.group(0)
    new = transform(old)
    if old == new:
        raise RuntimeError(f"{path}: function {name} produced no change")
    write(path, text[:match.start()] + new + text[match.end():])


def create_destination_module() -> None:
    path = ROOT / "backend" / "profile_mod_destinations.py"
    path.write_text('''from __future__ import annotations

from pathlib import Path

from client_layout import resolve_client_layout
from server_layout import resolve_server_layout

LANES = ("ue4ss", "runeschema", "paks")
ROLES = ("player", "server")


def _application(state: dict) -> dict:
    return state.setdefault("application", {})


def _configured(state: dict, role: str) -> dict:
    if role not in ROLES:
        raise ValueError("Mod destination role must be player or server.")
    root = _application(state).setdefault("mod_install_paths", {})
    value = root.setdefault(role, {})
    return value if isinstance(value, dict) else {}


def _layout(state: dict, role: str, selected_root: str | Path | None = None):
    application = _application(state)
    if role == "player":
        selected = str(selected_root or application.get("game_dir") or "").strip()
        if not selected:
            raise ValueError("Set the Player Dragonwilds game directory before configuring mod destinations.")
        return resolve_client_layout(selected)
    selected = str(selected_root or ((application.get("server_install") or {}).get("install_dir")) or "").strip()
    if not selected:
        raise ValueError("Set the Dedicated Server directory before configuring mod destinations.")
    return resolve_server_layout(selected)


def default_mod_install_paths(state: dict, role: str, selected_root: str | Path | None = None) -> dict[str, Path]:
    layout = _layout(state, role, selected_root)
    return {
        "ue4ss": layout.ue4ss_mods_dir.resolve(strict=False),
        "runeschema": layout.runeschema_mods_dir.resolve(strict=False),
        "paks": layout.paks_mods_dir.resolve(strict=False),
    }


def _safe_destination(game_root: Path, value: object, fallback: Path, lane: str) -> Path:
    raw = str(value or "").strip()
    candidate = Path(raw).expanduser().resolve(strict=False) if raw else fallback.resolve(strict=False)
    game = game_root.resolve(strict=False)
    # Deployment clears stale profile-owned children from these folders. Never
    # permit the game root itself or a path outside it to become a clear target.
    if candidate == game or game not in candidate.parents:
        raise ValueError(f"{lane} mod destination must be a folder inside the verified game directory: {game}")
    return candidate


def resolve_mod_install_paths(state: dict, role: str, selected_root: str | Path | None = None) -> dict[str, Path]:
    layout = _layout(state, role, selected_root)
    defaults = default_mod_install_paths(state, role, selected_root)
    configured = _configured(state, role)
    return {
        lane: _safe_destination(layout.game_root, configured.get(lane), defaults[lane], lane)
        for lane in LANES
    }


def mod_destination_status(state: dict) -> dict:
    result = {}
    for role in ROLES:
        configured = dict(_configured(state, role))
        try:
            defaults = default_mod_install_paths(state, role)
            resolved = resolve_mod_install_paths(state, role)
            layout = _layout(state, role)
            result[role] = {
                "ready": True,
                "installation": str(layout.game_root),
                "paths": {lane: str(resolved[lane]) for lane in LANES},
                "defaults": {lane: str(defaults[lane]) for lane in LANES},
                "overrides": {lane: str(configured.get(lane) or "") for lane in LANES},
            }
        except Exception as exc:
            result[role] = {
                "ready": False,
                "installation": "",
                "paths": {lane: str(configured.get(lane) or "") for lane in LANES},
                "defaults": {lane: "" for lane in LANES},
                "overrides": {lane: str(configured.get(lane) or "") for lane in LANES},
                "error": str(exc),
            }
    return result


def save_mod_install_paths(state: dict, role: str, paths: dict | None = None, *, reset: bool = False) -> dict:
    configured = _configured(state, role)
    if reset:
        configured.clear()
    else:
        values = paths if isinstance(paths, dict) else {}
        defaults = default_mod_install_paths(state, role)
        layout = _layout(state, role)
        normalized = {}
        for lane in LANES:
            value = str(values.get(lane) or "").strip()
            if not value:
                continue
            target = _safe_destination(layout.game_root, value, defaults[lane], lane)
            # Persist only real overrides. Selecting the canonical destination
            # remains dynamic when the installation root later changes.
            if target != defaults[lane]:
                normalized[lane] = str(target)
        configured.clear()
        configured.update(normalized)
    return mod_destination_status(state)[role]
''', encoding="utf-8")


def patch_profile_store() -> None:
    replace_once(
        "backend/profile_store.py",
        '            "game_exe": "",\n            "keep_core_persistent": False,\n',
        '            "game_exe": "",\n            "mod_install_paths": {"player": {}, "server": {}},\n            "keep_core_persistent": False,\n',
        "default machine mod destinations",
    )


def patch_service() -> None:
    replace_once(
        "backend/dragonwilds_service.py",
        "from client_layout import resolve_client_layout\n",
        "from client_layout import resolve_client_layout\nfrom profile_mod_destinations import mod_destination_status, save_mod_install_paths\n",
        "service mod destination import",
    )
    replace_once(
        "backend/dragonwilds_service.py",
        '''    if method == "application.process_catalog":\n        return process_catalog()\n''',
        '''    if method == "application.mod_destinations.get":\n        return mod_destination_status(state)\n    if method == "application.mod_destinations.save":\n        role = str(params.get("role") or "").strip().casefold()\n        result = save_mod_install_paths(state, role, params.get("paths"), reset=bool(params.get("reset")))\n        _legacy.save_state(state)\n        return {"role": role, "destination": result, "state": _legacy.public_state(state)}\n\n    if method == "application.process_catalog":\n        return process_catalog()\n''',
        "service mod destination RPC",
    )


def patch_local_world() -> None:
    replace_once(
        "backend/local_world.py",
        "from profile_store import APP_DATA_DIR, read_json, write_json\n",
        "from profile_store import APP_DATA_DIR, load_state, read_json, write_json\nfrom profile_mod_destinations import resolve_mod_install_paths\n",
        "local world destination imports",
    )

    def transform(block: str) -> str:
        match = re.match(r"def _live_roots\((.*?)\).*?:\n", block, flags=re.S)
        if not match:
            raise RuntimeError("Could not parse _live_roots signature")
        signature = match.group(1)
        # Retain the existing parameter name by extracting the first identifier.
        selected = signature.split(":", 1)[0].split("=", 1)[0].strip() or "install_dir"
        return f'''def _live_roots({signature}):\n    roots = resolve_mod_install_paths(load_state(), "player", {selected})\n    return {{"ue4ss": roots["ue4ss"], "paks": roots["paks"], "runeschema": roots["runeschema"]}}\n\n\n'''
    patch_function("backend/local_world.py", "_live_roots", transform)


def patch_sync_engine() -> None:
    replace_once(
        "backend/sync_engine.py",
        "from profile_store import APP_DATA_DIR\n",
        "from profile_store import APP_DATA_DIR, load_state\nfrom profile_mod_destinations import resolve_mod_install_paths\n",
        "sync engine destination imports",
    )

    def client_roots(_block: str) -> str:
        return '''def _client_mod_roots(selected: Path) -> dict[str, Path]:\n    roots = resolve_mod_install_paths(load_state(), "player", selected)\n    return {"ue4ss_mods": roots["ue4ss"], "pak_mods": roots["paks"], "runeschema_mods": roots["runeschema"]}\n\n\n'''
    patch_function("backend/sync_engine.py", "_client_mod_roots", client_roots)

    for name in ("snapshot_client_world", "snapshot_client_mod_unit", "restore_client_world"):
        def transform(block: str, name=name) -> str:
            if "layout = resolve_client_layout(selected_root)" in block and "profile_live = _client_mod_roots(selected_root)" not in block:
                block = block.replace(
                    "layout = resolve_client_layout(selected_root)",
                    "layout = resolve_client_layout(selected_root)\n    profile_live = _client_mod_roots(selected_root)",
                    1,
                )
            block = block.replace("layout.ue4ss_mods_dir", 'profile_live["ue4ss_mods"]')
            block = block.replace("layout.runeschema_mods_dir", 'profile_live["runeschema_mods"]')
            block = block.replace("layout.paks_mods_dir", 'profile_live["pak_mods"]')
            return block
        patch_function("backend/sync_engine.py", name, transform)


def patch_server_engine() -> None:
    replace_once(
        "backend/server_engine.py",
        "from profile_mod_layout import ensure_profile_mod_roots\n",
        "from profile_mod_layout import ensure_profile_mod_roots\nfrom profile_mod_destinations import resolve_mod_install_paths\n",
        "server engine destination import",
    )
    for name in ("snapshot_profile_mods", "snapshot_profile_mod_unit", "restore_profile_mods"):
        def transform(block: str, name=name) -> str:
            anchor = "layout = resolve_server_layout(game_root)"
            if anchor in block and "live_roots = resolve_mod_install_paths" not in block:
                block = block.replace(anchor, anchor + '\n    live_roots = resolve_mod_install_paths(load_state(), "server", game_root)', 1)
            block = block.replace("layout.ue4ss_mods_dir", 'live_roots["ue4ss"]')
            block = block.replace("layout.runeschema_mods_dir", 'live_roots["runeschema"]')
            block = block.replace("layout.paks_mods_dir", 'live_roots["paks"]')
            return block
        patch_function("backend/server_engine.py", name, transform)


def patch_renderer() -> None:
    path = "renderer/release-profile-mod-folders.js"
    text = read(path)
    insertion = r'''
  const destinationRole = (kind) => kind === 'server' ? 'server' : 'player';

  async function browseDestination(kind, lane, input) {
    const picked = await bridge.pickDirectory?.();
    if (picked) input.value = String(picked);
  }

  async function loadDestinationEditor(kind, panel) {
    try {
      const result = await bridge.invoke('application.mod_destinations.get', {});
      const role = destinationRole(kind);
      const status = result?.[role] || {};
      panel.querySelector('[data-mod-destination-installation]').textContent = status.installation
        ? `Installation: ${status.installation}`
        : (status.error || 'Configure the installation directory first.');
      for (const lane of ['ue4ss', 'runeschema', 'paks']) {
        const input = panel.querySelector(`[data-mod-destination="${lane}"]`);
        if (input) input.value = String(status.paths?.[lane] || status.overrides?.[lane] || '');
        if (input) input.placeholder = String(status.defaults?.[lane] || '');
      }
    } catch (error) {
      panel.querySelector('[data-mod-destination-installation]').textContent = text(error?.message || error || 'Could not load destinations.');
    }
  }

  function ensureDestinationEditor(kind) {
    const note = noteFor(kind);
    if (!note || note.parentElement?.querySelector(`[data-mod-destinations="${kind}"]`)) return;
    const panel = document.createElement('div');
    panel.className = 'identity-box';
    panel.dataset.modDestinations = kind;
    panel.innerHTML = `
      <strong>${kind === 'server' ? 'Server' : 'Player'} mod install destinations</strong>
      <p data-mod-destination-installation>Loading installation paths…</p>
      <small>Machine-level deployment targets. Profile Mods remain the source of truth.</small>
      ${[
        ['ue4ss', 'UE4SS Mods'],
        ['runeschema', 'RuneSchema Mods'],
        ['paks', 'PAKs'],
      ].map(([lane, label]) => `
        <label class="field" style="display:block;margin-top:10px">
          <span>${label}</span>
          <div style="display:flex;gap:8px;align-items:center">
            <input data-mod-destination="${lane}" type="text" spellcheck="false" style="flex:1;min-width:0" />
            <button type="button" class="button secondary" data-mod-destination-browse="${lane}">Browse</button>
          </div>
        </label>`).join('')}
      <div class="button-row" style="margin-top:10px">
        <button type="button" class="button primary" data-mod-destination-save>Save destinations</button>
        <button type="button" class="button secondary" data-mod-destination-reset>Use detected defaults</button>
      </div>`;
    note.insertAdjacentElement('afterend', panel);

    panel.querySelectorAll('[data-mod-destination-browse]').forEach((button) => {
      button.addEventListener('click', () => {
        const lane = button.dataset.modDestinationBrowse;
        const input = panel.querySelector(`[data-mod-destination="${lane}"]`);
        if (input) browseDestination(kind, lane, input).catch(() => {});
      });
    });
    panel.querySelector('[data-mod-destination-save]')?.addEventListener('click', async () => {
      const button = panel.querySelector('[data-mod-destination-save]');
      button.disabled = true;
      try {
        const paths = Object.fromEntries(['ue4ss', 'runeschema', 'paks'].map((lane) => [
          lane, text(panel.querySelector(`[data-mod-destination="${lane}"]`)?.value),
        ]));
        await bridge.invoke('application.mod_destinations.save', { role: destinationRole(kind), paths });
        await loadDestinationEditor(kind, panel);
        updateNote(kind, 'Mod install destinations saved. Refresh or activate the profile to materialize it there.', 'success');
      } catch (error) {
        updateNote(kind, text(error?.message || error || 'Could not save mod destinations.'), 'error');
      } finally { button.disabled = false; }
    });
    panel.querySelector('[data-mod-destination-reset]')?.addEventListener('click', async () => {
      const button = panel.querySelector('[data-mod-destination-reset]');
      button.disabled = true;
      try {
        await bridge.invoke('application.mod_destinations.save', { role: destinationRole(kind), reset: true });
        await loadDestinationEditor(kind, panel);
        updateNote(kind, 'Detected default mod destinations restored.', 'success');
      } catch (error) {
        updateNote(kind, text(error?.message || error || 'Could not reset mod destinations.'), 'error');
      } finally { button.disabled = false; }
    });
    loadDestinationEditor(kind, panel);
  }
'''
    marker = "  function rewriteUi() {\n"
    if marker not in text:
        raise RuntimeError("renderer rewriteUi marker missing")
    text = text.replace(marker, insertion + "\n" + marker, 1)
    text = text.replace(
        "    bindProfileFolderButton('#server-open-mods-folder', 'server');\n",
        "    bindProfileFolderButton('#server-open-mods-folder', 'server');\n    ensureDestinationEditor('local');\n    ensureDestinationEditor('server');\n",
        1,
    )
    write(path, text)


def create_tests() -> None:
    path = ROOT / "backend" / "test_profile_mod_destination_settings.py"
    path.write_text('''from pathlib import Path
from tempfile import TemporaryDirectory

import profile_mod_destinations as destinations


def _seed_client(root: Path) -> Path:
    game = root / "client" / "RuneScape Dragonwilds"
    (game / "Binaries" / "Win64" / "ue4ss" / "Mods" / "RuneSchema" / "mods").mkdir(parents=True)
    (game / "Content" / "Paks" / "~mods").mkdir(parents=True)
    (game / "RSDragonwilds.exe").write_bytes(b"exe")
    return game


def _seed_server(root: Path) -> Path:
    game = root / "server" / "RSDragonwilds"
    (game / "Binaries" / "Win64" / "ue4ss" / "Mods" / "RuneSchema" / "mods").mkdir(parents=True)
    (game / "Content" / "Paks" / "~mods").mkdir(parents=True)
    (game / "RSDragonwilds.exe").write_bytes(b"exe")
    return game


def main() -> None:
    with TemporaryDirectory() as td:
        root = Path(td)
        client = _seed_client(root)
        server = _seed_server(root)
        state = {
            "application": {
                "game_dir": str(client),
                "server_install": {"install_dir": str(server)},
                "mod_install_paths": {"player": {}, "server": {}},
            }
        }
        player_defaults = destinations.resolve_mod_install_paths(state, "player")
        server_defaults = destinations.resolve_mod_install_paths(state, "server")
        assert player_defaults["ue4ss"].name == "Mods"
        assert player_defaults["runeschema"].name.casefold() == "mods"
        assert player_defaults["paks"].name.casefold() == "~mods"
        assert server_defaults["ue4ss"].name == "Mods"

        custom = client / "Custom" / "UE4SS-Mods"
        saved = destinations.save_mod_install_paths(state, "player", {"ue4ss": str(custom)})
        assert saved["paths"]["ue4ss"] == str(custom.resolve())
        assert state["application"]["mod_install_paths"]["player"]["ue4ss"] == str(custom.resolve())
        assert saved["paths"]["paks"] == str(player_defaults["paks"])

        destinations.save_mod_install_paths(state, "player", reset=True)
        assert state["application"]["mod_install_paths"]["player"] == {}
        assert destinations.resolve_mod_install_paths(state, "player")["ue4ss"] == player_defaults["ue4ss"]

        try:
            destinations.save_mod_install_paths(state, "server", {"paks": str(root / "outside")})
        except ValueError as error:
            assert "verified game directory" in str(error)
        else:
            raise AssertionError("Outside-game mod destination was accepted")

        try:
            destinations.save_mod_install_paths(state, "server", {"paks": str(server)})
        except ValueError:
            pass
        else:
            raise AssertionError("Game root itself was accepted as a destructive destination")

    source_root = Path(__file__).resolve().parents[1]
    renderer = (source_root / "renderer" / "release-profile-mod-folders.js").read_text(encoding="utf-8")
    server_engine = (source_root / "backend" / "server_engine.py").read_text(encoding="utf-8")
    sync_engine = (source_root / "backend" / "sync_engine.py").read_text(encoding="utf-8")
    service = (source_root / "backend" / "dragonwilds_service.py").read_text(encoding="utf-8")
    assert "application.mod_destinations.get" in renderer and "application.mod_destinations.save" in renderer
    assert "Player mod install destinations" in renderer and "Server mod install destinations" in renderer
    assert 'resolve_mod_install_paths(load_state(), "server", game_root)' in server_engine
    assert 'resolve_mod_install_paths(load_state(), "player", selected)' in sync_engine
    assert 'method == "application.mod_destinations.save"' in service
    print("machine-level Player/Server mod destination settings: PASS")


if __name__ == "__main__":
    main()
''', encoding="utf-8")


def main() -> None:
    create_destination_module()
    patch_profile_store()
    patch_service()
    patch_local_world()
    patch_sync_engine()
    patch_server_engine()
    patch_renderer()
    create_tests()
    print("Machine-level mod destination settings staged successfully.")


if __name__ == "__main__":
    main()
