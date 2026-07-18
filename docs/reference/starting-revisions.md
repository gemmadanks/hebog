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
| PyBDSF released reference | `v1.14.1` at `1b6e0a04ba6327bc1ce3f576928fe58b81d8c1cc` | Expected current Rapthor comparator; runtime confirmation pending |
| PyBDSF `master` reference | `c70103be3ae9ae9908286f144e6ce956acc0ce5c` | Clean; 40 commits after `v1.14.1` |
| LSMTool dependency pin | `3adf3d6f1f8c03db34e13a45a752f6f6dd7d7f4a` | Object available locally |
| LSMTool local reference | `4e5cf93046e309844c04382375f86e68929bd2d8` | Two untracked files |

The `gec-468-ai-migrate-to-prefect` Rapthor branch at the recorded revision
defines the consumer and Prefect/Dask task-runner contract. Rapthor pins
LSMTool at `3adf3d6f1f8c03db34e13a45a752f6f6dd7d7f4a`; that object is available
locally, and its source-finding module matches the module in the checked-out
LSMTool branch.

Rapthor currently resolves the latest released PyBDSF distribution. At the
capture date [PyPI identifies that release as `1.14.1`](https://pypi.org/project/bdsf/1.14.1/);
its tag and package provenance resolve to
`1b6e0a04ba6327bc1ce3f576928fe58b81d8c1cc`. The refreshed `master` reference
is `c70103be3ae9ae9908286f144e6ce956acc0ce5c`. These are separate mandatory
performance comparators: Hebog must reduce the released version's matched
median `filter_skymodel` time by at least 50% and must also be faster than the
`master` reference under the same benchmark conditions.

The released version remains the current compatibility reference. Frozen
products from `master` provide forward-looking comparison evidence, but any
scientific differences between the two PyBDSF references must be adjudicated
against independent truth and the Rapthor contract rather than copied
automatically.

## Dependency and container evidence

The JSON inventory records SHA-256 checksums for Hebog's `uv.lock` and each
relevant `pyproject.toml`, development-container definition, and Dockerfile.
It also records the released PyBDSF source-distribution checksum published by
PyPI. These checksums make later changes to the candidate environment visible.

The inventory deliberately records these unresolved gaps:

- Rapthor declares `bdsf` using a latest-release resolution policy rather than
  pinning `1.14.1`; the controlled benchmark runtime must still confirm the
  installed distribution.
- Hebog and Rapthor container definitions use mutable base-image tags, and no
  digest from a built benchmark image has been captured.

The 40 commits from `v1.14.1` to the recorded `master` include residual-image
statistics speedups and RMS/adaptive-RMS simplification, as well as changes to
island masks, flux calculations, fitting, and output handling. Both exact
references therefore need isolated, matched benchmark environments and
separate scientific reports.

Resolve these gaps before checking off the Phase 0 revision-capture task or
using a run as release evidence. The eventual benchmark record must include
the released and `master` PyBDSF revisions, the installed LSMTool version, the
built container digest, and the full dependency inventory from each isolated
environment.
