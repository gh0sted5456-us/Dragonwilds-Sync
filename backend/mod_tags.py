from __future__ import annotations
import json
import re
from pathlib import Path
from v3_identity import CANONICAL_FILENAME, discover_identity_file, read_identity, write_identity

MAX_TAGS = 24
MAX_TAG_LEN = 40
HOTLOAD_MARKERS = ("hotload.txt", "hotload.json")
IDENTITY_FILENAME = CANONICAL_FILENAME
LEGACY_IDENTITY_FILENAME = "IDENTITY.txt"

# UE4SS ships these Lua mods baked into its own default distribution (loader
# scaffolding, console/cheat enabler toggles, keybind config, shared helpers).
# They physically exist on disk and are left untouched, but launcher mod lists
# don't present them since there is nothing for a player or server operator to
# manage about them -- they're part of the UE4SS runtime itself, not a mod a
# player installed.
UE4SS_BAKED_IN_DEFAULT_MODS = {
    "bpml_genericfunctions", "bpmodloadermod", "cheatmanagerenablermod",
    "consolecommandsmod", "consoleenablermod", "keybinds", "shared",
}

_IDENTITY_LINK_LABELS = {
    "nexus": "Nexus", "nexusmods": "Nexus", "nexus_link": "Nexus", "nexuslink": "Nexus",
    "steam": "Steam", "steam_link": "Steam", "steamlink": "Steam", "steam_workshop": "Steam",
    "website": "Website", "site": "Website", "url": "Website", "link": "Website", "web": "Website", "homepage": "Website",
    "github": "GitHub", "discord": "Discord", "youtube": "YouTube", "twitter": "Twitter", "x": "Twitter",
}
_IDENTITY_ALLOWED_SCHEMES = ("http://", "https://")
_IDENTITY_MAX_LINKS = 8


def _normalize(values) -> list[str]:
    if isinstance(values, str):
        values = values.replace(",", ";").split(";")
    if isinstance(values, dict):
        values = values.get("tags") or values.get("Tags") or []
    if not isinstance(values, (list, tuple, set)):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        tag = str(raw or "").strip()[:MAX_TAG_LEN]
        key = tag.casefold()
        if tag and key not in seen:
            result.append(tag); seen.add(key)
        if len(result) >= MAX_TAGS:
            break
    return result


def normalize_tags(values) -> list[str]:
    """Normalize launcher-facing tags from UI, TXT, JSON, or manifest input."""
    return _normalize(values)


def parse_tags_text(text: str) -> list[str]:
    values=[]
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";;", "//")):
            continue
        if "#" in line:
            line = line.split("#", 1)[0].strip()
        values.extend(line.split(";"))
    return _normalize(values)


def parse_tags_file(path: str | Path) -> list[str]:
    target = Path(path)
    if not target.is_file():
        return []
    try:
        if target.suffix.casefold() == ".json":
            return _normalize(json.loads(target.read_text(encoding="utf-8", errors="replace")))
        return parse_tags_text(target.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError, TypeError):
        return []


def tags_from_mod_root(root: str | Path) -> list[str]:
    base = Path(root)
    if not base.is_dir():
        return []
    identity = read_identity(base)
    if identity and identity.get("tags"):
        return _normalize(identity.get("tags"))
    # Legacy files remain readable but are never newly generated.
    tags = parse_tags_file(base / "tags.json")
    return tags or parse_tags_file(base / "tags.txt")


def tags_from_sidecar(path: str | Path, *, clean_stem: str = "") -> list[str]:
    """Read a PAK/file sidecar, preferring JSON while retaining tags.txt."""
    source = Path(path)
    stem = str(clean_stem or source.stem)
    for suffix in (".tags.json", ".tags.txt"):
        tags = parse_tags_file(source.with_name(stem + suffix))
        if tags:
            return tags
    return []


def ensure_baked_in_ue4ss_enabled(ue4ss_mods_root: str | Path) -> list[str]:
    """Ensure every UE4SS baked-in default mod present on disk carries a blank
    ``enabled.txt``, so UE4SS self-enables it independent of ``mods.txt`` --
    the file Dragonwilds Sync owns and rewrites for user-installed mod load
    order. mods.txt entries only cover load order/toggling for mods the
    launcher actually manages; the baked-in defaults ship with UE4SS itself
    and must keep working even if mods.txt is rebuilt without them.

    Never raises -- one bad folder (locked file, permission issue, OneDrive
    placeholder still hydrating) is reported as a warning and skipped rather
    than aborting the caller's scan.
    """
    root = Path(ue4ss_mods_root)
    warnings: list[str] = []
    if not root.exists():
        return warnings
    try:
        entries = {c.name.casefold(): c for c in root.iterdir() if c.is_dir()}
    except OSError as exc:
        return [f"Could not list UE4SS Mods folder for default-mod check: {exc}"]
    for name in UE4SS_BAKED_IN_DEFAULT_MODS:
        mod_dir = entries.get(name)
        if mod_dir is None:
            continue
        marker = mod_dir / "enabled.txt"
        try:
            if not marker.is_file():
                marker.write_text("", encoding="utf-8")
        except OSError as exc:
            warnings.append(f"Could not write enabled.txt for \"{mod_dir.name}\": {exc}")
    return warnings


def discover_packaged_metadata(archive_root: str | Path, *, effective_root: str | Path | None = None,
                                payload_files=None, recursive_fallback: bool = True) -> dict:
    """Discover metadata in a staged Nexus/manual archive.

    Authors commonly wrap a mod in one or more folders or place PAK metadata
    beside the payload. Prefer the effective mod root and PAK sidecars, then use
    a shallow recursive fallback. This is read-only and bounded to recognized
    filenames; arbitrary JSON/TXT files are never interpreted as metadata.
    """
    archive = Path(archive_root)
    effective = Path(effective_root) if effective_root is not None else archive
    roots: list[Path] = []
    root_candidates = (effective,) if not recursive_fallback else (effective, archive)
    for candidate in root_candidates:
        if candidate.is_dir() and candidate not in roots:
            roots.append(candidate)
    tags: list[str] = []
    sources: list[str] = []
    identity_hotload = False
    identity_sources: list[str] = []

    def add_identity(root: Path) -> None:
        nonlocal tags, identity_hotload
        identity_path = discover_identity_file(root)
        identity = read_identity(root)
        if not identity_path or not identity:
            return
        values = _normalize(identity.get("tags") or [])
        if values:
            tags = _normalize(tags + values)
        identity_hotload = identity_hotload or bool(identity.get("hotload_capable"))
        try: label = identity_path.relative_to(archive).as_posix()
        except ValueError: label = identity_path.name
        if label not in identity_sources: identity_sources.append(label)

    def add_file(path: Path) -> None:
        nonlocal tags
        values = parse_tags_file(path)
        if values:
            tags = _normalize(tags + values)
            try: label = path.relative_to(archive).as_posix()
            except ValueError: label = path.name
            if label not in sources: sources.append(label)

    payloads = [Path(value) for value in (payload_files or []) if Path(value).is_file()]
    for payload in payloads:
        stems = [payload.stem]
        clean = re.sub(r"^\d{1,3}[_-]+", "", payload.stem)
        if clean and clean not in stems: stems.append(clean)
        for stem in stems:
            for suffix in (".tags.json", ".tags.txt"):
                add_file(payload.with_name(stem + suffix))

    # A payload-specific PAK sidecar wins. Otherwise the effective mod root
    # wins over an outer Nexus/download wrapper.
    for root in roots:
        add_identity(root)
        if tags:
            break

    if not tags:
        for root in roots:
            for name in ("tags.json", "tags.txt"):
                add_file(root / name)
            if tags:
                break

    # Some Nexus archives have extra documentation/wrapper directories. Only
    # fall back when authoritative root/sidecar metadata was not found.
    if recursive_fallback and not tags and archive.is_dir():
        candidates = [p for p in archive.rglob("*") if p.is_file() and p.name.casefold() in {"tags.txt", "tags.json"}]
        candidates.sort(key=lambda p: (len(p.relative_to(archive).parts), 0 if p.suffix.casefold() == ".json" else 1, p.as_posix().casefold()))
        if candidates:
            shallowest = len(candidates[0].relative_to(archive).parts)
            for path in candidates:
                if len(path.relative_to(archive).parts) != shallowest: break
                add_file(path)

    marker_paths: list[str] = []
    marker_candidates: list[Path] = []
    for root in roots:
        marker_candidates.extend(root / marker for marker in HOTLOAD_MARKERS)
    if recursive_fallback and effective.is_dir():
        marker_candidates.extend(p for p in effective.rglob("*") if p.is_file() and p.name.casefold() in HOTLOAD_MARKERS)
    seen_markers: set[Path] = set()
    for marker in marker_candidates:
        if marker in seen_markers or not marker.is_file(): continue
        seen_markers.add(marker)
        try: marker_paths.append(marker.relative_to(archive).as_posix())
        except ValueError: marker_paths.append(marker.name)
    return {"tags": tags, "hotload_capable": identity_hotload or bool(marker_paths),
            "tag_files": identity_sources or sources, "hotload_files": identity_sources if identity_hotload else marker_paths}


def hotload_capable_from_root(root: str | Path) -> bool:
    """A blank hotload.txt/hotload.json is an explicit capability marker.

    Content is intentionally ignored: the marker means the mod author asserts that
    launcher-managed configuration can be applied while Dragonwilds is running.
    """
    base = Path(root)
    if not base.is_dir():
        return False
    identity = read_identity(base)
    if identity is not None and not identity.get("legacy"):
        return bool(identity.get("hotload_capable"))
    json_marker = base / "hotload.json"
    if json_marker.is_file():
        try:
            value = json.loads(json_marker.read_text(encoding="utf-8", errors="replace"))
            if isinstance(value, dict) and value.get("enabled") is False:
                return False
        except (OSError, json.JSONDecodeError, TypeError):
            pass
        return True
    text_marker = base / "hotload.txt"
    if not text_marker.is_file():
        return False
    try:
        meaningful = [line.strip().casefold() for line in text_marker.read_text(encoding="utf-8", errors="replace").splitlines()
                      if line.strip() and not line.lstrip().startswith(("#", ";", "//"))]
    except OSError:
        return True
    return not any(line in {"0", "false", "off", "disabled", "enabled=false"} for line in meaningful)


def set_hotload_marker(root: str | Path, enabled: bool) -> bool:
    """Persist hotload capability in canonical ID.txt."""
    base = Path(root)
    if not base.is_dir():
        return False
    identity = read_identity(base) or {"mod_id": base.name, "name": base.name, "runtime_role": "both"}
    identity["hotload_capable"] = bool(enabled)
    write_identity(base, identity)
    return bool(enabled)


def set_tags_file(root: str | Path, values) -> list[str]:
    """Persist canonical directory-mod tags in ID.txt at the mod root."""
    base = Path(root)
    if not base.is_dir():
        return []
    tags = normalize_tags(values)
    identity = read_identity(base) or {"mod_id": base.name, "name": base.name, "runtime_role": "both"}
    identity["tags"] = tags
    write_identity(base, identity)
    return tags


def ensure_mod_contract_files(root: str | Path) -> dict:
    """Repair launcher metadata files without changing mod capability.

    Existing community markers retain their meaning. New metadata is consolidated
    into ID.txt; legacy files remain untouched and readable.

    This runs on every mod-directory scan (including plain "read-only"
    inventory refreshes), so a write failure here -- a locked/read-only mod
    folder, a OneDrive placeholder that hasn't finished syncing, an
    antivirus lock, a permissions-restricted install location -- must never
    abort the scan of every other mod. Any failure is swallowed and reported
    back as "not repaired" rather than raised.
    """
    base = Path(root)
    if not base.is_dir():
        return {"hotload": False, "tags": False, "identity": False, "error": ""}
    identity = discover_identity_file(base)
    error = ""
    if identity is None:
        try:
            legacy_tags = parse_tags_file(base / "tags.json") or parse_tags_file(base / "tags.txt")
            legacy_hotload = any((base / marker).is_file() for marker in HOTLOAD_MARKERS)
            identity = write_identity(base, {"mod_id": base.name, "name": base.name, "runtime_role": "both",
                                             "tags": legacy_tags, "hotload_capable": legacy_hotload})
        except OSError as exc:
            error = str(exc)
    parsed = read_identity(base) or {}
    return {"hotload": bool(parsed.get("hotload_capable")), "tags": bool(parsed.get("tags")),
            "identity": identity is not None, "canonical": bool(identity and identity.name == CANONICAL_FILENAME), "error": error}


def parse_identity_text(text: str) -> dict:
    """Parse the ``key: value`` contract of an author-supplied IDENTITY.txt.

    Recognized keys: author/creator/by/modder (one free-text name),
    description/about/summary (one short blurb), and any other key whose
    value is an http(s) URL becomes a labeled link (nexus/steam/website/
    github/discord/... get a friendly label; anything else uses the key
    itself, title-cased). Non-http(s) values on an unrecognized key are
    ignored -- this file is never treated as anything but display metadata.
    """
    author = ""
    description = ""
    links: list[dict] = []
    seen_urls: set[str] = set()
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";;", "//")):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().casefold().replace(" ", "_").replace("-", "_")
        value = value.strip()
        if not key or not value:
            continue
        if key in ("author", "creator", "by", "modder", "authors"):
            if not author:
                author = value[:120]
        elif key in ("description", "about", "summary"):
            if not description:
                description = value[:400]
        elif value.casefold().startswith(_IDENTITY_ALLOWED_SCHEMES) and len(links) < _IDENTITY_MAX_LINKS:
            label = _IDENTITY_LINK_LABELS.get(key) or (key.replace("_", " ").title()[:24] or "Link")
            url = value[:2000]
            if url not in seen_urls:
                links.append({"label": label, "url": url})
                seen_urls.add(url)
    return {"author": author, "description": description, "links": links}


def identity_from_mod_root(root: str | Path) -> dict | None:
    """Read IDENTITY.txt from a UE4SS mod, RuneSchema mod, or PAK group root.

    Returns ``None`` when no file is present or it carries no recognizable
    fields, so callers can treat that as "no identity declared" rather than
    an empty-but-present card. Read-only -- Dragonwilds Sync never writes
    this file; it belongs entirely to the mod author.
    """
    base = Path(root)
    canonical = read_identity(base)
    if canonical is None:
        return None
    parsed = {"author": str(canonical.get("author") or ""), "description": str(canonical.get("description") or ""),
              "links": list(canonical.get("links") or []), "mod_id": str(canonical.get("mod_id") or ""),
              "name": str(canonical.get("name") or ""), "version": str(canonical.get("version") or ""),
              "runtime_role": str(canonical.get("runtime_role") or "both")}
    if not parsed["author"] and not parsed["description"] and not parsed["links"]:
        return None
    return parsed
