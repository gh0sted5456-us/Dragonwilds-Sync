# Dragonwilds Sync Release 1.2 — RSDW Toolkit

## Goal

Release 1.2 removes duplicate character/save-editor ownership from Dragonwilds Sync. Sync remains the orchestrator; RSDW provides the specialist editor/model surfaces.

## Character hydration contract

1. The profile character selector establishes one selected character ID.
2. The backend resolves that ID to the current save path and returns the exact JSON document plus SHA-256.
3. Every RSDWTools editor receives the same selected save through the embedded webview bridge.
4. RSDWModel Avatar receives only appearance/equipment parameters that can be resolved from save-backed values.
5. Switching characters increments a hydration token; stale asynchronous responses are discarded.
6. Editor save/download actions are intercepted and sent back to Sync. Sync refuses stale SHA writeback, creates an APPDATA backup, validates JSON, then atomically replaces the save.

## Local RSDWTools source

The existing RSDW cache refresh downloads the upstream RSDWTools repository revision, caches its `website/` directory under APPDATA, and validates the five editor entry points. Electron exposes that folder only through a restricted `rsdw-local:` protocol. Webviews have Node integration disabled, context isolation enabled, sandboxing enabled, navigation restricted to approved RSDW origins, and new windows denied/opened externally.

This replaces the old idea of operating a public Dragonwilds Sync webhost. No launcher public website service is required for the editor.

## RSDWModel Avatar

The Avatar viewer remains upstream-hosted for now because the full generated RSDWModel asset corpus is much larger than the launcher should bundle. The launcher hydrates its URL/hash from save-backed fields. `Customization.CustomizationData` is used for safe BodyType/Head/SkinTone/HairColor/EyeColor conversion, while explicit skeletal model paths in the save can hydrate equipment slots. Unknown mappings are left to RSDWModel defaults rather than guessed.

## Live Map & Tracking

RSDW Toolkit → Live Map & Tracking and Server → Map share one renderer component and one telemetry model. Dedicated Worlds continue to consume server-authoritative coordinates through the existing RSDWToolsUE4SS / `bridge_shm` adapter path. The bundled Lua component remains a thin adapter only; it does not create a second native IPC/telemetry system.

Private World Broadcast does not emulate gameplay hosting. If/when equivalent RSDW local-game telemetry is available, it can hydrate this same Toolkit map surface without introducing a second map implementation.

## Attribution

- Application Creator — Lucas Jones (jonesing4space)
- RuneSchema — Snorkles
- RSDW — Hi im Tat
- RSDW Modding Community — community contributors

A small RSDW credit remains visible but unobtrusive in Toolkit surfaces. Settings → About provides the full attribution list, current application version, changelog, and full Community License text.

## License

See `LICENSE.txt`. The Community License permits free use/redistribution/modification and royalty-free `.rsdwl` interoperability while withholding permission to sell Dragonwilds Sync itself or put access behind mandatory payment. Third-party rights remain separate.
