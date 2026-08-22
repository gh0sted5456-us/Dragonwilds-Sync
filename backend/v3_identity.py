from __future__ import annotations

"""V3 canonical mod/package identity metadata.

``ID.txt`` is the canonical exported filename. Discovery is case-insensitive and
retains read compatibility for historical ``identity.txt`` / ``identities.txt``
metadata. The file is declarative display/registry metadata only; no command or
script directive is ever executed.
"""

from copy import deepcopy
import json
import re
from pathlib import Path
from typing import Iterable

SCHEMA = "DragonwildsSync.ID.v1"
CANONICAL_FILENAME = "ID.txt"
LEGACY_FILENAMES = ("identity.txt", "identities.txt")
MAX_BYTES = 512 * 1024
MAX_ITEMS = 4096
_SECRET_TOKENS = ("password", "passcode", "secret", "token", "credential", "server_key", "admin_key", "csrf", "session")


def _norm_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _clean_scalar(value: object, limit: int = 4000) -> str:
    return str(value or "").replace("\x00", "").strip()[:limit]


def _safe_value(value):
    if isinstance(value, dict):
        out = {}
        for key, child in value.items():
            folded = _norm_key(key)
            if any(token.replace("_", "") in folded for token in _SECRET_TOKENS):
                continue
            out[str(key)[:120]] = _safe_value(child)
        return out
    if isinstance(value, list):
        return [_safe_value(child) for child in value[:MAX_ITEMS]]
    if isinstance(value, tuple):
        return [_safe_value(child) for child in value[:MAX_ITEMS]]
    if isinstance(value, str):
        return "" if value.startswith("dws-secret://") else _clean_scalar(value)
    return deepcopy(value)


def discover_identity_file(root: str | Path) -> Path | None:
    """Find canonical ID.txt case-insensitively, then legacy identity names."""
    base = Path(root)
    directory = base if base.is_dir() else base.parent
    if not directory.is_dir():
        return None
    try:
        files = [p for p in directory.iterdir() if p.is_file()]
    except OSError:
        return None
    by_folded: dict[str, list[Path]] = {}
    for path in files:
        by_folded.setdefault(path.name.casefold(), []).append(path)
    for wanted in (CANONICAL_FILENAME, *LEGACY_FILENAMES):
        matches = sorted(by_folded.get(wanted.casefold(), []), key=lambda p: p.name)
        if matches:
            return matches[0]
    return None


def _item_from_mapping(raw: dict, *, mod_id: str = "") -> dict:
    lowered = {_norm_key(k): v for k, v in raw.items()}
    item_name = _clean_scalar(lowered.get("itemname") or lowered.get("item") or lowered.get("name"), 200)
    persistence = _clean_scalar(lowered.get("persistenceid") or lowered.get("persistence") or lowered.get("pid"), 200)
    asset_path = _clean_scalar(lowered.get("assetpath") or lowered.get("path"), 1000)
    icon = _clean_scalar(lowered.get("icon") or lowered.get("iconpath"), 1000)
    record = {
        "ITEM Name": item_name,
        "PersistenceID": persistence,
        "Icon": icon,
        "AssetPath": asset_path,
        "ModId": _clean_scalar(lowered.get("modid") or mod_id, 160),
    }
    display = _clean_scalar(lowered.get("displayname") or lowered.get("label"), 200)
    if display:
        record["DisplayName"] = display
    return {k: v for k, v in record.items() if v}


def parse_id_text(text: str, *, source_name: str = "") -> dict:
    """Parse V3 ID.txt plus the historical key:value identity convention."""
    result = {
        "schema": SCHEMA,
        "source_filename": source_name,
        "legacy": str(source_name or "").casefold() in {x.casefold() for x in LEGACY_FILENAMES},
        "mod_id": "", "name": "", "version": "", "revision": "",
        "description": "", "runtime_role": "both", "hotload_capable": False, "author": "", "tags": [],
        "links": [], "items": [],
    }
    seen_tags: set[str] = set()
    seen_links: set[str] = set()
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";;", "//")):
            continue
        if line.startswith("[") and line.endswith("]"):
            continue
        separators = [(line.find(token), token) for token in (":", "=") if line.find(token) >= 0]
        if not separators:
            continue
        _, separator = min(separators)
        key, value = line.split(separator, 1)
        key_norm = _norm_key(key)
        value = value.strip()
        if not value:
            continue
        if key_norm in {"item", "itemrecord"}:
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                parsed = {}
                for part in value.split("|"):
                    if "=" in part:
                        k, v = part.split("=", 1); parsed[k.strip()] = v.strip()
            if isinstance(parsed, dict):
                row = _item_from_mapping(parsed, mod_id=result["mod_id"])
                if row and len(result["items"]) < MAX_ITEMS:
                    result["items"].append(row)
            continue
        if key_norm in {"schema", "format"}:
            continue
        if key_norm in {"modid", "id", "modidentifier"}:
            result["mod_id"] = _clean_scalar(value, 160)
        elif key_norm in {"name", "modname", "title"}:
            result["name"] = _clean_scalar(value, 200)
        elif key_norm in {"version", "modversion"}:
            result["version"] = _clean_scalar(value, 80)
        elif key_norm in {"revision", "rev", "metadatarevision"}:
            result["revision"] = _clean_scalar(value, 80)
        elif key_norm in {"description", "about", "summary"}:
            result["description"] = _clean_scalar(value, 4000)
        elif key_norm in {"author", "creator", "by", "modder", "authors"}:
            result["author"] = _clean_scalar(value, 200)
        elif key_norm in {"runtimerole", "role", "runtime"}:
            role = value.casefold().replace("-", "_")
            aliases = {"host": "server", "dedicated": "server", "clientonly": "client", "serveronly": "server"}
            role = aliases.get(role, role)
            result["runtime_role"] = role if role in {"client", "server", "both", "tooling"} else "both"
        elif key_norm in {"hotload", "hotloadcapable", "liveediting", "liveedit"}:
            result["hotload_capable"] = value.casefold() in {"1", "true", "yes", "on", "enabled"}
        elif key_norm in {"tags", "tag"}:
            for tag in re.split(r"[;,]", value):
                clean = _clean_scalar(tag, 40)
                folded = clean.casefold()
                if clean and folded not in seen_tags and len(result["tags"]) < 24:
                    result["tags"].append(clean); seen_tags.add(folded)
        elif value.casefold().startswith(("https://", "http://")):
            url = _clean_scalar(value, 1000)
            if url not in seen_links and len(result["links"]) < 12:
                result["links"].append({"label": _clean_scalar(key, 80), "url": url}); seen_links.add(url)
    for row in result["items"]:
        if not row.get("ModId") and result["mod_id"]:
            row["ModId"] = result["mod_id"]
    return _safe_value(result)


def read_identity(root_or_file: str | Path) -> dict | None:
    source = Path(root_or_file)
    target = source if source.is_file() and source.name.casefold() in {CANONICAL_FILENAME.casefold(), *(x.casefold() for x in LEGACY_FILENAMES)} else discover_identity_file(source)
    if target is None:
        return None
    try:
        if target.stat().st_size > MAX_BYTES:
            raise ValueError("Mod identity metadata exceeds the safety limit.")
        return parse_id_text(target.read_text(encoding="utf-8", errors="replace"), source_name=target.name)
    except OSError:
        return None


def render_id_text(identity: dict) -> str:
    """Render the canonical V3 file. Callers must save it exactly as ID.txt."""
    value = _safe_value(identity if isinstance(identity, dict) else {})
    lines = ["# Dragonwilds Sync ID v1", f"Schema: {SCHEMA}"]
    fields = (
        ("ModId", value.get("mod_id") or value.get("ModId")),
        ("Name", value.get("name") or value.get("Name")),
        ("Version", value.get("version") or value.get("Version")),
        ("Revision", value.get("revision") or value.get("Revision")),
        ("Author", value.get("author") or value.get("Author")),
        ("RuntimeRole", value.get("runtime_role") or value.get("RuntimeRole") or "both"),
        ("Description", value.get("description") or value.get("Description")),
    )
    for label, raw in fields:
        clean = _clean_scalar(raw, 4000)
        if clean:
            lines.append(f"{label}: {clean.replace(chr(10), ' ')}")
    # Canonical and human-editable. Historical HotloadCapable:true remains
    # readable, while a one-line "HOTLOAD = YES" file is fully valid.
    lines.append("HOTLOAD = YES" if bool(value.get("hotload_capable") or value.get("HotloadCapable")) else "HOTLOAD = NO")
    tags = value.get("tags") or value.get("Tags") or []
    if tags:
        lines.append("Tags: " + "; ".join(_clean_scalar(x, 40) for x in tags if _clean_scalar(x, 40)))
    for link in value.get("links") or []:
        if isinstance(link, dict) and str(link.get("url") or "").startswith(("http://", "https://")):
            lines.append(f"{_clean_scalar(link.get('label') or 'Website', 80)}: {_clean_scalar(link.get('url'), 1000)}")
    mod_id = _clean_scalar(value.get("mod_id") or value.get("ModId"), 160)
    for raw in (value.get("items") or [])[:MAX_ITEMS]:
        if not isinstance(raw, dict):
            continue
        item = _item_from_mapping(raw, mod_id=mod_id)
        if item:
            lines.append("Item: " + json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return "\n".join(lines).rstrip() + "\n"


def write_identity(root: str | Path, identity: dict) -> Path:
    base = Path(root)
    base.mkdir(parents=True, exist_ok=True)
    target = base / CANONICAL_FILENAME
    target.write_text(render_id_text(identity), encoding="utf-8")
    return target


def identity_items(identities: Iterable[dict]) -> list[dict]:
    rows: list[dict] = []
    for identity in identities:
        if not isinstance(identity, dict):
            continue
        for item in identity.get("items") or []:
            if isinstance(item, dict):
                row = dict(item)
                row.setdefault("ModId", identity.get("mod_id") or "")
                row["_identity_version"] = identity.get("version") or ""
                row["_identity_revision"] = identity.get("revision") or ""
                rows.append(row)
    return rows
