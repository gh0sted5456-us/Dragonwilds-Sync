# Alpha 3.2 Build Fix

## Exact failure fixed

Alpha 2 BuildFix1 reached the PyInstaller stage and failed with:

`ERROR: script '<project>\dragonwilds_service.py' not found`

The service actually lives at `backend\dragonwilds_service.py`. The old spec treated `SPECPATH` as though it were the spec filename and called `.parent`; on the affected PyInstaller version `SPECPATH` is already the directory containing the spec. That moved resolution one directory too high.

## Fix

`backend/DragonwildsSync.Service.spec` now anchors directly to:

`backend = Path(SPECPATH).resolve()`

The PyInstaller entry point therefore resolves to `backend/dragonwilds_service.py` regardless of the directory from which the root BAT was launched.

The Windows launcher also preflights the PowerShell build script, service entry point, and spec before invoking the build. It pauses on both success and failure by default, and opens `release/` after a successful build. Pass `--no-pause` only for CI or scripted use.

## Regression coverage

`backend/test_build_contract.py` now explicitly rejects `Path(SPECPATH).resolve().parent` and requires the service entry point to remain under `backend/`. This is in addition to the existing PowerShell 5.1 stderr/exit-code regression checks.
