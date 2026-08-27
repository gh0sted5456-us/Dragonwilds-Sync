# Known Limitations and Unverified Boundaries

This file lists current boundaries that must not be presented as certified behavior until their test-matrix gates pass.

## Release and versioning

- Packaged metadata is 3.0.4 on `main`; `testing-branch` is reserved for staged verification and package candidates.
- Historical Alpha/RC/Phase green results do not certify the current head.

## Responsiveness and cancellation

- The Core stdio dispatcher processes one request at a time. Long or wedged legacy handlers can delay later Core requests.
- Renderer and Electron-main requests now have central bounded deadlines, including longer policies for backup/update/sync operations. Those deadlines still require real workload calibration.
- A renderer/main timeout does not yet cooperatively cancel the Python operation. Full cancellation and Core queue-pressure behavior remains a required hardening and test gate.
- Worker startup stdout/stderr is captured in bounded rotated startup logs, but packaged-path and crash-report presentation still require platform acceptance.

## Dedicated runtime and multiple Worlds

- The worker architecture supports one execution owner per active hosted World, but real simultaneous multi-World Dragonwilds isolation must be proven against actual game config/save/runtime roots before being promised.
- Rollback/direct execution remains a migration safety path until real-game parity and recovery acceptance pass.

## Real game and external services

- CI cannot prove real Dragonwilds process behavior, actual generated game configuration, live player telemetry, console/spawner bridge behavior, Steam/SteamCMD updates, or cross-machine joining.
- Router forwarding, UPnP, NAT loopback, carrier-grade NAT, firewall products, DNS, and WAN reachability depend on the real environment.
- Production Cloudflare schema/deployment/credentials and rollback require authenticated operator acceptance.

## Linux and Proton

- Ubuntu AppImage build/smoke paths do not certify an actual Dragonwilds dedicated process under Linux/Proton/Wine.
- The upstream RSDW live bridge uses Windows-specific shared-memory/kernel behavior. Unsupported Linux live tools must fail gracefully.
- Proton process-tree containment and orphan cleanup require physical testing.

## Map, coordinates, and telemetry

- Exact map placement requires verified calibration and live telemetry. The application must not invent coordinate transforms.
- Optional RSDW/player bridge failures must remain isolated from the dedicated server and Sync.

## Packaging and updates

- Windows Portable and Ubuntu AppImage must be tested on clean machines without repository dependencies or developer runtimes.
- Installer-style Windows deployment is not the current primary package contract.
- Launcher self-update with active workers requires explicit recovery/reattach acceptance.

## Certification rule

Anything listed here is either unsupported, external, or not yet proven. It becomes certified only when the exact commit/artifact receives a passing result in `docs/test-matrix.json` and the generated report.
