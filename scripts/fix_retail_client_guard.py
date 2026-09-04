from pathlib import Path

path = Path(__file__).with_name("apply_curated_claude_guards.py")
text = path.read_text(encoding="utf-8")
old = '''    if "def looks_like_retail_client(" not in text:
        anchor = "\\ndef discover_server_layouts(selected: str | Path, *, max_depth: int = 8,\\n"
        func = ''' + "'''" + '''

def looks_like_retail_client(layout: ServerLayout) -> bool:
    """Identify a retail client tree when server code is about to write to it."""
    if is_complete_server_layout(layout):
        return False
    if _has_dedicated_evidence(layout.install_root) or _has_dedicated_evidence(layout.game_root):
        return False
    return (layout.game_root / "Binaries" / "Win64" / CLIENT_SHIPPING_EXE).is_file()
''' + "'''" + '''
        if anchor not in text:
            raise RuntimeError("server_layout discover anchor missing")
        text = text.replace(anchor, func + anchor, 1)
'''
new = '''    if "def looks_like_retail_client(" not in text:
        anchor = "\\ndef discover_server_layouts(selected: str | Path, *, max_depth: int = 8,\\n"
        func = ''' + "'''" + '''

def looks_like_retail_client(layout: ServerLayout) -> bool:
    """Identify positive retail-client evidence without trusting planned server paths.

    ``resolve_server_layout`` intentionally maps an unrecognized selection toward
    the location Full Setup *would* create. For a safety guard we instead inspect
    the operator-selected tree itself (and its normal nested RSDragonwilds root).
    """
    selected = layout.selected_root.parent if layout.selected_root.is_file() else layout.selected_root
    roots = (selected, selected / "RSDragonwilds")
    if any(_has_dedicated_evidence(root) for root in roots):
        return False
    return any((root / "Binaries" / "Win64" / CLIENT_SHIPPING_EXE).is_file() for root in roots)
''' + "'''" + '''
        if anchor not in text:
            raise RuntimeError("server_layout discover anchor missing")
        text = text.replace(anchor, func + anchor, 1)
'''
if text.count(old) != 1:
    raise RuntimeError(f"retail guard staging block expected once, found {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("Retail client guard now inspects the selected tree, not the planned SteamCMD destination.")
