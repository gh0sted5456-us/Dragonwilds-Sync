# External Mod Hosting for Server Hosts

Dragonwilds Sync normally sends mods directly from your server computer. You only need External Hosting when one of your mods is large enough that serving it to every player would put too much pressure on your upload speed.

## The simple rule

**Small mods come from your server. Big mods can come from your cloud link. Dragonwilds Sync handles the rest.**

You do not need a second copy of every mod. Keep your normal server mods exactly where they already are. Only mods you choose as **External** need a ZIP package.

Example:

```text
FarmersQoL          → Server
ExpandedLoot        → Server
BetterCapes         → Server
VisualOverhaul      → External
```

In this example, players download the first three mods from the World host. `VisualOverhaul` is downloaded from the public external link.

## Setting up a large mod

1. Open your World's Mods list in Dragonwilds Sync.
2. Find the large mod you want to offload.
3. Change **Delivery** from `Server` to `External`.
4. Click **Prepare Package**.
5. Sync creates the ZIP for you.
6. Upload that ZIP to Google Drive, OneDrive, Dropbox, or another public HTTPS file host.
7. Paste the public download link into Sync.
8. Leave **Fallback to Server** enabled unless you have a reason not to.
9. Click **Test Link**. Sync downloads the uploaded package and verifies that it is the exact ZIP it prepared.
10. When the status shows **READY**, publish your World normally.

## What players see

Players still perform one normal Sync operation.

```text
Client connects
    ↓
receives the World manifest
    ↓
downloads normal mods from the server
    +
downloads selected large mods from external links
    ↓
Sync verifies everything
    ↓
SYNCED
    ↓
Play
```

The server manifest remains the source of truth. The cloud provider only supplies the download bytes.

## Where files are installed

You do not need to build game-directory paths into the external ZIP. Dragonwilds Sync decides where every verified file belongs from the World manifest.

For example, a PAK mod may contain:

```text
VisualOverhaul.pak
VisualOverhaul.ucas
VisualOverhaul.utoc
```

After verification, Sync places those files into the correct Dragonwilds PAK mod location automatically.

## One mod = one source

Keep one logical mod together.

Good:

```text
VisualOverhaul.pak
VisualOverhaul.ucas
VisualOverhaul.utoc
        ↓
External
```

Do not split one mod so some of its files come from the server and other files come from the cloud. Choose either **Server** or **External** for the whole mod.

## Supported external sources

The first version supports public links from:

- Google Drive
- OneDrive
- Dropbox
- Direct HTTPS file hosts

The link must be public and readable without giving Sync your cloud account password, OAuth token, or private API key.

## Verification and fallback

External files are never trusted just because they downloaded successfully.

Sync checks the package SHA-256 and then verifies the actual mod files against the authenticated World manifest. If the external source is broken, unavailable, or returns the wrong file, Sync can fall back to normal server transfer when **Fallback to Server** is enabled.

## Updating an externally hosted mod

If you change the real mod on your server, Sync marks its old external package as **OUTDATED**.

Then:

1. Click **Prepare Package** again.
2. Upload the new ZIP.
3. Update the public link if needed.
4. Click **Test Link** again.
5. Publish the World.

Until the replacement is ready, normal server transfer remains the safe fallback.

## What should stay on the server/runtime system

External Hosting is only for ordinary World mods: UE4SS mods, RuneSchema mods, and PAK mods. Do not use it for UE4SS core, RuneSchema core, DragonConnect/DragonLink launcher components, RSDWTools/DevKit, `version.dll`, or Dragonwilds Sync application files.
