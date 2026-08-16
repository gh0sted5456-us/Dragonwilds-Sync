Dragonwilds Sync launcher-owned runtime bundles

The bundled UE4SS core intentionally does not contain RSDWTools. RSDWTools is
not installed as part of the portable application package.

UE4SS and RuneSchema are machine/server prerequisites managed by Settings > Server.
Both may be installed/updated from an editable GitHub/release/direct-ZIP URL or from a local ZIP/drop target.

Optional offline RuneSchema bake:
  Place the authoritative RuneSchema core ZIP at:
    resources/RuneSchema-core-latest.zip

When that file exists before running build.bat, electron-builder packages it automatically and the Windows build verifies that it is present in the finished application resources.

RuneSchema core layout is recognized by either:
  - a core mods/ directory, OR
  - config/ + dlls/ + enabled.txt

Dragonwilds Sync normalizes RuneSchema enabled.txt to a blank self-enable marker. RuneSchema itself is never listed in dynamic UE4SS mods.txt.
