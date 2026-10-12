# Alpha 3.1 Build Fix

## Failure reproduced from the August 12 build log

The build reached `[3/7] Build dependencies` and launched:

`npm install --no-audit --no-fund`

npm then printed the normal `inflight@1.0.6` deprecation warning on **stderr**. Windows PowerShell 5.1 converted that native stderr record into a PowerShell error record. Because the build script intentionally runs with `$ErrorActionPreference = 'Stop'`, PowerShell aborted the pipeline before npm could finish, even though the warning itself did not mean npm had failed.

## Fix

`Invoke-Native` now temporarily uses `ErrorActionPreference = 'Continue'` only while a native process is running and its stdout/stderr are being captured. The original preference is restored immediately afterward.

Native commands are now considered failed **only when their process exit code is non-zero**. Warnings and informational diagnostics on stderr are still written to `build.log`, but they no longer cause false build failures.

## Regression coverage

`backend/test_build_contract.py` now checks that the native runner contains this Windows PowerShell 5.1 stderr guard and remains exit-code driven.
