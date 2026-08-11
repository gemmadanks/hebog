# Phase 5 reference-runtime reconstruction

These definitions reconstruct the four Linux/arm64 runtimes needed by the
Step 2C-P external comparison. They are rebuild definitions, not a replacement
authorization: every build has a new OCI identity and must be reviewed and
bound in a new execution decision before the one-look campaign can run.

## Frozen inputs

Build PyBDSF and Aegean from a temporary context containing the applicable
Containerfile, its checked-in requirements files, and these exact artifacts:

| Artifact | SHA-256 |
| --- | --- |
| `bdsf-1.14.1.tar.gz` | `8d5113fecca19bb9f02a1a3e17aeb8f2d22c712cac9504e44271c4071f5434d2` |
| `bdsf-1.14.2.dev40+gc70103be3-cp312-cp312-linux_aarch64.whl` | `2f1fdfbecd39de93bad53e2a85258959e5114e1f049787ac15c763e8fc8f4d8d` |
| `aegeantools-2.3.5-py3-none-any.whl` | `dda95cb525e229b60bc357d3e5fc454cac20f364ee8aa10b730c2f7223da428d` |

The released PyBDSF source archive is the published 1.14.1 sdist. The master
wheel is the frozen output of `build_pybdsf_master_wheel.py` at commit
`c70103be3ae9ae9908286f144e6ce956acc0ce5c`; it is retained under the ignored
`benchmark-results/wheels/` directory on the controlled host. The Aegean wheel
is the published AegeanTools 2.3.5 wheel. The Containerfiles verify every
artifact checksum before installation.

## Build commands

From the prepared temporary context, build the three reference images with:

```console
podman build --platform linux/arm64 --target released \
  --file Containerfile.pybdsf \
  --tag localhost/rapthor-dev:ci-aligned-reconstructed .
podman build --platform linux/arm64 --target master \
  --file Containerfile.pybdsf \
  --tag localhost/hebog-pybdsf-master:c70103be3-reconstructed .
podman build --platform linux/arm64 \
  --file Containerfile.aegean \
  --tag localhost/hebog-aegean:2.3.5-step2cp-reconstructed .
```

Build Hebog only from a clean archive of
`106715b22b9858149e42467f4e2c581f15961cb0`. Place
`Containerfile.hebog` at the archive root, then run:

```console
podman build --platform linux/arm64 \
  --file Containerfile.hebog \
  --tag localhost/hebog:phase5-external-106715b-reconstructed .
```

The Hebog definition pins the two parent identities used by the approved
runtime. The Python lockfile and clean source archive reproduce its scientific
inventory and source tree. Package requirements for each external reference
pin the complete resolved Python inventory observed in the reconstruction.
Ubuntu package repositories and OCI layer timestamps are not content-addressed
by these definitions, so a later rebuild must still receive a new image
identity and cannot claim bitwise equality with an earlier local image.

## Current reconstructed identities

The 2026-08-11 reconstruction produced:

| Runtime | Image digest | Dependency inventory SHA-256 |
| --- | --- | --- |
| Hebog | `sha256:f78be6d330859cdd0889c476e26c884796f4991aaaf7bec52b90aa14a23c46ce` | `d383be3a97d716ce033b1151a5282729794dbc5f1734081d3ed36bcd2409b5a2` |
| PyBDSF 1.14.1 | `sha256:72454074489d5ed0d0ed08781ec11411a3e25ccf75e3378a924152176fa15b37` | `8211043e9fca55d706d1e890e2bf0b630e228a854db0949258c498506975669f` |
| PyBDSF master | `sha256:192964b32d50a6e960cf3710013ffa92d782ecf43a4d6def4309a7cb10911e73` | `83574dd4c15d79f3cf2ac52fb8aa7b5bd2ff323c93343b2f1337eec938e8bf99` |
| AegeanTools 2.3.5 | `sha256:6dd2064c5f5718e584d413ecb1fa6338306662693d0384b398630d639b5e22d3` | `17d1e3c1d84b13612153ad11d5478065712731a181adb1dfe2c2c180859eaaed` |

The two PyBDSF inventories are identical except for the `bdsf` version. The
Hebog source tree remains exactly
`471bed9a428df10d9139afc334d97b5df190f4f64e6dd6daeb91f9b436d37362`.
