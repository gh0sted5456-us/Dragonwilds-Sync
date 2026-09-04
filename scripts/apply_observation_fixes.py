from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def replace_between(text: str, start: str, end: str, replacement: str, label: str) -> str:
    begin = text.find(start)
    if begin < 0:
        raise RuntimeError(f"{label}: start marker not found")
    finish = text.find(end, begin)
    if finish < 0:
        raise RuntimeError(f"{label}: end marker not found")
    if text.find(start, begin + len(start)) >= 0 and text.find(start, begin + len(start)) < finish:
        raise RuntimeError(f"{label}: duplicate start marker inside replacement range")
    return text[:begin] + replacement + text[finish:]


def patch_rsdw_cache() -> None:
    path = "backend/rsdw_cache.py"
    text = read(path)
    marker = "\n\ndef _catalog_rows() -> list[dict]:\n"
    helper = r'''

def _refresh_catalog_only(repo: str, branch: str) -> dict:
    """Refresh the small canonical item catalog without downloading RSDWTools wholesale.

    The full RSDWTools archive is useful for the embedded editors and icon cache,
    but item/search data must not disappear just because GitHub codeload is slow
    or blocked on one machine.  This fallback downloads one generated catalog
    file and lets the manifest operate in a clearly-reported degraded mode.
    """
    repo = str(repo or DEFAULT_REPO).strip() or DEFAULT_REPO  # type: ignore[name-defined]
    branch = str(branch or DEFAULT_BRANCH).strip() or DEFAULT_BRANCH  # type: ignore[name-defined]
    revision_error = ""
    try:
        revision = str(_legacy._latest_revision(repo, branch) or "").strip()
    except Exception as exc:
        revision = ""
        revision_error = str(exc)
    if not revision:
        revision = f"{repo}@{branch}"

    target = RSDW_WEBSITE_DIR / _CATALOG_REL  # type: ignore[name-defined]
    RSDW_CACHE_ROOT.mkdir(parents=True, exist_ok=True)  # type: ignore[name-defined]
    with tempfile.TemporaryDirectory(prefix="rsdw-catalog-", dir=str(RSDW_CACHE_ROOT)) as temp_name:  # type: ignore[name-defined]
        staged = Path(temp_name) / "catalog.json"
        url = f"https://raw.githubusercontent.com/{repo}/{branch}/website/{_CATALOG_REL.as_posix()}"
        _legacy._download(url, staged, timeout=45)
        value = json.loads(staged.read_text(encoding="utf-8-sig"))
        tabs = value.get("tabs") if isinstance(value, dict) else None
        if not isinstance(tabs, dict) or not any(
            isinstance(section, dict) and isinstance(section.get("items"), list) and section.get("items")
            for section in tabs.values()
        ):
            raise RuntimeError("RSDW lightweight catalog contained no item rows.")
        target.parent.mkdir(parents=True, exist_ok=True)
        pending = target.with_name(f".{target.name}.{os.getpid()}.next")
        shutil.copy2(staged, pending)
        os.replace(pending, target)
    return {
        "ok": True,
        "changed": True,
        "revision": revision,
        "fallback": "catalog-only",
        "catalog_url": url,
        "revision_error": revision_error,
    }
'''
    text = replace_once(text, marker, helper + marker, "RSDW lightweight catalog helper")

    status_block = r'''def status() -> dict:
    base = _legacy.status()
    manifest = item_manifest()
    raw_count = _json_count(RSDW_RAW_ITEMS_DIR)
    revision = str(base.get("revision") or "")
    manifest_revision = str(manifest.get("revision") or "")
    missing_raw = int(manifest.get("missing_raw_json_count") or 0)
    manifest_ready = bool(manifest.get("item_count") and (not revision or revision == manifest_revision))
    raw_complete = bool(raw_count and missing_raw == 0)
    legacy_valid = bool(base.get("valid"))
    toolkit_valid = bool(base.get("toolkit_valid"))
    return {
        **base,
        # Item/search data is a first-class cache capability.  A failed full
        # toolkit/icon download may degrade presentation, but it must not make
        # the canonical item catalog unavailable to the application.
        "valid": bool(legacy_valid or manifest_ready),
        "data_ready": manifest_ready,
        "degraded": bool(manifest_ready and not (legacy_valid and toolkit_valid and raw_complete)),
        "raw_items_dir": str(RSDW_RAW_ITEMS_DIR),
        "raw_item_file_count": raw_count,
        "raw_items_complete": raw_complete,
        "item_manifest": str(RSDW_ITEM_MANIFEST_PATH),
        "item_manifest_count": int(manifest.get("item_count") or 0),
        "item_manifest_revision": manifest_revision,
        "item_manifest_valid": manifest_ready,
        "item_manifest_missing_icons": int(manifest.get("missing_icon_count") or 0),
        "item_manifest_missing_raw": missing_raw,
    }


'''
    text = replace_between(text, "def status() -> dict:\n", "def refresh(*, force: bool = False", status_block, "RSDW status")

    refresh_block = r'''def refresh(*, force: bool = False, repo: str = DEFAULT_REPO, branch: str = DEFAULT_BRANCH) -> dict:  # type: ignore[name-defined]
    """Refresh canonical RSDW item data without making the full archive a prerequisite.

    The normal path downloads only ``catalog.json`` from raw.githubusercontent.com.
    If that lightweight route fails on a fresh install, the historical full
    RSDWTools archive remains a one-time fallback. Existing manifests are kept
    as last-known-good data instead of being invalidated by a network failure.
    """
    current = item_manifest()
    catalog_error = ""
    archive_fallback_error = ""
    changed = False
    revision = ""

    try:
        lightweight = _refresh_catalog_only(repo, branch)
        revision = str(lightweight.get("revision") or "")
        changed = bool(lightweight.get("changed"))
    except Exception as exc:
        catalog_error = str(exc)
        if current.get("item_count"):
            revision = str(current.get("revision") or "")
        else:
            try:
                legacy = _legacy.refresh(force=force, repo=repo, branch=branch)
                revision = str(legacy.get("revision") or "")
                changed = bool(legacy.get("changed"))
            except Exception as fallback_exc:
                archive_fallback_error = str(fallback_exc)
                raise RuntimeError(
                    f"RSDW catalog download failed ({catalog_error}); full archive fallback also failed ({archive_fallback_error})"
                ) from fallback_exc

    needs_manifest = bool(
        force
        or not current.get("item_count")
        or (revision and str(current.get("revision") or "") != revision)
    )
    manifest_error = ""
    if needs_manifest:
        try:
            _build_item_manifest(repo=repo, revision=revision)
            changed = True
        except Exception as exc:
            manifest_error = str(exc)
            if not current.get("item_count"):
                raise

    result = status()
    return {
        **result,
        "ok": bool(result.get("item_manifest_valid")),
        "changed": bool(changed),
        "catalog_error": catalog_error,
        "archive_fallback_error": archive_fallback_error,
        "item_manifest_error": manifest_error,
        "item_manifest_stale": bool(manifest_error or not result.get("item_manifest_valid")),
    }


'''
    text = replace_between(text, "def refresh(*, force: bool = False", "def refresh_modules(*, force: bool = False", refresh_block, "RSDW refresh")

    modules_start = text.find("def refresh_modules(*, force: bool = False")
    if modules_start < 0:
        raise RuntimeError("RSDW refresh_modules start marker not found")
    modules_block = r'''def refresh_modules(*, force: bool = False, repo: str = DEFAULT_REPO, branch: str = DEFAULT_BRANCH,
                    model_repo: str = DEFAULT_MODEL_REPO, model_branch: str = DEFAULT_MODEL_BRANCH) -> dict:  # type: ignore[name-defined]
    """Refresh item data first; make large Toolkit/Model downloads best-effort.

    Startup/background refreshes stay lightweight.  An explicit force refresh
    still attempts the full RSDWTools website/icon cache and RSDWModel, but a
    failure there no longer removes the canonical item/search dataset.
    """
    tools = refresh(force=force, repo=repo, branch=branch)
    toolkit_error = ""
    model_error = ""
    legacy_tools = _legacy.status()
    model = _legacy.status()

    if force:
        try:
            legacy_tools = _legacy.refresh(force=True, repo=repo, branch=branch)
            full_revision = str(legacy_tools.get("revision") or tools.get("item_manifest_revision") or "")
            if full_revision:
                _build_item_manifest(repo=repo, revision=full_revision)
        except Exception as exc:
            toolkit_error = str(exc)
        try:
            model = _legacy.refresh_model_index(force=True, repo=model_repo, branch=model_branch)
        except Exception as exc:
            model = _legacy.status()
            model_error = str(exc)

    combined = status()
    return {
        **combined,
        "ok": bool(combined.get("item_manifest_valid")),
        "changed": bool(tools.get("changed") or legacy_tools.get("changed") or model.get("changed")),
        "tools_changed": bool(tools.get("changed") or legacy_tools.get("changed")),
        "model_changed": bool(model.get("changed")),
        "toolkit_error": toolkit_error,
        "model_error": model_error,
        "item_manifest_error": tools.get("item_manifest_error", ""),
        "full_refresh_attempted": bool(force),
        "degraded": bool(combined.get("degraded") or toolkit_error or model_error),
    }
'''
    text = text[:modules_start] + modules_block
    write(path, text)


def patch_managed_updates() -> None:
    path = "backend/managed_updates.py"
    text = read(path)
    old = r'''def _is_runeschema_core_zip(path: Path) -> bool:
    with zipfile.ZipFile(path) as archive:
        rows = [name.replace("\\", "/").strip("/") for name in archive.namelist() if name.strip("/")]
    first = {row.split("/", 1)[0] for row in rows}
    if len(first) == 1:
        wrapper = next(iter(first))
        wrapped_rows = [row[len(wrapper) + 1:] for row in rows if row.startswith(f"{wrapper}/")]
        if wrapped_rows:
            rows = wrapped_rows
    lowered = {row.casefold() for row in rows}
    return (any(row == "mods" or row.startswith("mods/") for row in lowered)
            or (any(row == "config" or row.startswith("config/") for row in lowered)
                and any(row == "dlls" or row.startswith("dlls/") for row in lowered)
                and "enabled.txt" in lowered))
'''
    new = r'''def _is_runeschema_core_zip(path: Path) -> bool:
    """Recognize RuneSchema cores at any safe release-wrapper depth.

    Official/community archives commonly add a release folder and may then
    contain a ``RuneSchema/`` payload folder.  Core identity is the self-enabled
    runtime root itself (enabled.txt + dlls/main.dll + config/mods), not an exact
    archive depth.
    """
    with zipfile.ZipFile(path) as archive:
        rows = [name.replace("\\", "/").strip("/") for name in archive.namelist() if name.strip("/")]
    if any(not row or row.startswith("../") or "/../" in f"/{row}/" for row in rows):
        return False
    lowered = {row.casefold() for row in rows}
    for row in lowered:
        if row != "enabled.txt" and not row.endswith("/enabled.txt"):
            continue
        root = row[:-len("enabled.txt")].rstrip("/")
        prefix = f"{root}/" if root else ""
        has_main = f"{prefix}dlls/main.dll" in lowered
        has_config = any(item == f"{prefix}config" or item.startswith(f"{prefix}config/") for item in lowered)
        has_mods = any(item == f"{prefix}mods" or item.startswith(f"{prefix}mods/") for item in lowered)
        if has_main and (has_config or has_mods):
            return True
    return False
'''
    text = replace_once(text, old, new, "RuneSchema nested core validator")
    write(path, text)


def patch_server_systems() -> None:
    path = "backend/server_systems.py"
    text = read(path)
    text = replace_once(
        text,
        '        "imgui": (core / "imgui.ini").is_file(),\n',
        '',
        "UE4SS optional imgui status",
    )
    old = '''    normalized = _normalize_bundled_integration_contract(target_root)\n    canonical_settings = _apply_canonical_ue4ss_settings(target_root)\n    return {"ok": True, "files_written": len(written), "files": written,\n'''
    new = '''    normalized = _normalize_bundled_integration_contract(target_root)\n    canonical_settings = _apply_canonical_ue4ss_settings(target_root)\n    # imgui.ini is runtime-generated/optional upstream. Keep an editable blank\n    # convenience file, but never classify a valid UE4SS core as incomplete\n    # merely because a new upstream package did not ship it.\n    imgui_settings = target_root / "ue4ss" / "imgui.ini"\n    if not imgui_settings.is_file() and (target_root / "ue4ss" / "UE4SS.dll").is_file():\n        imgui_settings.parent.mkdir(parents=True, exist_ok=True)\n        imgui_settings.write_text("", encoding="utf-8")\n    return {"ok": True, "files_written": len(written), "files": written,\n'''
    text = replace_once(text, old, new, "UE4SS new-layout install finalization")
    write(path, text)


def patch_test_runner() -> None:
    path = "scripts/run_backend_tests.cjs"
    text = read(path)
    marker = "'backend/test_managed_updates.py','backend/test_runtime_reset_window_contract.py'"
    replacement = "'backend/test_managed_updates.py','backend/test_runtime_cache_compat.py','backend/test_runtime_reset_window_contract.py'"
    text = replace_once(text, marker, replacement, "runtime/cache regression registration")
    write(path, text)


def write_regression_test() -> None:
    path = ROOT / "backend/test_runtime_cache_compat.py"
    path.write_text(r'''from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path

import managed_updates
import rsdw_cache
import server_systems
import ue4ss_repository


def _bind_rsdw_root(root: Path) -> None:
    legacy = rsdw_cache._legacy
    shared = {
        "RSDW_CACHE_ROOT": root,
        "RSDW_DATA_DIR": root / "item_data",
        "RSDW_ICONS_DIR": root / "icons",
        "RSDW_WEBSITE_DIR": root / "website",
        "RSDW_STATE_PATH": root / "cache_state.json",
        "RSDW_ICON_MANIFEST_PATH": root / "icon-manifest.json",
        "RSDW_MODEL_DIR": root / "model",
        "RSDW_MODEL_INDEX": root / "model" / "avatar-index.json",
    }
    for module in (legacy, rsdw_cache):
        for name, value in shared.items():
            setattr(module, name, value)
    rsdw_cache.RSDW_RAW_ITEMS_DIR = root / "raw_items"
    rsdw_cache.RSDW_ITEM_MANIFEST_PATH = root / "item-manifest.json"
    rsdw_cache._ITEM_INDEX_CACHE = None


def test_rsdw_catalog_only_fallback_keeps_item_data_ready() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "rsdw"
        root.mkdir(parents=True)
        _bind_rsdw_root(root)
        legacy = rsdw_cache._legacy
        old_revision = legacy._latest_revision
        old_download = legacy._download
        seen = []
        try:
            legacy._latest_revision = lambda *_args, **_kwargs: "rev-catalog-only"

            def fake_download(url, target, timeout=90):
                seen.append(str(url))
                if "catalog.json" not in str(url):
                    raise AssertionError(f"unexpected heavyweight RSDW download: {url}")
                target = Path(target)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps({
                    "tabs": {"bag": {"items": [{
                        "name": "Test Item",
                        "itemData": "pid-test",
                        "maxStack": 12,
                        "weight": 1.5,
                        "sourcePath": "data/items/json/RSDragonwilds/Test/ITEM_Test.json",
                        "category": "Resources/Test",
                    }]}}
                }), encoding="utf-8")

            legacy._download = fake_download
            result = rsdw_cache.refresh(force=False)
            assert result["ok"] is True, result
            assert result["data_ready"] is True
            assert result["degraded"] is True
            assert result["item_manifest_count"] == 1
            assert result["raw_items_complete"] is False
            assert rsdw_cache.search_items("Test Item", 10)["count"] == 1
            assert seen and all("codeload.github.com" not in url for url in seen), seen
        finally:
            legacy._latest_revision = old_revision
            legacy._download = old_download


def test_current_ue4ss_layout_is_complete_without_packaged_imgui() -> None:
    old_defender = server_systems.review_with_defender
    try:
        server_systems.review_with_defender = lambda *_args, **_kwargs: None
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive = root / "UE4SS-current.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("dwmapi.dll", b"proxy")
                zf.writestr("ue4ss/UE4SS.dll", b"core")
                zf.writestr("ue4ss/UE4SS-settings.ini", "[Settings]\n")
            names = ue4ss_repository._validate_ue4ss_zip(archive)
            assert any(name.casefold().endswith("ue4ss/ue4ss.dll") for name in names)

            game = root / "RSDragonwilds"
            (game / "Content" / "Paks").mkdir(parents=True)
            server_systems.install_client_ue4ss_zip(str(archive), str(game))
            status = server_systems.client_runtime_status(str(game))
            assert status["ue4ss"]["installed"] is True, status
            assert (game / "Binaries" / "Win64" / "ue4ss" / "imgui.ini").is_file()
            assert not (game / "Binaries" / "Win64" / "version.dll").exists()
    finally:
        server_systems.review_with_defender = old_defender


def test_nested_runeschema_release_wrapper_is_a_core() -> None:
    with tempfile.TemporaryDirectory() as td:
        archive = Path(td) / "RuneSchema.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("RuneSchema-0.6.0/RuneSchema/enabled.txt", "")
            zf.writestr("RuneSchema-0.6.0/RuneSchema/dlls/main.dll", b"core")
            zf.writestr("RuneSchema-0.6.0/RuneSchema/config/config.json", "{}")
        assert managed_updates._is_runeschema_core_zip(archive) is True


def main() -> None:
    test_rsdw_catalog_only_fallback_keeps_item_data_ready()
    test_current_ue4ss_layout_is_complete_without_packaged_imgui()
    test_nested_runeschema_release_wrapper_is_a_core()
    print("RSDW degraded cache + current UE4SS/RuneSchema package compatibility: PASS")


if __name__ == "__main__":
    main()
''', encoding="utf-8")


def main() -> None:
    patch_rsdw_cache()
    patch_managed_updates()
    patch_server_systems()
    patch_test_runner()
    write_regression_test()
    print("Applied guarded RSDW/runtime observation fixes.")


if __name__ == "__main__":
    main()
