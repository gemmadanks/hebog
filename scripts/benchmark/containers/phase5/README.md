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
  --tag localhost/hebog-aegean:2.3.5-step2cp-reconstructed-matched .
```

Build Hebog only from a clean archive of
`303a49de3ea37af795d34e361f522a419d5c0bc2`. Place
`Containerfile.hebog` at the archive root, then run:

```console
podman build --platform linux/arm64 \
  --file Containerfile.hebog \
  --label org.opencontainers.image.revision=303a49de3ea37af795d34e361f522a419d5c0bc2 \
  --tag localhost/hebog:phase5-external-303a49d-reconstructed-final .
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
| Hebog | `sha256:728bbd7ab59d0fbb9537d36fac34652e640300091024498cbebdaeb452da55a6` | `d383be3a97d716ce033b1151a5282729794dbc5f1734081d3ed36bcd2409b5a2` |
| PyBDSF 1.14.1 | `sha256:72454074489d5ed0d0ed08781ec11411a3e25ccf75e3378a924152176fa15b37` | `8211043e9fca55d706d1e890e2bf0b630e228a854db0949258c498506975669f` |
| PyBDSF master | `sha256:192964b32d50a6e960cf3710013ffa92d782ecf43a4d6def4309a7cb10911e73` | `83574dd4c15d79f3cf2ac52fb8aa7b5bd2ff323c93343b2f1337eec938e8bf99` |
| AegeanTools 2.3.5 | `sha256:b496d2907c13d083e7c87eda61a6a40057f92b5cb6e605330bcb1b6db27158b8` | `346c1f32b0d78ce1d22f6d6ff20787a102d8491c14432865465596c9f41ba909` |

The two PyBDSF inventories are identical except for the `bdsf` version. The
final Hebog source tree is
`2f80c8779d3d8fe91fc599aa98edd95491d13922667cbab3af9d178caecc225b`.
The Aegean replacement deliberately retains the originally frozen NumPy
2.5.2, SciPy 1.17.1, Astropy 7.2.2, and LMFit 1.3.4 scientific stack.

## Step 2C-PF successor candidate

The prospective successor was built from a clean archive of
`c1f7eb0bdf5e8581e0024f0f7469c2908a22a594` with the same definition and an
overriding revision label:

```console
podman build --platform linux/arm64 \
  --file Containerfile.hebog \
  --label org.opencontainers.image.revision=c1f7eb0bdf5e8581e0024f0f7469c2908a22a594 \
  --label org.hebog.phase=5-step-2c-pf-successor \
  --tag localhost/hebog:phase5-external-successor-c1f7eb0 .
```

The resulting Linux/arm64 image ID is `0f362268f4ff...` and immutable digest
is `sha256:d0c1319072c3716811ed51452fe83d92be8f8d2b62a11795678f31037b7b1f68`.
Network-disabled checks inside it reproduce source tree `d50be758...` and
dependency inventory `d383be3...`. These identities are pending named
execution approval; they do not authorize the successor one-look.

## Post-failure campaign reconstruction

On 2026-08-14 the missing runtimes for the approved post-failure candidate
were rebuilt while the Rapthor devcontainer remained active. Hebog was built
from a clean archive of `63e4b5886a3f5acb75125d258f5b71c13ca4eeaf` using
the same definition and explicit revision/phase labels:

```console
podman build --platform linux/arm64 \
  --file Containerfile.hebog \
  --label org.opencontainers.image.revision=63e4b5886a3f5acb75125d258f5b71c13ca4eeaf \
  --label org.hebog.phase=5-external-post-failure-reconstruction \
  --tag localhost/hebog:phase5-external-post-failure-63e4b58-reconstructed .
```

| Runtime | Image ID | Image digest |
| --- | --- | --- |
| Hebog | `3f579507eafbff9ae0193e869f3f2cfbda83bf40668755857ca36c0027cfebfd` | `sha256:4341ec7946b737613178d407af5e26a2ec28e7aca6ffe40bf90abf879aeb9061` |
| PyBDSF 1.14.1 | `d63070b376ada2e8175dbcaeb64b0d462a3d064c416549c961ce789b26afd0da` | `sha256:c6dca91f0b32fd217460a5a2332e42a99fe68e6f1c11431af092e6be53e98bb8` |
| PyBDSF master | `3186a4b5ad49d049dd657875b213550a7e8f4ae73db4f4ef7037510058741d43` | `sha256:81fc680669bbf92dcac9b68be8d7a18e6b30a0826b0e2e7b63c05f81f1f304ca` |
| AegeanTools 2.3.5 | `d3a84d4175c45e8cd22e03f6d20ffb0e0b5590908ef0317fcb1fa8c562c70ca5` | `sha256:738591844996e672e8679a5f4b9233a1bd7bc06698af4aef69b4efff7f3b1551` |

The candidate source-tree hash remains `864d8f2b...`; all dependency inventory
hashes match the frozen values above. The changed OCI identities arise from a
new build and require a new named execution approval. They are not evidence of
a scientific change or authorization to open the one-look campaign.
