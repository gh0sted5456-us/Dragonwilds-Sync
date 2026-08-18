from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def patch_service() -> None:
    path = "backend/dragonwilds_service.py"
    text = read(path)
    text = text.replace(
        '    if method == "security.defender.status":\n        return defender_status()\n',
        '    if method == "security.defender.status":\n        return {"available": False, "enabled": False, "retired": True, "reason": "Microsoft Defender integration is not used by Dragonwilds Sync."}\n',
    )
    text = text.replace(
        '    if method in ("security.defender.scan", "server.maintenance.defender_scan"):\n        return defender_scan(str(params.get("path") or ""))\n',
        '    if method in ("security.defender.scan", "server.maintenance.defender_scan"):\n        return {"available": False, "enabled": False, "blocked": False, "skipped": True, "retired": True, "reason": "Microsoft Defender integration is not used by Dragonwilds Sync."}\n',
    )
    write(path, text)


def patch_server_systems() -> None:
    path = "backend/server_systems.py"
    text = read(path)
    text = text.replace(
        '        defender_state = defender_status()\n        security_reviews = []\n        for unit in required:\n            security_reviews.extend(review_mod_unit_with_defender(unit))\n',
        '        security_reviews = []\n',
    )
    defender_block = '''                              "security_posture": {
                                  "defender": {
                                      "available": bool(defender_state.get("available")), "enabled": bool(defender_state.get("enabled")),
                                      "mode": defender_state.get("mode") or "", "signature_version": defender_state.get("signature_version") or "",
                                      "checked_at": defender_state.get("checked_at"),
                                  },
                                  "reviewed_units": len({r.get("unit_key") for r in security_reviews}),
                                  "skipped_reviews": sum(1 for r in security_reviews if r.get("skipped")),
                              },
'''
    text = text.replace(defender_block, '                              "security_posture": {"package_validation": "hash-staging-rollback"},\n')

    match = re.search(r'def clear_server_mods\(game_root: str\) -> dict:\n.*?(?=\n\ndef )', text, re.S)
    if not match:
        raise RuntimeError("clear_server_mods function not found")
    block = match.group(0)
    block = block.replace('"""Clear profile mods while retaining RuneSchema core, UE4SS core and mods.txt."""',
                          '"""Clear profile mods while retaining RuneSchema, RSDWTools, UE4SS core and mods.txt."""')
    # Cover the historical variants used by this function without touching any
    # unrelated directory iteration elsewhere in the server engine.
    variants = (
        ('if child.name.lower() == "runeschema":', 'if child.name.lower() in {"runeschema", "rsdwtools"}:'),
        ('if child.name.casefold() == "runeschema":', 'if child.name.casefold() in {"runeschema", "rsdwtools"}:'),
        ('if path.name.lower() == "runeschema":', 'if path.name.lower() in {"runeschema", "rsdwtools"}:'),
        ('if path.name.casefold() == "runeschema":', 'if path.name.casefold() in {"runeschema", "rsdwtools"}:'),
    )
    for old, new in variants:
        block = block.replace(old, new)
    if "rsdwtools" not in block.casefold():
        # Last-resort insertion: preserve an RSDWTools directory before any
        # normal child removal inside the UE4SS Mods root.
        loop = re.search(r'(for\s+\w+\s+in\s+mods_root\.iterdir\(\):\n)', block)
        if not loop:
            raise RuntimeError("Could not identify Clear Mods UE4SS loop")
        var = re.search(r'for\s+(\w+)\s+in\s+mods_root\.iterdir', loop.group(1)).group(1)
        insertion = loop.group(1) + f'        if {var}.name.casefold() in {{"runeschema", "rsdwtools"}}:\n            continue\n'
        block = block[:loop.start()] + insertion + block[loop.end():]
    text = text[:match.start()] + block + text[match.end():]

    # No active Defender probe remains in the publish path. Keep helper imports
    # only if some older compatibility code still references them.
    if "defender_status(" not in text and "defender_scan(" not in text:
        text = text.replace('from security_scanner import defender_scan, defender_status\n', '')
    write(path, text)


def patch_renderer() -> None:
    path = "renderer/app.js"
    text = read(path)
    text = text.replace("      const scan=await api.invoke('server.maintenance.defender_scan',{path:zipPath}); if(scan.available&&scan.clean===false)throw new Error('Microsoft Defender blocked this archive.');\n", "")
    text = text.replace("    const scan=await api.invoke('server.maintenance.defender_scan',{path:zipPath});\n    if(scan.available&&scan.clean===false) throw new Error('Microsoft Defender reported a problem with this ZIP.');\n", "")
    write(path, text)

    polish_path = "renderer/release-polish.js"
    polish = read(polish_path)
    old = '''      if(kind==='server') api.openDetachedWindow?.({route:'server-detail',title:'Dragonwilds Sync · Server Mods',context:{selectedServerWorldId:id,serverTab:'mods'},width:1240,height:820});
      else api.openDetachedWindow?.({route:'world-detail',title:'Dragonwilds Sync · Private World Mods',context:{selectedWorldId:id,privateTab:'mods'},width:1240,height:820});'''
    new = '''      const route=kind==='server'?'servers':'worlds';
      const nav=document.querySelector(`[data-route="${route}"],[data-nav-route="${route}"]`);
      nav?.click();
      setTimeout(()=>{
        const card=[...document.querySelectorAll('[data-world-id]')].find((node)=>String(node.dataset.worldId||'')===String(id));
        const manage=[...card?.querySelectorAll('button')||[]].find((node)=>/manage|details|open/i.test(node.textContent||''));
        manage?.click();
      },60);'''
    if old in polish:
        polish = polish.replace(old, new, 1)
    polish = polish.replace('Open Mod Manager</button>', 'Manage Mods</button>')
    write(polish_path, polish)


def write_test() -> None:
    path = ROOT / "backend" / "test_rc2_followup.py"
    path.write_text('''from pathlib import Path\nROOT=Path(__file__).resolve().parent.parent\n\ndef main():\n    service=(ROOT/"backend/dragonwilds_service.py").read_text(encoding="utf-8")\n    systems=(ROOT/"backend/server_systems.py").read_text(encoding="utf-8")\n    app=(ROOT/"renderer/app.js").read_text(encoding="utf-8")\n    polish=(ROOT/"renderer/release-polish.js").read_text(encoding="utf-8")\n    clear=systems[systems.index("def clear_server_mods"):systems.index("\\ndef ", systems.index("def clear_server_mods")+4)]\n    assert "return defender_scan" not in service\n    assert "defender_state = defender_status()" not in systems\n    assert '\"defender\": {' not in systems\n    assert "server.maintenance.defender_scan" not in app\n    assert "rsdwtools" in clear.casefold()\n    assert "openDetachedWindow?.({route:'server-detail'" not in polish\n    assert "openDetachedWindow?.({route:'world-detail'" not in polish\n    print("RC2 follow-up contract passed")\n\nif __name__=="__main__": main()\n''', encoding="utf-8")
    runner_path = ROOT / "scripts" / "run_backend_tests.cjs"
    runner = runner_path.read_text(encoding="utf-8")
    if "backend/test_rc2_followup.py" not in runner:
        runner = runner.replace("  'backend/test_rc2_feedback.py',\n", "  'backend/test_rc2_feedback.py',\n  'backend/test_rc2_followup.py',\n")
        runner_path.write_text(runner, encoding="utf-8")


def main() -> None:
    patch_service()
    patch_server_systems()
    patch_renderer()
    write_test()
    print("RC2 follow-up applied")


if __name__ == "__main__":
    main()
