# identity.txt

`identity.txt` is a portable mod identity file a mod creator can
drop into the root of any:

- UE4SS mod folder (`Binaries/Win64/ue4ss/Mods/<ModName>/`)
- RuneSchema mod folder (`RuneSchema/mods/<ModName>/`)
- `.pak` mod folder (`Content/Paks/~mods/<ModName>/`)

next to the same launcher-recognized `tags.txt` / `hotload.txt` sidecars
already documented for those folders.

Dragonwilds Sync creates a commented template when it repairs a managed
directory mod's metadata contract. The author can edit it in the in-app Mod
Explorer. Existing uppercase `IDENTITY.txt` files remain compatible and are
never replaced.

## Format

Plain text, one `key: value` pair per line. Blank lines and lines starting
with `#`, `;;`, or `//` are ignored.

```
Modder: Snorkles
Nexus: https://www.nexusmods.com/runescapedragonwilds/mods/12
Steam: https://steamcommunity.com/sharedfiles/filedetails/?id=999999999
Website: https://example.com/my-mod
Description: Adds a farming quality-of-life overhaul.
```

Recognized keys:

- `Author` / `Creator` / `By` / `Modder` -- a free-text name. Only the first
  one found is used.
- `Description` / `About` / `Summary` -- a short blurb, capped at 400
  characters. Only the first one found is used.
- Any other key whose value is an `http://` or `https://` URL becomes a
  labeled link. `Nexus`, `Steam`, `Website`/`Site`/`Url`/`Link`/`Web`/
  `Homepage`, `Github`, `Discord`, `Youtube`, and `Twitter`/`X` get a
  friendly label automatically; any other key is title-cased and used as
  the label as-is. Up to 8 links are read; values that aren't `http(s)`
  links are ignored (this file is display metadata only -- it can never
  point the launcher at a local path or a non-web protocol).

A file with none of the recognized fields is treated the same as no file at
all.

## Where it shows up

- The mod's row in the UE4SS / RuneSchema / Paks load-order list (both the
  Server world's mod manager and the SinglePlayer/Private World mod list)
  shows a small "ⓘ By &lt;author&gt;" button when an `IDENTITY.txt` was
  found.
- Clicking it opens a **Mod Info** popup with the author, description, and
  one button per declared link: **Open in App** (a small, fully isolated
  in-app browser window -- no access to any Dragonwilds Sync data or APIs)
  or **Open in Browser** (the system default browser).

## Where it's implemented

- `backend/mod_tags.py` -- `parse_identity_text()` / `identity_from_mod_root()`
  (parsing), `UE4SS_BAKED_IN_DEFAULT_MODS` (a related, separate concern: the
  set of UE4SS's own baked-in default Lua mods that are excluded from every
  mod list entirely, since IDENTITY.txt or not, there's nothing for an
  operator to manage about them).
- `backend/local_world.py` / `backend/server_systems.py` -- wire
  `identity_from_mod_root(...)` into each mod unit's dict/`ModUnit.identity`
  during a scan, for UE4SS mods, RuneSchema mods, and directory-based PAK
  groups.
- `renderer/app.js` -- `modIdentityBadge()` / `openModIdentityDetails()`
  render the badge and popup; `electron/main.cjs`'s
  `createExternalBrowserWindow()` (IPC: `dragonwilds:open-in-app-browser`,
  bridged as `window.dragonwilds.openInAppBrowser(url)`) is the in-app
  browser window -- a bare `BrowserWindow` with no preload script and no
  `window.dragonwilds` access, since it may load arbitrary third-party
  content.
