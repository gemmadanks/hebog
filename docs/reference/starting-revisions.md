# Phase 0 starting revisions

The machine-readable starting inventory is
[`config/baselines/phase-0-starting-revisions.json`](https://github.com/gemmadanks/hebog/blob/main/config/baselines/phase-0-starting-revisions.json).
It captures the local evidence used for the first Phase 0 contract inventory.
Commit identifiers, rather than branch names, are authoritative.

This is a **candidate inventory**, not a qualification baseline. No scientific
equivalence or performance claim may be attributed to it until the unresolved
runtime versions and container digest are captured.

## Repository evidence

| Repository | Starting revision | State |
| --- | --- | --- |
| Hebog | `9ab6b6068aa515885b29bbbe54d1b96feb7965ff` | Clean |
| Rapthor | `b1a64674b1022476cf052fc2d06ee3b16f031ecd` | Clean |
| PyBDSF local reference | `c70103be3ae9ae9908286f144e6ce956acc0ce5c` | Clean |
| LSMTool dependency pin | `3adf3d6f1f8c03db34e13a45a752f6f6dd7d7f4a` | Object available locally |
| LSMTool local reference | `4e5cf93046e309844c04382375f86e68929bd2d8` | Two untracked files |

The `gec-468-ai-migrate-to-prefect` Rapthor branch at the recorded revision
defines the consumer and Prefect/Dask task-runner contract. Rapthor pins
LSMTool at `3adf3d6f1f8c03db34e13a45a752f6f6dd7d7f4a`; that object is available
locally, and its source-finding module matches the module in the checked-out
LSMTool branch. The local PyBDSF checkout provides implementation and
terminology evidence, but it is not yet proven to be the package installed in
the measured Rapthor runtime.

## Dependency and container evidence

The JSON inventory records SHA-256 checksums for Hebog's `uv.lock` and each
relevant `pyproject.toml`, development-container definition, and Dockerfile.
These checksums make later changes to the candidate environment visible.

The inventory deliberately records these unresolved gaps:

- Rapthor declares `bdsf` without a package version or source revision.
- Hebog and Rapthor container definitions use mutable base-image tags, and no
  digest from a built benchmark image has been captured.

The refreshed PyBDSF checkout includes post-`1.14.1` changes to island masks,
island-integrated flux calculations, RMS processing, and output handling. This
makes resolving the version installed in the benchmark container a scientific
requirement, not merely package bookkeeping.

Resolve these gaps before checking off the Phase 0 revision-capture task or
using a run as release evidence. The eventual benchmark record must include
the installed PyBDSF and LSMTool versions, the built container digest, and the
full dependency inventory from inside that container.
