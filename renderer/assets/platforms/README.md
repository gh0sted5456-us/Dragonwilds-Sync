Platform and ecosystem marks are bundled for local/offline identification only.
They are shipped with Dragonwilds Sync so Desktop, WebGUI, and the public website
do not depend on third-party CDNs for normal placard rendering.

Current bundled marks include:

- Steam
- Windows
- Linux
- Xbox
- PlayStation
- Nintendo Switch (legacy compatibility mark)
- Nintendo Switch 2
- Epic Games
- Discord
- Nexus Mods
- GitHub
- UE4SS
- RuneSchema
- PAKs
- Adults Only / Kid Friendly presentation badges

Canonical platform compatibility and storefront metadata lives in:

```text
resources/platform-registry.json
```

The public website footer uses only trusted entries from the same platform family and
links platform/store icons to the official RuneScape: Dragonwilds product pages.
Store links are presentation metadata owned by Dragonwilds Sync; they must not come
from arbitrary World telemetry or `.rsdwl` user input.

Nintendo Switch 2 is the canonical supported Nintendo platform key. Existing
`nintendo`, `nintendo switch`, and `switch` values remain readable as legacy aliases
and should normalize to `switch2` in new application/WebGUI/world-builder work.

Sources/provenance:

- Steam, Epic Games, PlayStation, Discord: originally sourced from Simple Icons.
- Nintendo Switch and Nexus Mods: originally sourced from Simple Icons 13.x.
- Nintendo Switch 2: bundled local identification treatment derived from the existing Nintendo Switch mark with an explicit Switch 2 identifier for Dragonwilds platform compatibility.
- Xbox: adapted from the Microsoft/Xbox logo asset previously sourced from Wikimedia Commons (`File:Xbox Logo.svg`) and presented in Xbox green for dark-surface visibility.
- Windows: bundled geometric Windows mark using the standard Windows blue presentation.
- GitHub: bundled GitHub mark for local website/download presentation.
- Linux: bundled local platform-identification artwork.
- UE4SS: bundled local vector treatment based on project-provided UE4SS reference artwork; used only to identify the UE4SS runtime/mod family.
- RuneSchema: bundled local vector treatment based on project-provided RuneSchema reference artwork; used only to identify the RuneSchema mod family.
- PAKs: original generic Dragonwilds Sync package/cube mark used to identify cooked Unreal PAK/UTOC/UCAS-oriented content; it is not a third-party company logo.

Simple Icons is CC0-1.0. Brand names and logos remain trademarks of their
respective owners. Their inclusion does not imply endorsement or affiliation.
