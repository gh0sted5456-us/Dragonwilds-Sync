Dragonwilds Sync launcher-owned runtime bundles

Official UE4SS baseline:
  v3.0.1-1088-ga1e7f571
  SHA-256 7306a7799881344936ddead14b66030c402fce7d45d0f81a4de0b38055eebcd8

The UE4SS baseline is kept as one complete upstream archive. RuneSchema is a
separate selectable runtime and is never baked into or mixed with that archive.

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
