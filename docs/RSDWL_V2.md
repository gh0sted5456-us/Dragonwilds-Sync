# RSDWL v2 package envelope

`.rsdwl` is a ZIP-backed Dragonwilds Sync interchange container. The extension alone does not determine the payload. Importers must inspect `manifest.json` and route by `packageType`.

Current package types:

- `world` — shareable World connection/presentation profile.
- `character` — untouched Dragonwilds character save plus launcher metadata/optional portrait.

The envelope is intentionally extensible: future package types add typed payload roles without changing the ZIP/container convention.

## Common manifest

```json
{
  "format": "dragonwilds-sync-launcher",
  "version": 2,
  "packageType": "world",
  "packageId": "...",
  "createdAtUtc": "...",
  "producer": {
    "application": "Dragonwilds Sync",
    "version": "1.0.0",
    "fingerprint": "..."
  },
  "payloads": [
    {
      "role": "world-profile",
      "path": "world/world.json",
      "mediaType": "application/json",
      "sha256": "...",
      "size": 1234,
      "required": true
    }
  ],
  "security": {
    "digestAlgorithm": "sha256",
    "payloadIndexSha256": "...",
    "exportKey": "..."
  },
  "metadata": {}
}
```

`exportKey` is a provenance/integrity identifier derived from launcher fingerprint + UTC creation time + payload-index SHA-256. It is **not** an authentication secret or a digital signature.

## Import safety

Importers reject traversal/absolute paths, duplicate archive members, duplicate indexed payload paths, excessive file counts/expansion, wrong package types, missing required payloads, invalid sizes/checksums, and an inconsistent export key.

## World credential policy

World packages may carry the normal player password and the server's separate, rotatable, sync-scoped `share_access_key`. They must never carry the private `server_key`, owner/admin key, unique passkey, or equivalent aliases.

The receiving server authenticates the Share Access Key with nonce/HMAC proof and assigns a narrower `sync-read` scope. The package records credential source as `imported-rsdwl`; feed profiles use `online-feed`; locally linked/manual profiles retain their own source. This source is recorded server-side with the authentication token/activity.
