# Deprecated code cleanup — September 2026

The current cleanup removes only code/assets proven to be superseded while preserving compatibility paths that still serve upgrades, saved profiles, or current wrappers.

Removed/simplified in this pass:

- duplicate historical preload bridge logic: `electron/preload.cjs` is now a redirect-only shim to the live `preload-v2.cjs` implementation;
- obsolete hand-drawn UE4SS and RuneSchema SVG compatibility artwork, replaced everywhere by the canonical bundled WebP assets;
- source-ownership bookkeeping updated for the hybrid external-mod PyInstaller hook.

Intentionally retained:

- V2/legacy service and WebHost providers still referenced by current wrapper layers;
- retired DragonLink gameplay DLL/config cleanup needed to upgrade old installations;
- `FileMirror.v1`, which remains a supported verified transport fallback;
- the inert Defender compatibility API until its remaining current RPC/import surfaces are removed together.

A future cleanup may delete a retained shim only when its remaining runtime/build/test references are migrated in the same change and the full Windows build gate remains green.
