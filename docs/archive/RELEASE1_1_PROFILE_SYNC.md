# Dragonwilds Sync Release 1.1 — Profile Sync

## Navigation consolidation

Release 1.1 reduces the player-facing World model to **Private Worlds** and **Worlds**.

Private Worlds represent local save profiles and use the normal Dragonwilds client installation. They remain private/singleplayer until the player chooses **Broadcast**. Broadcast starts only the Dragonwilds Sync discovery/file service; Dragonwilds itself remains responsible for creating the co-op gameplay session.

Worlds combines linked, discovered, favorite, recently played, and imported/curated profiles. The browser includes search, 30-second status refresh, All/Favorites/Recently Played/Curated filters, card and horizontal layouts, LAN discovery, metadata Ping, Quick Launch, and Send to Desktop.

## Broadcast and networking

Both Private and Dedicated profiles use the single action **Broadcast**.

- Private: publishes launcher metadata/manifests/files and Sync fingerprint; gameplay hosting stays in-game.
- Dedicated: manages the dedicated runtime and publishes the separate Sync/Studio endpoint.

Launcher synchronization uses an independent Sync port rather than the Dragonwilds gameplay port. World identity remains the exact World Name plus known internal/external IP aliases; ports are transport metadata.

## Advanced numbered servers

**Settings → Application → Advanced → Enable Multiple Servers** is off by default. When enabled, Dedicated profiles expose a Server Number / Instance selector.

Default automatic ports:

- Game: `7777 + (instance - 1)`
- Sync: `27051 + (instance - 1)`

Manual overrides remain available. Each profile carries independent config/save/log/profile state. Release 1.1 still manages one active dedicated runtime at a time; true simultaneous managed runtime isolation is intentionally deferred rather than emulated unsafely through the singleton backend.

## Server health workspace

The server Overview/Health surface includes live history for CPU, process/system RAM, network upload/download, and uptime/runtime status. CPU and memory pressure contribute directly to the explainable Health Score. Players/Map continue to use the existing server-side PlayerTracker/bridge plumbing.

## RSDWL v3 profile bundle

New exports use one `.rsdwl` type. See `RSDWL_V3_PROFILE_BUNDLE.md` for the archive contract.

Legacy RSDWL v2 character and World packages remain importable, but the launcher no longer generates new v2 packages.

## Shared Worlds webhost removal

The old standalone static Shared Worlds webhost/template is removed from the application resources, builder contract, settings UI, and current documentation. Migration-only legacy state/RPC shapes remain so older APPDATA and v2 packages load without data loss.

Public/discovery acquisition remains behind adapters and the existing launcher broadcast/LAN mechanisms; Release 1.1 does not hard-code an undocumented public HTTP server-list endpoint.
