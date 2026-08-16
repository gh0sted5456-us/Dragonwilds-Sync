# Alpha 3 Runtime Parity Audit

This audit compares the Electron/headless runtime against the preserved mature Python capability contract.

| Capability family | Alpha 3 owner | Status |
|---|---|---|
| Client World profiles / presentation | renderer + profile_store | Headless/live |
| Simple / Advanced client workflow | renderer | Live |
| Internal/External smart routing | world_identity + network_client | Live |
| HMAC authentication | network_client + server_systems | Live |
| Manifest diff/download/report | sync_engine + server_systems | Live |
| Commit-on-Play World swap | sync_engine | Live |
| Direct Connect companion | sync_engine + packaged resource | Live |
| LAN discovery | server_systems + renderer | Live |
| Public IP / geolocation | network_client + server_systems | Live |
| Hosted World profiles | profile_store | Live |
| Physical mod/save World swap | server_engine | Live |
| Mod scan/classification/order | server_systems | Live |
| Master/Slave section push | server_systems + service | Live |
| Live/Pending publication | server_systems + renderer | Live |
| Authenticated file share | server_systems | Live |
| Dedicated Start/Stop/Restart | server_engine | Live |
| Connected-player parsing | PlayerLogMonitor | Live |
| Hardware broadcast | server_systems | Live |
| SteamCMD setup/update/delete | server_systems | Live |
| Firewall configuration | server_systems | Live |
| Steam build check | server_systems | Live |
| UE4SS latest check/update/ZIP | server_systems + server_engine | Live |
| Authoritative UE4SS runtime library | server_systems | Live |
| RuneSchema core/mod ZIP deployment | server_systems | Live |
| Save backup history | server_engine + server_systems | Live |
| Feedback/rating | server_systems + renderer | Live |
| Access policy | server_systems + hosted World editor | Live |
| Activity console data | server_engine + SyncState + renderer | Live |
| Windows packaging | build.bat + build_windows.ps1 | Source verified; Windows build must run on Windows |

The legacy GUI file is preserved for comparison only. A source audit verifies no active Electron/headless runtime module imports it.
