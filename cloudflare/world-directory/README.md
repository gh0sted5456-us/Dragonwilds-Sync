# Dragonwilds Sync — Legacy Cloudflare World Directory

This folder documents the **retired first-generation** public telemetry prototype.

The active Dragonwilds Sync public-directory implementation lives under:

```text
cloudflare/dragonwilds-sync-directory/
```

Use that implementation, its Wrangler configuration, and its current authentication/bootstrap instructions for deployments.

The historical prototype used a single JSON environment secret containing per-World signing keys. That transitional mechanism is intentionally no longer named or documented here because V3 uses the authoritative backend/network identity and secret-reference architecture instead.

The public-directory security boundary remains unchanged:

- public heartbeat/telemetry only;
- no server administration;
- no World passwords;
- no WebGUI sessions;
- no private remote-management credentials;
- no secrets committed to GitHub.

This legacy folder is retained only so older repository references do not become unexplained dead links. Do not deploy it for current Dragonwilds Sync builds.
