from __future__ import annotations

import re
from pathlib import Path


PAK_EXTENSIONS = {".pak", ".utoc", ".ucas"}
_LOAD_PREFIX = re.compile(r"^\d{2,3}_(.+)$")


def _visible(path: Path) -> list[Path]:
    try:
        return [item for item in path.iterdir() if not item.name.startswith(".")]
    except OSError:
        return []


def peel_wrappers(root: Path) -> tuple[Path, str | None]:
    """Peel arbitrary packaging wrappers without crossing a payload boundary."""
    current = root
    wrapper = None
    payload_names = {"scripts", "raw", "ue4ss", "mods", "content", "binaries", "runeschema"}
    for _ in range(16):
        entries = _visible(current)
        names = {entry.name.casefold() for entry in entries}
        if any(entry.is_file() for entry in entries) or names.intersection(payload_names):
            break
        if len(entries) != 1 or not entries[0].is_dir():
            break
        current = entries[0]
        wrapper = current.name
    return current, wrapper


def _single(candidates: list[Path], label: str) -> Path | None:
    unique: dict[str, Path] = {}
    for candidate in candidates:
        if candidate.is_dir():
            unique[str(candidate.resolve()).casefold()] = candidate
    candidates = list(unique.values())
    leaves = [item for item in candidates if not any(item != other and item in other.parents for other in candidates)]
    if len(leaves) == 1:
        return leaves[0]
    if len(leaves) > 1:
        names = ", ".join(item.name for item in sorted(leaves, key=lambda p: str(p).casefold())[:6])
        raise ValueError(f"The archive contains multiple {label} payloads ({names}). Import one mod at a time.")
    return None


def _dedupe(candidates: list[Path]) -> list[Path]:
    unique: dict[str, Path] = {}
    for candidate in candidates:
        if candidate.is_dir():
            unique[str(candidate.resolve()).casefold()] = candidate
    return sorted(unique.values(), key=lambda item: str(item).casefold())


def inspect_mod_payloads(root: Path) -> list[dict]:
    """Return independently assignable payloads found in an extracted archive."""
    found: list[dict] = []
    directories = [root, *[item for item in root.rglob("*") if item.is_dir()]]

    explicit_ue: list[Path] = []
    explicit_rs: list[Path] = []
    for mods in [item for item in directories if item.name.casefold() == "mods"]:
        children = [item for item in _visible(mods) if item.is_dir()]
        if mods.parent.name.casefold() == "ue4ss":
            explicit_ue.extend(children)
        elif mods.parent.name.casefold() == "runeschema":
            explicit_rs.extend(children)

    ue = explicit_ue or [item.parent.parent for item in root.rglob("main.lua") if item.parent.name.casefold() == "scripts"]
    rs = explicit_rs or [item for item in directories if (item / "raw").is_dir()
                         and any(p.suffix.casefold() == ".json" for p in (item / "raw").rglob("*"))]
    for kind, candidates in (("ue4ss", ue), ("runeschema", rs)):
        for content in _dedupe(candidates):
            # Explicit RuneSchema ancestry wins over a Lua script embedded in a
            # RuneSchema mod; never offer the same payload twice.
            if kind == "ue4ss" and any(parent.name.casefold() == "runeschema" for parent in content.parents):
                continue
            relative = content.relative_to(root).as_posix()
            manifest = next((item.name for item in (content / "manifest.json", content / "ID.txt") if item.is_file()), "")
            found.append({"id": f"{kind}:{relative}", "kind": kind, "name": content.name,
                          "payload_root": relative, "manifest": manifest, "selected": True})

    pak_files = [item for item in root.rglob("*") if item.is_file() and item.suffix.casefold() in PAK_EXTENSIONS]
    groups: dict[tuple[str, str], list[Path]] = {}
    for item in pak_files:
        if any(candidate == item or candidate in item.parents for candidate in explicit_rs):
            continue
        match = _LOAD_PREFIX.match(item.stem)
        stem = (match.group(1) if match else item.stem)
        groups.setdefault((item.parent.relative_to(root).as_posix(), stem.casefold()), []).append(item)
    for (relative, _stem), files in sorted(groups.items()):
        first = files[0]
        match = _LOAD_PREFIX.match(first.stem)
        name = match.group(1) if match else first.stem
        found.append({"id": f"paks:{relative}:{name}", "kind": "paks", "name": name,
                      "payload_root": relative, "payload_name": name,
                      "manifest": "manifest.json" if (first.parent / "manifest.json").is_file() else "", "selected": True})
    return found


def locate_mod_payload(root: Path, kind: str, fallback_name: str, *, payload_root: str = "", payload_name: str = "") -> dict:
    """Find one coherent mod payload inside an otherwise arbitrary ZIP tree."""
    kind = str(kind or "").casefold()
    if payload_root:
        pure = Path(str(payload_root).replace("\\", "/"))
        if pure.is_absolute() or ".." in pure.parts:
            raise ValueError("Unsafe mod payload selection.")
        selected = (root / pure).resolve()
        resolved_root = root.resolve()
        if selected != resolved_root and resolved_root not in selected.parents:
            raise ValueError("Mod payload selection escapes the archive.")
        if not selected.is_dir():
            raise ValueError("The selected mod payload is no longer present in the archive.")
        if kind == "paks":
            wanted = str(payload_name or "").casefold()
            files = []
            for item in selected.iterdir():
                if not item.is_file() or item.suffix.casefold() not in PAK_EXTENSIONS:
                    continue
                match = _LOAD_PREFIX.match(item.stem)
                clean = (match.group(1) if match else item.stem).casefold()
                if not wanted or clean == wanted:
                    files.append(item)
            if not files:
                raise ValueError("The selected PAK group is empty.")
            first = files[0]
            match = _LOAD_PREFIX.match(first.stem)
            name = match.group(1) if match else first.stem
            return {"content": selected, "name": name, "files": files,
                    "manifest": str(selected / "manifest.json") if (selected / "manifest.json").is_file() else ""}
        return {"content": selected, "name": selected.name,
                "manifest": next((str(item) for item in (selected / "manifest.json", selected / "ID.txt") if item.is_file()), "")}
    peeled, wrapper = peel_wrappers(root)
    fallback = wrapper or Path(fallback_name).stem or "ImportedMod"

    if kind == "ue4ss":
        explicit: list[Path] = []
        directories = [peeled, *[item for item in peeled.rglob("*") if item.is_dir()]]
        for mods in [item for item in directories if item.name.casefold() == "mods"]:
            if mods.parent.name.casefold() == "ue4ss" or mods == peeled / "Mods":
                explicit.extend(item for item in _visible(mods) if item.is_dir())
        scripts = [item.parent.parent for item in peeled.rglob("main.lua") if item.parent.name.casefold() == "scripts"]
        content = _single(explicit, "UE4SS mod") or _single(scripts, "UE4SS mod") or peeled
        return {"content": content, "name": content.name if content != peeled else fallback,
                "manifest": next((str(item) for item in (content / "manifest.json", content / "ID.txt") if item.is_file()), "")}

    if kind == "runeschema":
        explicit: list[Path] = []
        directories = [peeled, *[item for item in peeled.rglob("*") if item.is_dir()]]
        for mods in [item for item in directories if item.name.casefold() == "mods" and item.parent.name.casefold() == "runeschema"]:
            explicit.extend(item for item in _visible(mods) if item.is_dir())
        raw_roots = [item.parent for item in directories if item.name.casefold() == "raw"
                     and any(p.suffix.casefold() == ".json" for p in item.rglob("*"))]
        manifest_roots = [item.parent for item in peeled.rglob("manifest.json")
                          if any(p.suffix.casefold() == ".json" and p != item for p in item.parent.rglob("*"))]
        content = _single(explicit, "RuneSchema mod") or _single(raw_roots, "RuneSchema mod") or _single(manifest_roots, "RuneSchema mod") or peeled
        return {"content": content, "name": content.name if content != peeled else fallback,
                "manifest": next((str(item) for item in (content / "manifest.json", content / "ID.txt") if item.is_file()), "")}

    if kind == "paks":
        files = [item for item in peeled.rglob("*") if item.is_file() and item.suffix.casefold() in PAK_EXTENSIONS]
        groups: dict[tuple[str, str], list[Path]] = {}
        for item in files:
            match = _LOAD_PREFIX.match(item.stem)
            stem = (match.group(1) if match else item.stem).casefold()
            groups.setdefault((str(item.parent.resolve()).casefold(), stem), []).append(item)
        if len(groups) != 1:
            if not groups:
                raise ValueError("No .pak/.utoc/.ucas payload was found in this archive.")
            raise ValueError("The archive contains multiple PAK payload groups. Import one mod at a time.")
        (_parent, _stem), package_files = next(iter(groups.items()))
        first = package_files[0]
        match = _LOAD_PREFIX.match(first.stem)
        return {"content": first.parent, "name": match.group(1) if match else first.stem,
                "files": sorted(package_files, key=lambda item: item.suffix.casefold()),
                "manifest": str(first.parent / "manifest.json") if (first.parent / "manifest.json").is_file() else ""}

    raise ValueError("Unsupported mod archive type.")
