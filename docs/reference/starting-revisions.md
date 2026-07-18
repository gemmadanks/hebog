# Phase 0 starting revisions

The captured machine-readable inventory is
[`config/baselines/phase-0-starting-revisions.json`](https://github.com/gemmadanks/hebog/blob/main/config/baselines/phase-0-starting-revisions.json).
Commit identifiers, artifact checksums, and the built-image digest are
authoritative; branch names and the local image tag are descriptive only.

## Repository evidence

| Repository | Starting revision | State |
| --- | --- | --- |
| Hebog | `9ab6b6068aa515885b29bbbe54d1b96feb7965ff` | Clean starting point |
| Rapthor | `b1a64674b1022476cf052fc2d06ee3b16f031ecd` | Clean Prefect/Dask comparator |
| PyBDSF released reference | `v1.14.1` at `1b6e0a04ba6327bc1ce3f576928fe58b81d8c1cc` | Installed as `1.14.1` |
| PyBDSF `master` reference | `c70103be3ae9ae9908286f144e6ce956acc0ce5c` | Built as `1.14.2.dev40+gc70103be3` |
| LSMTool dependency pin | `3adf3d6f1f8c03db34e13a45a752f6f6dd7d7f4a` | Installed as `1.8.0` |
| LSMTool local reference | `4e5cf93046e309844c04382375f86e68929bd2d8` | Two unrelated untracked files retained |

Rapthor's recorded `gec-468-ai-migrate-to-prefect` branch defines the consumer
contract and uses a Prefect Dask task runner. It resolves the latest released
`bdsf` distribution; the controlled runtime confirms that this installed
`1.14.1`. The `master` comparator is exactly 40 commits after that release.

## Controlled reference runtime

Both references ran in fresh containers from the same local image, resolved to
immutable digest
`sha256:dce93991e2e671428ff8043a7e0d132294d2d2decf1e1587e9904d3e8f49b754`.
The runtime used Python 3.12.3 on `aarch64` and reported 16,321,134,592 bytes
of visible RAM. The complete installed distributions are bound by separate
dependency-inventory digests because the master run adds its wheel ahead of
the installed release:

- release: `ad533f28942ba1d3891a1c5d960028c7bde558ea682e08da21a246235d2eb3c8`;
- master: `9ae1698f862aba82638c5c71bcf699fbda4da056d59a79f939f76230aa32fe76`.

The master wheel is
`bdsf-1.14.2.dev40+gc70103be3-cp312-cp312-linux_aarch64.whl` with SHA-256
`2f1fdfbecd39de93bad53e2a85258959e5114e1f049787ac15c763e8fc8f4d8d`.
Its pinned build-helper versions are in the JSON inventory. Rebuild it with
`scripts/benchmark/build_pybdsf_master_wheel.py`; the command fails if the
checkout is dirty, at another commit, the local image has another digest, the
build emits more than one wheel, or the platform artifact has another checksum.

## Evidence and remaining limits

The compact and representative released/master evidence documents in
`config/baselines/` contain exact environment, configuration, dataset,
software, and container identities. The separate representative-dataset
inventory binds both images, both sky models, the sector vertices, and the
Measurement Set tree without committing restricted data.

Three reproducibility limits remain explicit rather than blocking the captured
reference evidence:

- later Hebog runs must capture the digest of their own application image;
- the source container definitions still use mutable parent tags, so a rebuild
  must record newly resolved parents; and
- the original Rapthor run moved its intermediate sky-model files, so the
  controlled rerun uses the corresponding generated rich-demo source models
  frozen by checksum.

These limits prohibit treating a future rebuild as byte-identical without new
evidence. They do not weaken the immutable identity of the completed runs.
