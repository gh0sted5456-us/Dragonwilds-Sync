from __future__ import annotations

"""Python ports of RuneSchema's own tooling logic (mods.txt load order,
compatibility report, FModel snippet generator), plus variant detection.

These are line-for-line ports of the C++ in RuneSchema 0.6.1 Experimental's
source (``ModLoadOrder.cpp``, ``CompatibilityReporter.cpp``,
``FModelSnippetGenerator.cpp``, ``Utility/ObjectPath.cpp``), reviewed
directly from that source rather than inferred from strings or behavior --
so the file formats this module reads and writes are exactly the ones
RuneSchema itself reads and writes, and a round-trip through either side
should look identical on disk.

Two things are deliberately NOT ported here because they need the live
running Unreal Engine process's own reflection data, which only exists
inside the game: JSON schema generation (walks live UClass/FProperty
metadata) and the "Overview" tab's version display (both are surfaced from
observed evidence -- config.json shape, UE4SS.log's own mod-load line --
not recomputed).
"""

import json
import os
import re
import time
from pathlib import Path

_HEADER_LINES = (
    "; RuneSchema mod load order - mods are loaded top to bottom.\n",
    "; Set the value to 0 to disable a mod without removing its folder.\n",
)

# RuneSchema's own mod-load line ("RuneSchema v0.6.1 Experimental by Okaetsu
# loaded." vs "RuneSchema v0.6.0 by Okaetsu loaded.") is the one signal that
# comes directly from whichever DLL is actually running, so it takes
# priority over config.json shape -- a leftover Experimental config.json
# sitting next to an official 0.6.0 DLL should not be misreported.
_VERSION_LINE = re.compile(r"RuneSchema\s+v([0-9][0-9.]*)(\s+Experimental)?\s+by\s+\S+\s+loaded\.", re.IGNORECASE)

# Properties RuneSchema's own generators consider unsafe to suggest editing.
# FModelSnippetGenerator's set (used here) is a superset of
# JsonSchemaGenerator's -- it additionally excludes SimpleConstructionScript
# and UberGraphFunction.
_UNSAFE_PROPERTY_NAMES = {
    "PersistenceID", "InternalName", "RootComponent", "UberGraphFrame",
    "BlueprintCreatedComponents", "InstanceComponents",
    "SimpleConstructionScript", "UberGraphFunction",
}


def _is_unsafe_property(name: str) -> bool:
    return name in _UNSAFE_PROPERTY_NAMES or name.endswith("Guid") or name.endswith("GUID")


def _strip_json_comments(text: str) -> str:
    """Strip // and /* */ comments outside of string literals.

    Mirrors nlohmann::json::parse(..., ignore_comments=true), which is how
    RuneSchema itself reads every JSON file this module also reads.
    """
    out = []
    i, n = 0, len(text)
    in_string = False
    escape = False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            i += 2
            while i < n and text[i] not in "\r\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _parse_jsonc(text: str):
    return json.loads(_strip_json_comments(text))


# --------------------------------------------------------------------------
# Variant detection
# --------------------------------------------------------------------------

def detect_variant(runtime: dict, config_raw: str = "") -> dict:
    """Best-effort detection of which RuneSchema build is installed.

    Priority: RuneSchema's own "vX.Y.Z [Experimental] by Okaetsu loaded."
    line in UE4SS.log (comes straight from the running DLL) beats
    config.json shape (a leftover config from a previously-installed build
    proves nothing about what's running now), which beats "unknown".
    """
    root_value = str(runtime.get("game_root") or "").strip()
    log_candidates = []
    if root_value:
        root = Path(root_value)
        log_candidates = [
            root / "Binaries" / "Win64" / "ue4ss" / "UE4SS.log",
            root / "RSDragonwilds" / "Binaries" / "Win64" / "ue4ss" / "UE4SS.log",
            root / "Binaries" / "Win64" / "UE4SS.log",
        ]
    for path in log_candidates:
        try:
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        match = None
        for candidate in _VERSION_LINE.finditer(text):
            match = candidate  # last occurrence wins (most recent load)
        if match:
            experimental = bool(match.group(2))
            return {
                "variant": "experimental" if experimental else "github",
                "version": match.group(1) + (match.group(2) or ""),
                "source": "ue4ss_log",
            }

    if config_raw.strip():
        try:
            data = _parse_jsonc(config_raw)
            if isinstance(data, dict) and isinstance(data.get("tooling"), dict):
                return {"variant": "experimental", "version": "", "source": "config_shape"}
            if isinstance(data, dict):
                return {"variant": "github", "version": "0.6.0", "source": "config_shape"}
        except (json.JSONDecodeError, ValueError):
            pass

    return {"variant": "unknown", "version": "", "source": "none"}


# --------------------------------------------------------------------------
# Load order (mods.txt) -- port of ModLoadOrder.cpp
# --------------------------------------------------------------------------

def _trim(value: str) -> str:
    return value.strip(" \t\r\n")


def load_order_read(mods_root: Path, strict_values: bool) -> list[dict]:
    """Port of ModLoadOrder::Load(). Returns [{"name": str, "enabled": bool}]."""
    mods_txt = mods_root / "mods.txt"
    entries: list[dict] = []
    try:
        text = mods_txt.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return entries
    for raw_line in text.splitlines():
        trimmed = _trim(raw_line)
        if not trimmed or trimmed[0] in (";", "#"):
            continue
        separator = trimmed.find(":")
        if separator < 0:
            continue
        name = _trim(trimmed[:separator])
        value = _trim(trimmed[separator + 1:])
        if not name:
            continue
        if strict_values and value not in ("0", "1"):
            entries.append({"name": name, "enabled": False})
            continue
        entries.append({"name": name, "enabled": value != "0"})
    return entries


def _write_plain(mods_txt: Path, entries: list[dict]) -> None:
    mods_txt.parent.mkdir(parents=True, exist_ok=True)
    lines = list(_HEADER_LINES)
    lines += [f"{entry['name']} : {1 if entry['enabled'] else 0}\n" for entry in entries]
    tmp = mods_txt.with_suffix(mods_txt.suffix + ".tmp")
    tmp.write_text("".join(lines), encoding="utf-8")
    os.replace(tmp, mods_txt)


def _write_preserving_comments(mods_txt: Path, entries: list[dict]) -> None:
    """Port of ModLoadOrder::SavePreservingComments().

    Faithfully reproduces its exact (slightly surprising) behavior: comment
    and blank lines from the existing file are kept, in their original
    order, ahead of every entry -- entry lines from the old file are
    dropped, not edited in place, and the new entries (in the order passed
    in) are appended afterward as one contiguous block. This matches what
    RuneSchema's own "Save Load Order" button produces, so a file edited
    from here and one edited in-game look the same.
    """
    kept_lines: list[str] = []
    try:
        existing = mods_txt.read_text(encoding="utf-8", errors="replace")
    except OSError:
        existing = ""
    for raw_line in existing.splitlines():
        trimmed = _trim(raw_line)
        separator = trimmed.find(":")
        if not trimmed or trimmed[0] in (";", "#") or separator < 0:
            kept_lines.append(raw_line)
            continue
        name = _trim(trimmed[:separator])
        if not name:
            kept_lines.append(raw_line)
        # else: entry line -- dropped, rewritten below.

    mods_txt.parent.mkdir(parents=True, exist_ok=True)
    lines = [line + "\n" for line in kept_lines]
    lines += [f"{entry['name']} : {1 if entry['enabled'] else 0}\n" for entry in entries]
    tmp = mods_txt.with_suffix(mods_txt.suffix + ".tmp")
    tmp.write_text("".join(lines), encoding="utf-8")
    os.replace(tmp, mods_txt)


def load_order_write(mods_root: Path, entries: list[dict], preserve_comments: bool) -> None:
    """Port of ModLoadOrder::WriteEntries()."""
    mods_txt = mods_root / "mods.txt"
    if preserve_comments and mods_txt.exists():
        _write_preserving_comments(mods_txt, entries)
    else:
        _write_plain(mods_txt, entries)


def discover_mod_folders(mods_root: Path) -> list[str]:
    if not mods_root.is_dir():
        return []
    names = []
    for entry in mods_root.iterdir():
        if entry.is_dir():
            names.append(entry.name)
    return names


def load_order_resolve(mods_root: Path, discovered_names: list[str], mods_txt_settings: dict) -> dict:
    """Port of ModLoadOrder::Resolve().

    Unlike the read-only ReadEntries(), this also reconciles against what's
    actually on disk (adds newly-discovered mod folders, drops entries for
    folders that no longer exist) and, depending on settings, persists that
    reconciliation back to mods.txt -- exactly what RuneSchema itself does
    on every load and what its "Reconcile mods.txt Now" button does on
    demand.

    Returns {"entries": [...] (post-reconcile, pre-filter, in file order),
    "ordered_enabled_names": [...], "changed": bool, "persisted": bool}.
    """
    discovered_sorted = sorted(discovered_names)
    enabled = bool(mods_txt_settings.get("enabled", True))
    if not enabled:
        return {
            "entries": [{"name": name, "enabled": True} for name in discovered_sorted],
            "ordered_enabled_names": discovered_sorted, "changed": False, "persisted": False,
            "note": "mods.txt is disabled in Settings; using alphabetical folder order.",
        }

    mods_txt = mods_root / "mods.txt"
    file_existed = mods_txt.exists()
    auto_create = bool(mods_txt_settings.get("autoCreate", True))
    if not file_existed and not auto_create:
        return {
            "entries": [{"name": name, "enabled": True} for name in discovered_sorted],
            "ordered_enabled_names": discovered_sorted, "changed": False, "persisted": False,
            "note": "mods.txt does not exist and autoCreate is off.",
        }

    strict_values = bool(mods_txt_settings.get("strictValues", True))
    entries = load_order_read(mods_root, strict_values)

    discovered_set = set(discovered_names)
    before = len(entries)
    entries = [entry for entry in entries if entry["name"] in discovered_set]
    dropped_stale = len(entries) != before

    known = {entry["name"] for entry in entries}
    appended_any = False
    for name in discovered_sorted:
        if name not in known:
            known.add(name)
            entries.append({"name": name, "enabled": True})
            appended_any = True

    reconcile_folders = bool(mods_txt_settings.get("reconcileFolders", True))
    appended_new_entries = appended_any and reconcile_folders

    persisted = False
    if not file_existed or (reconcile_folders and (dropped_stale or appended_new_entries)):
        preserve_comments = bool(mods_txt_settings.get("preserveComments", True))
        load_order_write(mods_root, entries, preserve_comments)
        persisted = True

    ordered_enabled_names = [entry["name"] for entry in entries if entry["enabled"]]
    return {
        "entries": entries, "ordered_enabled_names": ordered_enabled_names,
        "changed": dropped_stale or appended_any, "persisted": persisted,
    }


# --------------------------------------------------------------------------
# Compatibility report -- port of CompatibilityReporter.cpp + ObjectPath.cpp
# --------------------------------------------------------------------------

def normalize_object_path(path: str, object_name: str = "", class_reference: bool = False) -> str:
    """Port of PS::ObjectPath::Normalize().

    Treats a numeric FModel export suffix (".0") as the asset's own name, so
    "/Game/Items/ITEM_Iron", "/Game/Items/ITEM_Iron.0", and
    "/Game/Items/ITEM_Iron.ITEM_Iron" all normalize to the same target.
    """
    if not path:
        return path
    colon = path.find(":")
    top_level = path if colon < 0 else path[:colon]
    sub_path = "" if colon < 0 else path[colon:]
    slash = top_level.rfind("/")
    dot = top_level.rfind(".")
    has_asset_suffix = dot >= 0 and (slash < 0 or dot > slash)

    resolved_name = object_name
    if not resolved_name:
        package_start = 0 if slash < 0 else slash + 1
        package_end = dot if has_asset_suffix else len(top_level)
        resolved_name = top_level[package_start:package_end]

    if not has_asset_suffix:
        top_level = top_level + "." + resolved_name
    elif top_level[dot + 1:].isdigit() and top_level[dot + 1:] != "":
        top_level = top_level[:dot + 1] + resolved_name

    if class_reference and not top_level.endswith("_C"):
        top_level += "_C"

    return top_level + sub_path


def generate_compatibility_report(mods_root: Path, ordered_mod_names: list[str], settings: dict) -> dict:
    """Port of CompatibilityReporter::Generate().

    ``mods_root`` is the RuneSchema ``mods`` folder (containing one
    subfolder per content mod); the report file, when written, goes to its
    sibling ``config/compatibility_report.txt`` -- exactly where
    RuneSchema's own "Generate Compatibility Report" button writes it, so
    either can read what the other wrote.
    """
    if not settings.get("enabled", True):
        return {"generated": False, "reason": "Compatibility reports are disabled in Settings.", "report": "", "warning_count": 0}

    target_writes: dict[str, list[dict]] = {}
    property_writes: dict[str, list[dict]] = {}

    for mod_name in ordered_mod_names:
        mod_path = mods_root / mod_name
        if not mod_path.is_dir():
            continue
        for loader_entry in sorted(mod_path.iterdir(), key=lambda p: p.name):
            if not loader_entry.is_dir() or loader_entry.name in ("config", "paks"):
                continue
            for file_entry in sorted(loader_entry.iterdir(), key=lambda p: p.name):
                if not file_entry.is_file() or file_entry.suffix.lower() not in (".json", ".jsonc"):
                    continue
                try:
                    data = _parse_jsonc(file_entry.read_text(encoding="utf-8", errors="replace"))
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(data, dict):
                    continue

                relative_file = str(file_entry.relative_to(mods_root)).replace(os.sep, "/")
                for raw_target, properties in data.items():
                    if raw_target.startswith("$") or not isinstance(properties, dict):
                        continue
                    normalized_target = raw_target
                    if loader_entry.name == "assets" and raw_target.startswith("/"):
                        normalized_target = normalize_object_path(raw_target)
                    target_key = f"{loader_entry.name}|{normalized_target}"
                    target_writes.setdefault(target_key, []).append({"mod": mod_name, "file": relative_file})
                    for property_name, property_value in properties.items():
                        property_key = f"{target_key}|{property_name}"
                        property_writes.setdefault(property_key, []).append(
                            {"mod": mod_name, "file": relative_file, "is_array": isinstance(property_value, list)})

    lines = ["RuneSchema compatibility report", "Load order: " + " -> ".join(ordered_mod_names), ""]
    warning_count = 0

    def different_mods(sites: list[dict]) -> bool:
        return len({site["mod"] for site in sites}) > 1

    if settings.get("warnSameTarget", True):
        for key in sorted(target_writes):
            sites = target_writes[key]
            if not different_mods(sites):
                continue
            warning_count += 1
            lines.append(f"[TARGET] {key}")
            for site in sites:
                lines.append(f"  - {site['mod']} ({site['file']})")

    warn_same_property = settings.get("warnSameProperty", True)
    warn_array_replacement = settings.get("warnArrayReplacement", True)
    if warn_same_property or warn_array_replacement:
        for key in sorted(property_writes):
            sites = property_writes[key]
            if not different_mods(sites):
                continue
            array_replacement = any(site["is_array"] for site in sites)
            if (not array_replacement and not warn_same_property) or \
               (array_replacement and not warn_same_property and not warn_array_replacement):
                continue
            warning_count += 1
            label = "[ARRAY]" if (array_replacement and warn_array_replacement) else "[PROPERTY]"
            lines.append(f"{label} {key}")
            for site in sites:
                lines.append(f"  - {site['mod']} ({site['file']})")

    if warning_count == 0:
        lines.append("No cross-mod target or property conflicts found.")

    report_text = "\n".join(lines) + "\n"
    written_path = None
    if settings.get("writeFile", True):
        config_dir = mods_root.parent / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        report_path = config_dir / "compatibility_report.txt"
        tmp = report_path.with_suffix(report_path.suffix + ".tmp")
        tmp.write_text(report_text, encoding="utf-8")
        os.replace(tmp, report_path)
        written_path = str(report_path)

    return {"generated": True, "report": report_text, "warning_count": warning_count, "path": written_path}


# --------------------------------------------------------------------------
# FModel snippet generator -- port of FModelSnippetGenerator.cpp
# --------------------------------------------------------------------------

def _sanitize_value(value):
    if isinstance(value, dict):
        return {name: _sanitize_value(child) for name, child in value.items() if not _is_unsafe_property(name)}
    if isinstance(value, list):
        return [_sanitize_value(child) for child in value]
    return value


def _safe_properties(properties) -> dict:
    if not isinstance(properties, dict):
        return {}
    return {name: _sanitize_value(value) for name, value in properties.items() if not _is_unsafe_property(name)}


def _extract_object_name(reference) -> str:
    if not isinstance(reference, dict):
        return ""
    value = reference.get("ObjectName")
    if not isinstance(value, str):
        return ""
    first = value.find("'")
    last = value.rfind("'")
    if first != -1 and last > first:
        return value[first + 1:last]
    return value


def _generate_snippet(input_path: Path) -> dict | None:
    exports = _parse_jsonc(input_path.read_text(encoding="utf-8", errors="replace"))
    if not isinstance(exports, list):
        return None

    blueprint_class = next(
        (entry for entry in exports if isinstance(entry, dict) and entry.get("Type") == "BlueprintGeneratedClass"),
        None,
    )

    snippet: dict = {"$generated": "Review and remove unwanted properties before moving this file into a mod loader folder."}

    if blueprint_class is not None:
        class_name = blueprint_class.get("Name", "")
        cdo_name = _extract_object_name(blueprint_class.get("ClassDefaultObject", {}))
        cdo = next((entry for entry in exports if isinstance(entry, dict) and entry.get("Name") == cdo_name), None)
        if not class_name or cdo is None or not isinstance(cdo.get("Properties"), dict):
            return None

        properties = _safe_properties(cdo["Properties"])
        for entry in exports:
            if not isinstance(entry, dict) or "Outer" not in entry or "Properties" not in entry:
                continue
            if _extract_object_name(entry.get("Outer")) == cdo_name:
                component_name = entry.get("Name", "")
                if component_name and not _is_unsafe_property(component_name):
                    properties[component_name] = _safe_properties(entry.get("Properties"))
        snippet[class_name] = properties
    else:
        asset = next(
            (entry for entry in exports if isinstance(entry, dict) and isinstance(entry.get("Package"), str)
             and isinstance(entry.get("Properties"), dict)),
            None,
        )
        if asset is None:
            return None
        package = asset["Package"]
        name = asset.get("Name", "")
        target = normalize_object_path(package, name)
        snippet[target] = _safe_properties(asset["Properties"])

    return snippet


def generate_fmodel_snippets(runeschema_config_root: Path) -> dict:
    """Port of PS::FModelSnippetGenerator::GenerateConfiguredInputs().

    ``runeschema_config_root`` is RuneSchema's ``config`` folder; reads from
    its ``fmodel-input`` subfolder and writes to ``fmodel-snippets``.
    """
    input_dir = runeschema_config_root / "fmodel-input"
    output_dir = runeschema_config_root / "fmodel-snippets"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    generated = 0
    skipped: list[str] = []
    for entry in sorted(input_dir.iterdir(), key=lambda p: p.name):
        if not entry.is_file() or entry.suffix.lower() not in (".json", ".jsonc"):
            continue
        try:
            snippet = _generate_snippet(entry)
        except (json.JSONDecodeError, ValueError, OSError):
            skipped.append(entry.name)
            continue
        if snippet is None:
            skipped.append(entry.name)
            continue
        destination = output_dir / f"{entry.stem}.runeschema.json"
        tmp = destination.with_suffix(destination.suffix + ".tmp")
        tmp.write_text(json.dumps(snippet, indent=2), encoding="utf-8")
        os.replace(tmp, destination)
        generated += 1

    return {"generated": generated, "skipped": skipped, "input_path": str(input_dir), "output_path": str(output_dir)}
