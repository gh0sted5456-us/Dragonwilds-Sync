# Alpha 5 Verification

## Automated source verification

The repository verification command is:

```text
npm run verify
```

It covers:

- Electron main/preload and renderer JavaScript syntax.
- Positive World identity and smart-route rules.
- Client sync path safety and safe extraction.
- Hosted-World activation, mod/save snapshots and process guards.
- Server HMAC/publication/runtime behavior.
- Defender/access-policy behavior.
- Health scoring and version-currency invariants.
- Alpha 5 runtime build parsing and World-maintenance JSON semantics.
- Read-only managed-file locking, valid save, invalid JSON rejection and path traversal rejection.
- Client-facing suppression of UE4SS/RuneSchema core plumbing.
- Service World isolation.
- Windows build contract, including frozen-service path and hidden-console requirements.

## Windows release verification still required

This development environment cannot execute the real Windows PyInstaller + Electron Builder pipeline. On a Windows test machine:

1. Extract Alpha 5 into a fresh folder.
2. Run `build.bat`.
3. Confirm `release\` contains the portable EXE and NSIS installer.
4. Launch the portable build and verify no command prompt appears when opening/selecting World placards.
5. In Settings → Server, set a test server directory/EXE and exercise Full Setup, Firewall and Update Server only on a disposable/test host.
6. Activate a test World, open a JSON config in Maintenance, confirm the live file becomes read-only, save valid JSON, then Release Lock and confirm it becomes writable again.
7. Confirm the client mod view defaults to Client Required and never shows `dwmapi.dll`, `mods.txt`, the UE4SS core unit or RuneSchema core as user mods.
8. Confirm runtime-stack/version labels populate when Steam/GitHub data is reachable and degrade to unknown/missing evidence rather than blocking the launcher when it is not.
