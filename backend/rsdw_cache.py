from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from profile_store import APP_DATA_DIR

RSDW_CACHE_ROOT = APP_DATA_DIR / "rsdw_cache"
RSDW_DATA_DIR = RSDW_CACHE_ROOT / "item_data"
RSDW_ICONS_DIR = RSDW_CACHE_ROOT / "icons"
RSDW_WEBSITE_DIR = RSDW_CACHE_ROOT / "website"
RSDW_STATE_PATH = RSDW_CACHE_ROOT / "cache_state.json"
RSDW_ICON_MANIFEST_PATH = RSDW_CACHE_ROOT / "icon-manifest.json"
RSDW_MODEL_DIR = RSDW_CACHE_ROOT / "model"
RSDW_MODEL_INDEX = RSDW_MODEL_DIR / "avatar-index.json"
DEFAULT_REPO = "RSDWArchive/RSDWTools"
DEFAULT_BRANCH = "main"
DEFAULT_MODEL_REPO = "RSDWArchive/RSDWModel"
DEFAULT_MODEL_BRANCH = "main"
_LOCK = threading.RLock()


def _read_state() -> dict:
    try:
        value = json.loads(RSDW_STATE_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _json_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.json") if p.is_file()] if root.exists() else []


def _icon_files(root: Path) -> list[Path]:
    allowed = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
    return [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in allowed] if root.exists() else []


def _replace_icon_manifest(root: Path, *, repo: str, revision: str) -> dict:
    """Atomically replace the upstream icon index while custom bindings remain separate."""
    records = []
    for path in sorted(_icon_files(root), key=lambda item: item.as_posix().casefold()):
        payload = path.read_bytes()
        records.append({"path": path.relative_to(root).as_posix(), "bytes": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest()})
    manifest = {
        "schema": "DragonwildsSync.RSDWIconManifest.v1", "source": repo,
        "revision": revision, "generated_at": time.time(), "icon_count": len(records),
        "icons": records, "custom_icon_policy": "preserved-in-custom-item-records",
    }
    RSDW_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="icon-manifest.", suffix=".tmp", dir=str(RSDW_CACHE_ROOT))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)
            handle.flush()
            try: os.fsync(handle.fileno())
            except OSError: pass
        os.replace(tmp_name, RSDW_ICON_MANIFEST_PATH)
    finally:
        try: Path(tmp_name).unlink(missing_ok=True)
        except OSError: pass
    return manifest


def icon_manifest() -> dict:
    try:
        value = json.loads(RSDW_ICON_MANIFEST_PATH.read_text(encoding="utf-8"))
        if isinstance(value, dict) and isinstance(value.get("icons"), list):
            return value
    except Exception:
        pass
    return {"schema": "DragonwildsSync.RSDWIconManifest.v1", "icon_count": 0, "icons": []}


def _character_catalog_summary(root: Path) -> dict:
    path = root / "tools" / "character-editor" / "data" / "character_catalog.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        value = {}
    counts = {
        key: len(value.get(key) or []) if isinstance(value.get(key), list) else 0
        for key in ("BodyType", "Head", "HairPreset", "FacialHairPreset", "SkinTone", "HairColor", "EyeColor", "EyebrowColor")
    }
    return {"path": str(path), "valid": all(counts[key] > 0 for key in counts), "counts": counts}


def validate_cache() -> dict:
    data_files = _json_files(RSDW_DATA_DIR)
    icon_files = _icon_files(RSDW_ICONS_DIR)
    required_tools = (
        "character-editor", "item-editor", "spell-editor", "recipe-unlocker", "quest-editor",
    )
    character_catalog = _character_catalog_summary(RSDW_WEBSITE_DIR)
    toolkit_valid = bool(
        (RSDW_WEBSITE_DIR / "index.html").is_file()
        and all((RSDW_WEBSITE_DIR / "tools" / name / "index.html").is_file() for name in required_tools)
        and character_catalog["valid"]
    )
    model_valid = False
    model_dataset = ""
    try:
        model = json.loads(RSDW_MODEL_INDEX.read_text(encoding="utf-8-sig"))
        slots = model.get("slots") if isinstance(model, dict) else None
        model_valid = bool(
            model.get("schema") == "RSDWModel.WebsiteAvatarIndex.v1"
            and isinstance(slots, dict) and slots.get("baseBody") and slots.get("baseHead")
            and (RSDW_MODEL_DIR / "Avatar" / "index.html").is_file()
            and (RSDW_MODEL_DIR / "Avatar" / "avatar.js").is_file()
            and (RSDW_MODEL_DIR / "Avatar" / "avatar.css").is_file()
        )
        model_dataset = str(model.get("datasetVersion") or "")
    except Exception:
        pass
    valid = bool(data_files and icon_files)
    return {
        "valid": valid,
        "toolkit_valid": toolkit_valid,
        "character_catalog_valid": character_catalog["valid"],
        "character_catalog_counts": character_catalog["counts"],
        "model_valid": model_valid,
        "model_dataset": model_dataset,
        "model_index": str(RSDW_MODEL_INDEX),
        "data_file_count": len(data_files),
        "icon_count": len(icon_files),
        "data_dir": str(RSDW_DATA_DIR),
        "icons_dir": str(RSDW_ICONS_DIR),
        "icon_manifest": str(RSDW_ICON_MANIFEST_PATH),
        "icon_manifest_count": int(icon_manifest().get("icon_count") or 0),
        "website_dir": str(RSDW_WEBSITE_DIR),
    }


def status() -> dict:
    meta = _read_state()
    result = {**validate_cache(), **meta}
    result.setdefault("repo", DEFAULT_REPO)
    result.setdefault("branch", DEFAULT_BRANCH)
    result.setdefault("model_repo", DEFAULT_MODEL_REPO)
    result.setdefault("model_branch", DEFAULT_MODEL_BRANCH)
    return result


_AVATAR_PALETTE_FALLBACK = {
    "skin": [
        {"id": item[0], "label": item[1], "hex": item[2]}
        for item in [
            ("skinOriginal", "Original", "#D8A58E"), ("skin01", "Skin 1", "#E1DCD3"), ("skin02", "Skin 2", "#DEDBD0"),
            ("skin03", "Skin 3", "#CBB37B"), ("skin04", "Skin 4", "#C5A873"), ("skin05", "Skin 5", "#C0A26D"),
            ("skin06", "Skin 6", "#C09868"), ("skin07", "Skin 7", "#B28860"), ("skin08", "Skin 8", "#AA7D5D"),
            ("skin09", "Skin 9", "#9C7154"), ("skin10", "Skin 10", "#8C6344"), ("skin11", "Skin 11", "#73492E"),
            ("skin12", "Skin 12", "#653A1E"), ("skin13", "Skin 13", "#5D2E15"), ("skin14", "Skin 14", "#522A15"),
            ("skin15", "Skin 15", "#442918"), ("skin16", "Skin 16", "#39251B"),
        ]
    ],
    "hair": [{"id": f"hair{i:02d}", "label": f"Hair {i}", "hex": color} for i, color in enumerate(
        ["#F1DAD0", "#976B4C", "#965F3B", "#614D3A", "#5A3118", "#BA2F1C", "#191613", "#181714", "#070605"], 1)],
    "eyes": [{"id": f"eye{i:02d}", "label": f"Eye {i}", "hex": color} for i, color in enumerate(
        ["#66FF04", "#1651D9", "#82603E", "#FCF1EF", "#E04903", "#58EDF9", "#C42B02", "#2A2A2A"], 1)],
}


def avatar_palette() -> dict:
    """Return the current RSDWModel appearance colors without baking them into the app."""
    try:
        value = json.loads(RSDW_MODEL_INDEX.read_text(encoding="utf-8-sig"))
        colors = value.get("colors") if isinstance(value, dict) else None
        if not isinstance(colors, dict):
            return {}
        result: dict[str, list[dict]] = {}
        for role in ("skin", "hair", "eyes"):
            rows = colors.get(role)
            if not isinstance(rows, list):
                continue
            result[role] = [
                {
                    "id": str(row.get("id") or "")[:64],
                    "label": str(row.get("label") or row.get("id") or "")[:80],
                    "hex": str(row.get("hex") or "")[:16],
                }
                for row in rows
                if isinstance(row, dict) and row.get("id")
            ]
        return {role: result.get(role) or [dict(row) for row in rows] for role, rows in _AVATAR_PALETTE_FALLBACK.items()}
    except Exception:
        return {role: [dict(row) for row in rows] for role, rows in _AVATAR_PALETTE_FALLBACK.items()}


def _request_json(url: str, timeout: int = 20) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "DragonwildsSync/Alpha12", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _download(url: str, target: Path, timeout: int = 90) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "DragonwildsSync/Alpha12"})
    with urllib.request.urlopen(request, timeout=timeout) as response, target.open("wb") as output:
        shutil.copyfileobj(response, output)


def _latest_revision(repo: str, branch: str) -> str:
    data = _request_json(f"https://api.github.com/repos/{repo}/commits/{branch}")
    return str(data.get("sha") or "").strip()


def _atomic_swap_dir(staged: Path, live: Path) -> None:
    live.parent.mkdir(parents=True, exist_ok=True)
    backup = live.with_name(live.name + ".previous")
    shutil.rmtree(backup, ignore_errors=True)
    if live.exists():
        os.replace(live, backup)
    try:
        os.replace(staged, live)
    except Exception:
        if backup.exists() and not live.exists():
            os.replace(backup, live)
        raise
    shutil.rmtree(backup, ignore_errors=True)


def refresh(*, force: bool = False, repo: str = DEFAULT_REPO, branch: str = DEFAULT_BRANCH) -> dict:
    """Refresh the local RSDW item data/icon cache once, atomically.

    Both launcher-update and dedicated-server-update paths call this same routine.
    It is intentionally idempotent and preserves the previous cache until the new
    data and icon directories have validated.
    """
    repo = str(repo or DEFAULT_REPO).strip() or DEFAULT_REPO
    branch = str(branch or DEFAULT_BRANCH).strip() or DEFAULT_BRANCH
    with _LOCK:
        before = status()
        revision = _latest_revision(repo, branch)
        if not revision:
            raise RuntimeError("RSDW upstream revision could not be determined.")
        if not force and before.get("valid") and before.get("toolkit_valid") and str(before.get("revision") or "") == revision:
            return {**before, "ok": True, "changed": False, "checked_at": time.time()}

        RSDW_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="rsdw-refresh-", dir=str(RSDW_CACHE_ROOT)) as temp_name:
            temp = Path(temp_name)
            archive_path = temp / "rsdw.zip"
            _download(f"https://codeload.github.com/{repo}/zip/refs/heads/{branch}", archive_path)
            extract = temp / "extract"
            extract.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(archive_path) as zf:
                # Never trust archive member paths, even when the current source is
                # an upstream GitHub archive. Reject absolute paths and traversal so
                # a compromised/malformed archive cannot write outside the staging
                # directory before validation and atomic promotion.
                extract_root = extract.resolve()
                for member in zf.infolist():
                    member_path = (extract / member.filename).resolve()
                    if member_path != extract_root and extract_root not in member_path.parents:
                        raise RuntimeError(f"Unsafe path in RSDW archive: {member.filename}")
                zf.extractall(extract)
            roots = [p for p in extract.iterdir() if p.is_dir()]
            if not roots:
                raise RuntimeError("RSDW archive contained no repository root.")
            repo_root = roots[0]
            source_website = repo_root / "website"
            source_data = source_website / "tools" / "item-editor" / "data"
            source_icons = source_website / "shared" / "icons"
            if not _json_files(source_data):
                raise RuntimeError("RSDW item manifest/data directory was missing or empty.")
            if not _icon_files(source_icons):
                raise RuntimeError("RSDW icon directory was missing or empty.")
            required_tools = ("character-editor", "item-editor", "spell-editor", "recipe-unlocker", "quest-editor")
            if not (source_website / "index.html").is_file() or not all((source_website / "tools" / name / "index.html").is_file() for name in required_tools):
                raise RuntimeError("RSDW Toolkit website/editor sources were incomplete in the upstream archive.")
            character_catalog = _character_catalog_summary(source_website)
            if not character_catalog["valid"]:
                raise RuntimeError("RSDW Toolkit character catalog was missing required appearance lists, including hairstyles and facial hair.")

            staged_data = RSDW_CACHE_ROOT / ".item_data.next"
            staged_icons = RSDW_CACHE_ROOT / ".icons.next"
            staged_website = RSDW_CACHE_ROOT / ".website.next"
            shutil.rmtree(staged_data, ignore_errors=True)
            shutil.rmtree(staged_icons, ignore_errors=True)
            shutil.rmtree(staged_website, ignore_errors=True)
            shutil.copytree(source_data, staged_data)
            shutil.copytree(source_icons, staged_icons)
            # Cache the upstream static website too. Dragonwilds Sync exposes it only
            # through Dragonwilds Sync's loopback-only local HTTP server; it is never a public web host.
            shutil.copytree(source_website, staged_website)
            if not _json_files(staged_data) or not _icon_files(staged_icons):
                raise RuntimeError("RSDW staged cache failed validation.")
            if not all((staged_website / "tools" / name / "index.html").is_file() for name in required_tools):
                raise RuntimeError("RSDW staged Toolkit website failed validation.")
            _atomic_swap_dir(staged_data, RSDW_DATA_DIR)
            _atomic_swap_dir(staged_icons, RSDW_ICONS_DIR)
            _atomic_swap_dir(staged_website, RSDW_WEBSITE_DIR)

        _replace_icon_manifest(RSDW_ICONS_DIR, repo=repo, revision=revision)

        meta = {
            "repo": repo,
            "branch": branch,
            "revision": revision,
            "refreshed_at": time.time(),
            "checked_at": time.time(),
        }
        fd, tmp_name = tempfile.mkstemp(prefix="cache_state.", suffix=".tmp", dir=str(RSDW_CACHE_ROOT))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(meta, handle, indent=2)
                handle.flush()
                try: os.fsync(handle.fileno())
                except OSError: pass
            os.replace(tmp_name, RSDW_STATE_PATH)
        finally:
            try: Path(tmp_name).unlink(missing_ok=True)
            except OSError: pass
        result = status()
        return {**result, "ok": True, "changed": True}


def _write_state(meta: dict) -> None:
    RSDW_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="cache_state.", suffix=".tmp", dir=str(RSDW_CACHE_ROOT))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(meta, handle, indent=2)
            handle.flush()
            try: os.fsync(handle.fileno())
            except OSError: pass
        os.replace(tmp_name, RSDW_STATE_PATH)
    finally:
        try: Path(tmp_name).unlink(missing_ok=True)
        except OSError: pass


def refresh_model_index(*, force: bool = False, repo: str = DEFAULT_MODEL_REPO, branch: str = DEFAULT_MODEL_BRANCH) -> dict:
    """Atomically refresh the small RSDWModel manifest independently of the app."""
    repo = str(repo or DEFAULT_MODEL_REPO).strip() or DEFAULT_MODEL_REPO
    branch = str(branch or DEFAULT_MODEL_BRANCH).strip() or DEFAULT_MODEL_BRANCH
    with _LOCK:
        before = status()
        revision = _latest_revision(repo, branch)
        if not revision:
            raise RuntimeError("RSDWModel upstream revision could not be determined.")
        if not force and before.get("model_valid") and str(before.get("model_revision") or "") == revision:
            return {**before, "ok": True, "changed": False, "checked_at": time.time()}
        RSDW_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
        staged = RSDW_CACHE_ROOT / ".model.next"
        shutil.rmtree(staged, ignore_errors=True)
        staged.mkdir(parents=True)
        try:
            raw_base = f"https://raw.githubusercontent.com/{repo}/{branch}/website"
            avatar_dir = staged / "Avatar"
            avatar_dir.mkdir(parents=True, exist_ok=True)
            _download(f"{raw_base}/avatar-index.json", staged / "avatar-index.json", timeout=45)
            _download(f"{raw_base}/animation-index.json", staged / "animation-index.json", timeout=45)
            _download(f"{raw_base}/data.config.json", staged / "data.config.json", timeout=30)
            _download(f"{raw_base}/styles.css", staged / "styles.css", timeout=30)
            _download(f"{raw_base}/Avatar/index.html", avatar_dir / "index.html", timeout=30)
            _download(f"{raw_base}/Avatar/avatar.js", avatar_dir / "avatar.js", timeout=45)
            _download(f"{raw_base}/Avatar/avatar.css", avatar_dir / "avatar.css", timeout=30)
            # The viewer shell and Three.js runtime are served locally by the
            # launcher. Current model files remain independently versioned in
            # RSDWModel and are fetched only for the selected avatar layers.
            index_path = avatar_dir / "index.html"
            index_text = index_path.read_text(encoding="utf-8")
            index_text = index_text.replace(
                'https://unpkg.com/three@0.184.0/build/three.module.js',
                '/__rsdwmodel/vendor/three/build/three.module.js',
            ).replace(
                'https://unpkg.com/three@0.184.0/examples/jsm/',
                '/__rsdwmodel/vendor/three/examples/jsm/',
            )
            index_path.write_text(index_text, encoding="utf-8")
            avatar_script_path = avatar_dir / "avatar.js"
            avatar_script = avatar_script_path.read_text(encoding="utf-8")
            avatar_script = avatar_script.replace(
                'https://unpkg.com/three@0.184.0/examples/jsm/libs/draco/',
                '/__rsdwmodel/vendor/three/examples/jsm/libs/draco/',
            )
            avatar_script_path.write_text(avatar_script, encoding="utf-8")
            # Keep the renderer and its dependencies local while resolving the
            # independently versioned, selected model layers from RSDWModel.
            # This avoids embedding a remote page and keeps module updates
            # separate from launcher releases.
            config_path = staged / "data.config.json"
            config = json.loads(config_path.read_text(encoding="utf-8-sig"))
            index_config = json.loads((staged / "avatar-index.json").read_text(encoding="utf-8-sig"))
            dataset_version = str(index_config.get("datasetVersion") or config.get("datasetVersion") or config.get("dataset") or "").strip()
            if dataset_version:
                config["datasetVersion"] = dataset_version
                config["assetBaseUrl"] = f"https://raw.githubusercontent.com/{repo}/{branch}/{dataset_version}/WebAssets"
            config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
            parsed = json.loads((staged / "avatar-index.json").read_text(encoding="utf-8-sig"))
            slots = parsed.get("slots") if isinstance(parsed, dict) else None
            if parsed.get("schema") != "RSDWModel.WebsiteAvatarIndex.v1" or not isinstance(slots, dict) or not slots.get("baseBody") or not slots.get("baseHead"):
                raise RuntimeError("RSDWModel avatar index failed schema validation.")
            if not all((avatar_dir / name).is_file() for name in ("index.html", "avatar.js", "avatar.css")):
                raise RuntimeError("RSDWModel local Avatar viewer files were incomplete.")
            _atomic_swap_dir(staged, RSDW_MODEL_DIR)
        finally:
            shutil.rmtree(staged, ignore_errors=True)
        meta = _read_state()
        meta.update({
            "model_repo": repo, "model_branch": branch, "model_revision": revision,
            "model_refreshed_at": time.time(), "checked_at": time.time(),
        })
        _write_state(meta)
        return {**status(), "ok": True, "changed": True}


def refresh_modules(*, force: bool = False, repo: str = DEFAULT_REPO, branch: str = DEFAULT_BRANCH,
                    model_repo: str = DEFAULT_MODEL_REPO, model_branch: str = DEFAULT_MODEL_BRANCH) -> dict:
    """Refresh RSDWTools and RSDWModel as independently versioned modules."""
    tools = refresh(force=force, repo=repo, branch=branch)
    model_error = ""
    try:
        model = refresh_model_index(force=force, repo=model_repo, branch=model_branch)
    except Exception as exc:
        model = status()
        model_error = str(exc)
    if not model_error:
        meta = _read_state()
        meta["checked_at"] = time.time()
        _write_state(meta)
    combined = status()
    return {
        **combined, "ok": bool(combined.get("valid") and combined.get("toolkit_valid")),
        "changed": bool(tools.get("changed") or model.get("changed")),
        "tools_changed": bool(tools.get("changed")), "model_changed": bool(model.get("changed")),
        "model_error": model_error,
    }


def resolve_icon(item_key: str) -> str:
    """Best-effort local icon lookup for character/inventory rendering."""
    key = str(item_key or "").strip()
    if not key or not RSDW_ICONS_DIR.exists():
        return ""
    safe = key.casefold()
    candidates = []
    for path in RSDW_ICONS_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".svg"}:
            stem = path.stem.casefold()
            if stem == safe or safe in stem or stem in safe:
                candidates.append(path)
                if stem == safe: break
    return str(candidates[0]) if candidates else ""

def _record_name(record: dict) -> str:
    for key in ("Name", "name", "DisplayName", "display_name", "ItemName", "item_name", "label", "Label"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _record_id(record: dict) -> str:
    for key in ("PersistenceID", "PersistenceId", "persistence_id", "ItemID", "ItemId", "item_id", "ID", "Id", "id", "Key", "key"):
        value = record.get(key)
        if isinstance(value, (str, int)) and str(value).strip():
            return str(value).strip()
    return ""


def _iter_records(value, source: str = ""):
    if isinstance(value, dict):
        rid = _record_id(value)
        name = _record_name(value)
        if rid or name:
            yield value, source
        for child in value.values():
            if isinstance(child, (dict, list)):
                yield from _iter_records(child, source)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_records(child, source)


def resolve_catalog_item(item_data: str) -> dict | None:
    """Resolve the opaque save ItemData identifier against the current upstream catalog."""
    wanted = str(item_data or "").strip().casefold()
    if not wanted:
        return None
    candidates: list[tuple[int, dict]] = []
    for path in _json_files(RSDW_DATA_DIR):
        try:
            obj = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        for record, _ in _iter_records(obj, path.name):
            values = (record.get("itemData"), record.get("ItemData"), _record_id(record))
            if any(str(value or "").strip().casefold() == wanted for value in values):
                # The upstream data often contains both a recipe/output stub and
                # the complete catalog row for one ItemData ID. Prefer the row
                # carrying the authoritative equipment slot and model/source
                # metadata so avatar hydration does not stop at the stub.
                score = 0
                if str(record.get("equipment") or record.get("Equipment") or "").strip():
                    score += 20
                if str(record.get("sourcePath") or record.get("SourcePath") or "").strip():
                    score += 10
                if _record_name(record):
                    score += 5
                if _record_id(record):
                    score += 2
                score += min(len(record), 20)
                candidates.append((score, record))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def _model_terms(value: str) -> set[str]:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(value or ""))
    tokens = {part.casefold() for part in re.findall(r"[A-Za-z0-9]+", text)}
    return tokens - {"rsdragonwilds", "content", "gameplay", "character", "player", "equipment", "item", "armour", "armor", "mesh", "data", "json", "uemodel", "med", "sk", "01"}


def resolve_avatar_model(slot: str, sex: str, terms: list[str] | tuple[str, ...]) -> dict | None:
    """Map current catalog/save terms to a current RSDWModel avatar row."""
    try:
        index = json.loads(RSDW_MODEL_INDEX.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    rows = ((index.get("slots") or {}).get(str(slot or "")) or []) if isinstance(index, dict) else []
    wanted_terms: set[str] = set()
    compact = ""
    for term in terms:
        wanted_terms.update(_model_terms(term))
        compact += re.sub(r"[^a-z0-9]", "", str(term or "").casefold())
    generic_terms = {
        "body", "torso", "chest", "legs", "leg", "head", "helmet", "helm",
        "cape", "jewellery", "jewelry", "right", "left", "hand", "weapon",
        "shield", "female", "male", "medium", "mesh", "slot", "wearable",
        "leggings", "trousers", "bottom", "bottoms", "top", "tunic",
    }
    meaningful_wanted = {token for token in wanted_terms if token not in generic_terms and not re.fullmatch(r"t\d+", token)}
    candidates = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_sex = str(row.get("sex") or "")
        if sex and row_sex not in {sex, "U_MED", ""}:
            continue
        hay = " ".join(str(row.get(key) or "") for key in ("id", "name", "displayName", "label", "path", "equipmentMeshDataPath"))
        row_terms = _model_terms(hay)
        shared = wanted_terms & row_terms
        meaningful_shared = meaningful_wanted & row_terms
        row_compact = re.sub(r"[^a-z0-9]", "", hay.casefold())
        score = len(shared) * 7
        for token in wanted_terms:
            if len(token) >= 5 and token in row_compact:
                score += 4
        if compact and len(compact) >= 8 and (compact in row_compact or any(len(token) >= 8 and token in compact for token in row_terms)):
            score += 8
        if str(row.get("id") or "").startswith("EV:"):
            # Equipment variants commonly reuse an Iron base mesh. Do not let
            # that inherited base path make Dragonkin/Paladin/etc. variants look
            # like the plain Iron item. A variant wins only when its own label or
            # mesh-data path contains a meaningful requested set name.
            specific_hay = " ".join(str(row.get(key) or "") for key in ("label", "displayName", "equipmentMeshDataPath"))
            specific_terms = _model_terms(specific_hay)
            meaningful = wanted_terms - {"head", "body", "legs", "torso", "helmet", "female", "male", "medium", "mesh"}
            specific_shared = meaningful & specific_terms
            score += len(specific_shared) * 6 + (3 if specific_shared else -5)
        # Slot words such as Body/Head/Legs are useful for ranking only after
        # the set itself matched. They must never turn an unavailable item into
        # a visually unrelated armour set (for example Adventurer -> Dark Mage).
        meaningful_substring = any(len(token) >= 5 and token in row_compact for token in meaningful_wanted)
        if meaningful_wanted and not meaningful_shared and not meaningful_substring:
            continue
        candidates.append((score, row))
    if not candidates:
        return None
    score, row = max(candidates, key=lambda item: item[0])
    if score < 7:
        return None
    return {"id": str(row.get("id") or ""), "label": str(row.get("label") or row.get("displayName") or ""), "score": score}


def search_items(query: str = "", limit: int = 80) -> dict:
    """Search the validated APPDATA-backed RSDW item cache.

    This deliberately tolerates upstream JSON shape changes: records are discovered
    by common item/name/ID fields rather than relying on one hard-coded manifest.
    """
    text = str(query or "").strip().casefold()
    limit = max(1, min(int(limit or 80), 250))
    if not validate_cache().get("valid"):
        return {"items": [], "count": 0, "cache": status()}
    rows = []
    seen = set()
    for path in _json_files(RSDW_DATA_DIR):
        try:
            obj = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        for record, _ in _iter_records(obj, path.name):
            rid = _record_id(record)
            name = _record_name(record) or rid
            haystack = f"{rid} {name} {json.dumps(record, ensure_ascii=False)[:1600]}".casefold()
            if text and text not in haystack:
                continue
            identity = (rid.casefold(), name.casefold())
            if identity in seen:
                continue
            seen.add(identity)
            icon_key = rid or name
            rows.append({
                "id": rid,
                "item_data": str(record.get("itemData") or record.get("ItemData") or rid),
                "name": name or "Unknown Item",
                "icon_path": resolve_icon(icon_key),
                "source": path.name,
                "source_path": str(record.get("sourcePath") or record.get("SourcePath") or ""),
                "equipment": str(record.get("equipment") or record.get("Equipment") or ""),
                "stackable": bool(record.get("Stackable") or record.get("stackable") or record.get("IsStackable") or record.get("is_stackable")),
                "raw_hint": {k: v for k, v in record.items() if k in {"PersistenceID", "PersistenceId", "ItemID", "ItemId", "Name", "DisplayName", "Stackable", "MaxStackSize", "Durability", "BaseDurability"}},
            })
            if len(rows) >= limit:
                return {"items": rows, "count": len(rows), "cache": status()}
    return {"items": rows, "count": len(rows), "cache": status()}
