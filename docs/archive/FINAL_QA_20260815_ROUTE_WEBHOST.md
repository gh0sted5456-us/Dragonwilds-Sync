# V1 dual-route, character workspace, and WebHost publishing QA

## Implemented

- Client and Server network settings detect and display LAN and public addresses independently.
- Linked World history retains exact World identity, both routes, credentials, selected character, and connection time. Automatic routing can retry the stored WAN route when the client leaves its LAN.
- Ledger and Character Map are no longer global Profile tabs. They appear as subtabs only after a character is selected and filter their records to that character.
- WebHost supports Direct WAN/DNS publishing and an optional checksum-verified Cloudflare Quick Tunnel. MAMP was rejected as redundant because it is a local development web stack, not an Internet publishing mechanism.

## External-path validation

The isolated WebHost smoke fixture started on a random loopback port, opened a temporary outbound HTTPS tunnel, resolved its public hostname, and received a valid `/health` response. Microsoft Edge then loaded the same temporary public `/servers` address and exposed the Dragonwilds Sync Worlds page, discovery filters, language selector, and placard/horizontal layout controls. The tunnel was stopped after the check.

## Linux/WSL status

The source, Linux builder, AppImage/tar/Flatpak metadata, and Ubuntu workflow remain included. On this host, `wsl --status` reports WSL2 as selected but unavailable because virtualization/Virtual Machine Platform is not active, and `wsl --list --verbose` reports no installed Linux distribution. A native Linux binary cannot be honestly produced or runtime-tested until those machine prerequisites are corrected or the included Ubuntu workflow is run.

## Release gate

The timestamped release folder records the final automated verification result, Windows artifact hashes, raw-source manifest, and the Linux prerequisite boundary. It does not label an unbuilt Linux package as tested.
