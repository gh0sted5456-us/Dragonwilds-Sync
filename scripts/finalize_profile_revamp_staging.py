from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str, label: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    replace_once(
        "backend/server_engine.py",
        'SERVER_INFRASTRUCTURE_UE4SS = {"runeschema", "dragonlink", *UE4SS_BAKED_IN_DEFAULT_MODS}',
        'SERVER_INFRASTRUCTURE_UE4SS = {"runeschema", "dragonlink", "mods.txt", *UE4SS_BAKED_IN_DEFAULT_MODS}',
        "server generated control exclusion",
    )
    replace_once(
        "backend/sync_engine.py",
        'LAUNCHER_LOCAL_UE4SS_MODS = {"runeschema", "runeschema.zip", "rsdwtools", "dragonlink"} | UE4SS_BAKED_IN_DEFAULT_MODS',
        'LAUNCHER_LOCAL_UE4SS_MODS = {"runeschema", "runeschema.zip", "rsdwtools", "dragonlink", "mods.txt"} | UE4SS_BAKED_IN_DEFAULT_MODS',
        "client generated control exclusion",
    )
    print("Generated UE4SS control files excluded from profile storage.")


if __name__ == "__main__":
    main()
