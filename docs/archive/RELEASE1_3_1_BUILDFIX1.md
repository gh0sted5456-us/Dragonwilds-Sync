# Dragonwilds Sync Release 1.3.1 — BuildFix1

This build-fix addresses a real Windows packaging regression reported from `build_windows.ps1`.

`electron-builder` successfully produced both the NSIS installer and portable executable, then the build wrapper incorrectly returned `BUILD FAILED` during final resource verification because `$bundledRuneSchema` had never been initialized before `Test-Path`. The script now resolves the bundled RuneSchema path explicitly before verifying the packaged copy.

No application/profile/package format changes are introduced by this build fix.
