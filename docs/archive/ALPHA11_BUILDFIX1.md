# Alpha 11.1 BuildFix1

## Failure fixed

The Alpha 11 Windows build stopped during `npm run prepare:monaco` because the project pinned `monaco-editor 0.56.0` while the renderer still uses Monaco's AMD loader/runtime layout (`min/vs/loader.js`, `editor.main.js`, and `base/worker/workerMain.js`).

## Correction

- Pin `monaco-editor` to `0.52.2`, the compatible 0.52.x AMD line used by the current renderer integration.
- `prepare_monaco.cjs` validates the installed Monaco version before copying files.
- It validates all three required runtime files before and after the copy.
- The Windows build re-checks all pinned Node dependency versions after dependency installation.
- Packaged `app.asar` still must contain `loader.js` and `workerMain.js`; the gate was retained rather than weakened.

This is a builder/runtime compatibility fix only. Alpha 11 gameplay/profile/server/SinglePlayer/character/mod-management behavior is retained.
