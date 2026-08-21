# System Verification and Release Gates

This is the authoritative test process for Dragonwilds Sync. The inventory in
[`SYSTEMS.md`](SYSTEMS.md) defines what must be tested; `test-matrix.json` maps
each system to automated and physical evidence. A source-contract pass is useful,
but it is not release certification.

## Phased review

| Phase | Purpose | Exit condition |
|---|---|---|
| 0. Baseline | Pin commit, dependencies, platform, package version, and known limitations | Reproducible environment and clean evidence directory |
| 1. Source safety | Parse Python/JavaScript, validate contracts, docs, matrix, assets, and schemas | `npm run test:systems:source` passes |
| 2. Core regression | Run isolated backend regression files and subprocess protocols | `npm run test:systems:backend` passes without hangs |
| 3. Process and fault | Exercise Core, World worker, feature workers, listeners, deadlines, crashes, and cleanup | No orphan, leaked listener, unbounded wait, or corrupt durable state |
| 4. Integrated desktop | Exercise Full, Quick, internal tools, WebHost, restart, cancellation, and offline behavior | Required workflows pass from a development build |
| 5. Packaged platforms | Build and test Windows portable and Ubuntu AppImage on clean machines | Install/boot/persist/update/uninstall evidence passes |
| 6. Real environment | Use real Dragonwilds, Steam/SteamCMD, Proton where applicable, two machines, and router/network faults | Game, Sync, Direct Connect, directory, and recovery scenarios pass |
| 7. Stress and soak | Repeat lifecycle work, large manifests, prolonged services, fault injection, and resource monitoring | No freezes, unbounded growth, duplicate processes, or state damage |
| 8. Release decision | Review every required matrix row and known limitation | Exact commit/package hashes have no required failed or unrun gates |

## Commands

```bash
npm ci
npm run test:systems:list
npm run test:systems:source
npm run test:systems:backend
npm run test:systems
```

The runner creates an isolated application-data root for every automated case,
enforces a case deadline, and writes JSON plus Markdown evidence under
`test-results/`. Use `--system RUNTIME` or another stable system ID to narrow an
investigation:

```bash
python scripts/run_system_tests.py --tier all-automated --system RUNTIME
```

Manual and physical rows are listed by the runner but never converted into an
automatic pass. Record the tester, commit, package SHA-256, platform versions,
Dragonwilds build ID, Steam/Proton version, network topology, observations, and
linked defects.

## Freeze definition

A test is a freeze failure when an operation exceeds its documented deadline,
the interface stops accepting input, progress ceases without a terminal result,
or cancellation/close leaves work, a child process, a listener, or a lock alive.
Every freeze investigation must capture the active operation, request ID, process
tree, listener list, CPU/RAM, relevant logs, deadline, cancellation result, and
whether durable state remained valid.

## Release rule

Automated green permits the next phase. It does not certify the product. A release
is eligible only when every matrix case marked `required_for_release` is passed
against the exact candidate artifact, or an explicit documented waiver is
approved. See [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md).
