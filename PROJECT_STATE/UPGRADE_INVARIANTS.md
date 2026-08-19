# Upgrade Invariants

Use this as the pre-flight checklist before replacing frameworks, reorganizing folders, modernizing Electron/Python, changing sync formats, or asking an AI/codegen system to 'clean up' the project.

## Authority invariants

1. **One runtime authority.** Desktop, Minimal Mode, WebGUI, Remote Commands, notifications, and update actions must call the same backend lifecycle rather than own process state independently.
2. **One synchronization authority.** `sync_engine.py` (or a deliberate successor) owns transport/parity; DragonConnect does not become a second sync protocol.
3. **One profile concept.** Local, Co-Op, and Dedicated are modes/workflows around World profiles, not unrelated duplicate profile stores.
4. **One logical mod Explorer.** Application View Mods/Explore actions should not fork into independent filesystem management implementations.

## Runtime safety invariants

5. **Process before broadcast.** Never advertise/publish Sync before the dedicated process is verified.
6. **Watchdog before publication.** Catastrophic controller loss must not leave an unmanaged dedicated process.
7. **Failure withdraws share.** Do not leave false-running/false-online state.
8. **Lifecycle locks remain authoritative.** Start/stop/restart/update must not race each other through different control surfaces.
9. **Same-profile Start preserves live save.** Never restore an older snapshot over current live progress simply because Start was pressed.
10. **World switch snapshots outgoing state first.** Incoming profile materialization must not inherit another World's live save.

## State/persistence invariants

11. **Desired ≠ managed ≠ materialized.** Do not collapse these layers into 'whatever is currently in the game folder'.
12. **Known reads do not rewrite state.** A screen open should not churn profile timestamps or migrations.
13. **No durable plaintext secrets in normal profile/state JSON.** Preserve the `dws-secret://` reference boundary or migrate it intentionally to a stronger platform vault.
14. **Portable exports never include decrypted local credentials.**
15. **Unknown/unmanaged files are not silently deleted.** Ownership must justify cleanup.

## Mod/component invariants

16. **User Mods are UE4SS, RuneSchema, Pak.** Infrastructure is not a fourth user-mod family.
17. **RuneSchema child content stays logically RuneSchema.** Physical UE4SS hosting does not reclassify it.
18. **DragonCore is HOST/SERVER, hidden from ordinary mod UI and client parity.**
19. **DragonConnect is CLIENT, hidden from ordinary mod UI.** Keep `PersistentDirectConnectIP` until a migration explicitly replaces that physical identity.
20. **RSDWTools is data; RSDW Toolkit/DevKit is runtime tooling.** Never merge these concepts because of an old folder/package name.
21. **Pak content is not emitted into UE4SS `mods.txt`.**
22. **`mods.txt` is generated state, not a mod.**
23. **Never send the server's literal `mods.txt` to a joining client.** Generate client state from verified CLIENT/BOTH roles and derived frameworks/components.

## Sync/security invariants

24. **Parity is verified after materialization.** `launch_ready` must require final host/local agreement, not just successful download requests.
25. **Sync endpoint and game endpoint are separate concepts.** Do not assume the HTTP/auth host is the gameplay socket.
26. **Download paths remain safe and hashes remain authoritative for transfer integrity.** Launch-time metadata optimization does not weaken network integrity checks.
27. **Public directories do not own private World admin authority.** Credentials/sessions/permissions remain at the target World.
28. **WebGUI writes use authenticated/CSRF/permission/audit boundaries.**
29. **Source registries are declarative.** Do not add arbitrary remote commands/scripts as 'update metadata'.

## Performance invariants

30. **Open known local state immediately.** Do not make World/Character/Mod/Save management wait for GitHub, Nexus, Steam, CL, full reconcile, or whole-tree hashing.
31. **Resolve is cheap; Reconcile is explicit/needed.**
32. **Cache invalidation is part of the feature.** Do not add persistent caches without mutation/version/signature invalidation.
33. **Explicit Rescan/Verify bypasses caches.**
34. **Do not replace real latency with fake spinners/sleeps.** Measure and remove the blocking cause.
35. **No unnecessary polling.** Prefer shared event/invalidation state; Community refresh is explicit.

## UI invariants

36. **Application-owned tools open as internal windows.** Move/resize/minimize/maximize must not reload the app.
37. **Real websites stay browser/external surfaces.**
38. **Notifications focus/restore existing app windows where possible instead of creating duplicates.**
39. **Explorer hides managed Core/tooling/control infrastructure.**
40. **See in Explorer remains the physical OS-folder action; View Mods remains the logical in-app Explorer.**

## Upgrade procedure

Before a large upgrade:

1. read all `PROJECT_STATE/` files
2. run current packaged CI and record the green baseline
3. identify which invariant, if any, the upgrade intentionally changes
4. write the migration/recovery story before changing persistent formats
5. modify the authoritative owner, not every surface independently
6. add/adjust a regression that expresses the new invariant
7. retain compatibility adapters until old installs can migrate safely
8. package on Windows and Ubuntu
9. perform the real-game/cross-machine acceptance list
10. update this dossier with the new decision and reason

If a change cannot explain which owner it modifies and how state converges afterward, it is probably creating a second authority.
