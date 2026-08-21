# Alpha 11 Verification

## Automated source regression suite

Run:

```bat
npm run verify
```

The build pipeline runs this automatically after installing dependencies. The Python regression runner covers:

- positive World identity and sync safety;
- server engine/World activation;
- server publish/auth/HMAC/runtime behavior;
- managed config/hotload/client-sync policy;
- Player ID → `DedicatedServer.ini` (`OwnerId` + `OwnerID`);
- dynamic `mods.txt` exclusions;
- Client Generate Last and Server Push writer contracts;
- server-only PlayerTracker/client-only Direct Connect contracts;
- SinglePlayer profile/mod/character behavior;
- UE4SS extraction/removal of embedded `enabled.txt`;
- family-local UE4SS order;
- physical PAK numeric prefixes;
- RuneSchema no-order and embedded-PAK preservation;
- `.rsdwl` starter-character storage;
- build-script/packaging contracts.

JavaScript syntax checks cover renderer, Electron main/preload and Discord IPC transport.

## Windows `build.bat` release gates

A release is accepted only after all of the following succeed:

1. Python/Node/npm toolchain discovery.
2. Required resources/source files found.
3. Pinned Python and Node build dependencies installed or version-verified.
4. Monaco prepared locally and full verification suite green.
5. PyInstaller service build succeeds.
6. Packaged `DragonwildsSync.Service.exe` answers `state.get` over real stdin/stdout JSON-RPC.
7. electron-builder emits Windows EXE artifacts.
8. Packaged `app.asar` contains Monaco `vs/loader.js` and worker runtime.
9. `win-unpacked` contains PlayerTracker `Scripts/main.lua`, PlayerTracker blank `enabled.txt`, and Direct Connect companion ZIP.

## Manual Windows acceptance checklist

- Run `build.bat` from Explorer and from an editor terminal; confirm both produce the same `release` artifacts.
- First-run Player setup resolves the retail game.
- Enable Server mode; verify setup requests Player ID and Full Setup refuses an empty ID.
- Confirm generated `DedicatedServer.ini` contains matching `OwnerId` and `OwnerID`, then confirm it is read-only outside the launcher.
- Create/activate a hosted World; edit a JSON config in Monaco and verify invalid JSON is rejected, valid save is atomic, and the file remains read-only after save.
- Mark a safe config Synchronize to Client; publish/sync and confirm the client copy arrives read-only. Confirm `DedicatedServer.ini` is absent from client payloads.
- Configure scheduled Restart and Update + Restart at an exact time and interval; verify notification center warnings.
- Drop two UE4SS ZIPs containing `enabled.txt`; confirm extraction removes the markers, reorder them, and confirm `mods.txt` order changes.
- Switch client `mods.txt` writer between Client Generates Last and Server Pushes File; confirm identical selected explicit mod order and no self-enabled infrastructure entries.
- Drop two normal PAK ZIPs; reorder and confirm `01_`/`02_` filenames change physically.
- Drop a RuneSchema ZIP containing JSON/script/internal PAK; confirm the whole mod remains beneath `RuneSchema/mods/<mod>` with no numeric prefix.
- Open SinglePlayer; assign a character, configure independent mods, Play, then switch to a remote World and back to verify character/mod snapshots.
- Export/import `.rsdwl`; confirm safety backup before overwrite.
- Add a starter `.rsdwl` to a hosted World, publish, view it from a client placard, and explicitly import it.
- Confirm PlayerTracker exists only on the hosted server and Direct Connect only on the player installation.
- Confirm World Ping / Refresh Metadata updates presentation/status without performing file sync.
