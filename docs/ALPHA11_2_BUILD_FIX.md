# Alpha 11.2 BuildFix2

- Fixed PlayerTracker deployment/read-only ownership ordering exposed by Windows service RPC verification.
- UE4SS, RuneSchema, and PlayerTracker are server-machine prerequisites installed/repaired by Full Setup.
- Added editable UE4SS and RuneSchema source URLs under Settings → Server.
- Added Pull / Update and Load ZIP actions plus drag/drop ZIP targets for each runtime.
- Added GitHub repo, releases/latest, release-tag, and direct ZIP resolution for runtime sources.
- Added optional bundled RuneSchema core resource support at `resources/RuneSchema-core-latest.zip`.
- Full Setup still requires Player ID (Owner) and hydrates DedicatedServer.ini.
- World activation verifies/self-heals server runtimes rather than treating PlayerTracker/RuneSchema as World-owned content.

- Pinned PyInstaller 6.22.0 for the Windows/Python 3.14 build path and made the BAT verify/upgrade it before freezing the service.
- Disabled UPX for the JSON-RPC service executable to reduce unnecessary freezer variability.
- RuneSchema core detection accepts config+dlls+enabled.txt even when a ZIP omits an empty mods/ folder, and normalizes enabled.txt to a blank self-enable marker.
