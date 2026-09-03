from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "renderer" / "app-v2.js"
OVERLAY_PATH = ROOT / "renderer" / "release-profile-mod-folders.js"


class CleanupError(RuntimeError):
    pass


def require_count(text: str, needle: str, expected: int, label: str) -> None:
    actual = text.count(needle)
    if actual != expected:
        raise CleanupError(f"{label}: expected {expected} occurrence(s), found {actual}")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    require_count(text, old, 1, label)
    return text.replace(old, new, 1)


def regex_replace_once(text: str, pattern: str, replacement: str, label: str, *, flags: int = 0) -> str:
    compiled = re.compile(pattern, flags)
    matches = list(compiled.finditer(text))
    if len(matches) != 1:
        raise CleanupError(f"{label}: expected 1 match, found {len(matches)}")
    return compiled.sub(replacement, text, count=1)


def matching_brace(source: str, opening: int) -> int:
    if source[opening] != "{":
        raise CleanupError("brace scanner did not start on an opening brace")
    depth = 0
    state = "normal"
    i = opening
    while i < len(source):
        char = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else ""
        if state == "line_comment":
            if char in "\r\n":
                state = "normal"
        elif state == "block_comment":
            if char == "*" and nxt == "/":
                state = "normal"
                i += 1
        elif state in {"single", "double", "template"}:
            quote = {"single": "'", "double": '"', "template": "`"}[state]
            if char == "\\":
                i += 1
            elif char == quote:
                state = "normal"
        else:
            if char == "/" and nxt == "/":
                state = "line_comment"
                i += 1
            elif char == "/" and nxt == "*":
                state = "block_comment"
                i += 1
            elif char == "'":
                state = "single"
            elif char == '"':
                state = "double"
            elif char == "`":
                state = "template"
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return i
                if depth < 0:
                    raise CleanupError("brace depth became negative")
        i += 1
    raise CleanupError("matching closing brace was not found")


def remove_named_js_function(source: str, name: str, label: str) -> str:
    pattern = re.compile(rf"(?m)^  (?:async )?function {re.escape(name)}\(")
    matches = list(pattern.finditer(source))
    if len(matches) != 1:
        raise CleanupError(f"{label}: expected one function named {name}, found {len(matches)}")
    start = matches[0].start()
    opening = source.find("{", matches[0].end())
    if opening < 0:
        raise CleanupError(f"{label}: opening brace not found")
    end = matching_brace(source, opening) + 1
    while end < len(source) and source[end] in " \t":
        end += 1
    newline_count = 0
    while end < len(source) and source[end] in "\r\n" and newline_count < 4:
        if source[end] == "\n":
            newline_count += 1
        end += 1
    return source[:start] + source[end:]


def replace_element_by_id(source: str, tag: str, element_id: str, replacement: str, label: str) -> str:
    pattern = rf'<{tag}\b(?=[^>]*\bid="{re.escape(element_id)}")[^>]*>.*?</{tag}>'
    return regex_replace_once(source, pattern, replacement, label, flags=re.DOTALL)


def clean_app(source: str) -> str:
    for name in ("installSinglePlayerZip", "installServerZip", "openSmartModImport", "bindModDropZone"):
        source = remove_named_js_function(source, name, f"remove {name}")

    source = replace_element_by_id(
        source,
        "button",
        "sp-install-mod",
        '<button class="btn ghost" id="sp-open-mods-folder">Open Mods Folder</button>',
        "replace Private World manual import button",
    )
    source = replace_element_by_id(
        source,
        "div",
        "sp-mod-dropzone",
        '<div class="identity-box profile-mod-folder-note" data-profile-mod-folder-note="local"><strong>Folder-managed mods</strong><p>Open this World profile’s Mods folder, add, remove, or replace files in Explorer, then Rescan. Dragonwilds Sync identifies additions, changes, and removals from the profile folder itself.</p></div>',
        "replace Private World ZIP drop zone",
    )
    source = replace_element_by_id(
        source,
        "button",
        "install-server-mod-zip",
        '<button class="btn ghost" id="server-open-mods-folder">Open Mods Folder</button>',
        "replace server manual import button",
    )
    source = replace_element_by_id(
        source,
        "div",
        "server-mod-dropzone",
        "",
        "remove server ZIP drop zone",
    )

    source = replace_once(
        source,
        "    root.querySelector('#sp-install-mod')?.addEventListener('click',async()=>{const zipPath=await window.dragonwilds.pickFile('zip');if(!zipPath)return;try{await openSmartModImport(zipPath,'singleplayer');}catch(error){toast('Mod inspection failed',error.message,'error');}});\n",
        "",
        "remove Private World manual import binding",
    )
    source = replace_once(
        source,
        "    root.querySelector('#install-server-mod-zip')?.addEventListener('click', async () => {\n      const zipPath=await window.dragonwilds.pickFile('zip'); if(!zipPath)return;\n      try { await openSmartModImport(zipPath,'server'); } catch(error) { toast('Mod inspection failed',error.message,'error'); }\n    });\n",
        "",
        "remove server manual import binding",
    )
    source = replace_once(
        source,
        "    bindModDropZone(root.querySelector('#sp-mod-dropzone'), (path)=>openSmartModImport(path,'singleplayer'));\n",
        "",
        "remove Private World ZIP drop binding",
    )
    source = replace_once(
        source,
        "    bindModDropZone(root.querySelector('#server-mod-dropzone'), (path)=>openSmartModImport(path,'server'));\n",
        "",
        "remove server ZIP drop binding",
    )

    source = regex_replace_once(
        source,
        r"(?ms)^      if\(kind==='compatibility-mod-archive'\)\{\n.*?^      \}\n",
        "      if(kind==='compatibility-mod-archive'){\n        toast('Manual mod archive import retired','This .rsdwl file is a renamed mod ZIP, not a World manifest. Open the selected World profile’s Mods folder, place the mod in its normal UE4SS, RuneSchema, or PAK structure, then Rescan.','error');\n        return;\n      }\n",
        "retire renamed-ZIP RSDWL installation",
    )

    old_copy = '<div class="identity-box"><strong>Manual + Nexus-linked inventory</strong><p>Each mod can retain Nexus Mod ID, File ID, latest File ID/version evidence and update state without requiring the client to care where the mod came from. Automatic authenticated download remains behind the Nexus adapter boundary.</p></div>'
    new_copy = '<div class="identity-box"><strong>Folder-managed + Nexus-linked inventory</strong><p>Manual mods are read from this World profile’s Mods folder. Nexus Mod ID, File ID, latest version evidence, update state, and rollback history remain attached to discovered mods.</p></div>'
    source = replace_once(source, old_copy, new_copy, "update server inventory help copy")

    forbidden = (
        "openSmartModImport",
        "installSinglePlayerZip",
        "installServerZip",
        "bindModDropZone",
        'id="sp-install-mod"',
        'id="install-server-mod-zip"',
        'id="sp-mod-dropzone"',
        'id="server-mod-dropzone"',
        "Install Manual ZIP",
        "Import Mod Package",
        "confirm-smart-mod-import",
        "Install Manual RSDWL Mod",
    )
    for marker in forbidden:
        if marker in source:
            raise CleanupError(f"legacy renderer marker remains: {marker}")

    required = (
        'id="sp-open-mods-folder"',
        'id="server-open-mods-folder"',
        "profile.package.inspect",
        "profile.package.import",
        "singleplayer.mod.detect",
        "singleplayer.mod.install",
        "server.maintenance.detect_mod_zip",
        "server.world.mod.install",
        "Manual mod archive import retired",
    )
    for marker in required:
        if marker not in source:
            raise CleanupError(f"required supported workflow marker was lost: {marker}")
    return source


def clean_overlay(source: str) -> str:
    source = remove_named_js_function(source, "replaceImportButton", "remove overlay importer replacement")
    source = remove_named_js_function(source, "replaceDropZone", "remove overlay drop-zone replacement")

    insertion = """  function bindProfileFolderButton(selector, kind) {
    const button = document.querySelector(selector);
    if (!button || button.dataset.profileFolderBound === '1') return;
    button.dataset.profileFolderBound = '1';
    button.title = 'Open this World profile’s mod folder in Windows Explorer';
    button.addEventListener('click', () => openProfileMods(kind, button));
  }

"""
    source = replace_once(
        source,
        "  function hardenRuntimeBaselineUi() {\n",
        insertion + "  function hardenRuntimeBaselineUi() {\n",
        "add native profile-folder button binding",
    )

    source = regex_replace_once(
        source,
        r"(?ms)^  function rewriteUi\(\) \{\n.*?^  \}\n\n  function scheduleRewrite\(\) \{",
        "  function rewriteUi() {\n    rewritePending = false;\n    bindProfileFolderButton('#sp-open-mods-folder', 'local');\n    bindProfileFolderButton('#server-open-mods-folder', 'server');\n    hardenRuntimeBaselineUi();\n    refreshFolderHelpCopy();\n  }\n\n  function scheduleRewrite() {",
        "bind native folder controls",
    )

    require_count(source, "refreshLegacyHelpCopy", 1, "legacy help function before rename")
    source = source.replace("refreshLegacyHelpCopy", "refreshFolderHelpCopy", 1)

    forbidden = (
        "replaceImportButton",
        "replaceDropZone",
        "#sp-install-mod",
        "#install-server-mod-zip",
        "#sp-mod-dropzone",
        "#server-mod-dropzone",
        "refreshLegacyHelpCopy",
    )
    for marker in forbidden:
        if marker in source:
            raise CleanupError(f"legacy overlay marker remains: {marker}")
    for marker in ("#sp-open-mods-folder", "#server-open-mods-folder", "bindProfileFolderButton"):
        if marker not in source:
            raise CleanupError(f"required native folder binding missing: {marker}")
    return source


def write_changed(path: Path, content: str) -> None:
    original = path.read_text(encoding="utf-8")
    if original == content:
        raise CleanupError(f"{path.relative_to(ROOT)} did not change")
    path.write_text(content, encoding="utf-8", newline="\n")
    print(f"updated {path.relative_to(ROOT)}: {len(original)} -> {len(content)} bytes")


def main() -> None:
    app = APP_PATH.read_text(encoding="utf-8")
    overlay = OVERLAY_PATH.read_text(encoding="utf-8")
    write_changed(APP_PATH, clean_app(app))
    write_changed(OVERLAY_PATH, clean_overlay(overlay))
    print("legacy manual importer source cleanup complete")


if __name__ == "__main__":
    main()
