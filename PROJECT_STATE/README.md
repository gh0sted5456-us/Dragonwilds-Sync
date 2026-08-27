# Engineering State

This folder contains durable engineering authority for the current stable
`main` branch. Candidate work is verified on `testing-branch`. Test evidence must identify its exact commit; do not place
ever-changing run IDs or a supposedly current SHA in these standing documents.

## Authority order

1. [`../docs/SYSTEMS.md`](../docs/SYSTEMS.md) — complete stable system inventory.
2. [`ARCHITECTURE.md`](ARCHITECTURE.md) — process and authority boundaries.
3. [`SYSTEM_MAP.json`](SYSTEM_MAP.json) — machine-readable owner map.
4. [`UPGRADE_INVARIANTS.md`](UPGRADE_INVARIANTS.md) — non-negotiable safety rules.
5. [`../docs/test-matrix.json`](../docs/test-matrix.json) — executable test coverage.
6. [`ACCEPTANCE_REMAINING.md`](ACCEPTANCE_REMAINING.md) — gates automation cannot certify.

Historical phase and handoff documents are under [`archive/`](archive/README.md).
They explain how a feature arrived but do not override current source or the files
above.

## Version state

`package.json`, its lockfile, release metadata, and canonical changelog remain
the authority for the shipped version. The current stable version is `3.0.4`.

## Core invariants

- One trusted desired-state/control authority.
- At most one lifecycle operation per World and one live executor for that World.
- No listener or publication before the real dedicated process is verified.
- Workers execute bounded revisions and do not become durable profile writers.
- UI, Quick, and WebHost use the same trusted authority.
- Secrets remain secret references; public data is explicitly allowlisted.
- Client runtime is role-correct and never copies the server's literal `mods.txt`.
- Automated green advances a phase; it never substitutes for required physical evidence.
