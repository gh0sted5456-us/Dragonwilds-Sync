# System Test Matrix

`test-matrix.json` is the executable authority. This view summarizes its phased
coverage; pass/fail evidence belongs in timestamped runner reports.

| Case | Mode | Phase | Primary proof |
|---|---|---|---|
| `SRC-MATRIX-DOCS` | Automated | Source | Inventory and matrix integrity |
| `SRC-JS-CONTRACTS` | Automated | Source | Electron, renderer, website, Cloudflare, release contracts |
| `SRC-PYTHON-SYNTAX` | Automated | Source | Python source compilation |
| `AUTO-BACKEND-REGRESSION` | Automated | Backend | Isolated Core regression suite |
| `INT-DESKTOP-FREEZE` | Manual | Integrated | UI responsiveness, propagated deadline/cancel, restart |
| `INT-WORKER-FAULTS` | Manual | Integrated | Worker faults, reattach, cleanup, repeated lifecycle |
| `INT-WORLD-DATA` | Manual | Integrated | Profiles, mods, exchange, character/item, restore |
| `NET-WEBHOST-DIRECTORY` | Manual | Network | Auth, CSRF, federation, offline/partial failure |
| `MANUAL-SYSTEM-DIMENSION-AUDIT` | Manual | Integrated | Ten required dimensions for every stable system |
| `REAL-CROSS-MACHINE-SYNC` | Physical | Real environment | Identity, parity, Direct Connect, real join |
| `PKG-WINDOWS-CLEAN` | Physical | Packaged | Clean Windows portable artifact |
| `PKG-UBUNTU-CLEAN` | Physical | Packaged | Clean AppImage and real Proton behavior |
| `SOAK-RESOURCE-BOUNDS` | Physical | Soak | Resource bounds, repeated faults, long services |

Every stable system ID in [`SYSTEMS.md`](SYSTEMS.md) appears in the JSON matrix.
The validator rejects unknown IDs, duplicate cases, missing procedures, missing
automated deadlines, uncovered systems, and any system missing one of the ten
required coverage dimensions. It also rejects backend regression files omitted
from the automated backend runner.
