# Reference-finder container recipes

These Containerfiles build isolated Linux runtimes for the comparison source
finders. `scripts/benchmark/prepare_notebook_comparison.py --build-images`
uses them to create the local PyBDSF and Aegean images for the campaign
comparison notebook; see
[Use the notebooks and refresh comparisons](../../../../docs/how-to/notebooks.md).

| File | Purpose |
| --- | --- |
| `Containerfile.pybdsf` | `released` target: PyBDSF 1.14.1 built from the published sdist. `master` target: a locally built PyBDSF `master` wheel for matched performance benchmarks. |
| `Containerfile.aegean` | AegeanTools 2.3.5 from the published wheel. |
| `requirements-*.txt` | Complete pinned Python inventories for the build and runtime stages. |

## Input artifacts

Build from a temporary context that contains the applicable Containerfile,
its requirements files and these exact artifacts. Each Containerfile verifies
the checksum before installation.

| Artifact | SHA-256 |
| --- | --- |
| `bdsf-1.14.1.tar.gz` | `8d5113fecca19bb9f02a1a3e17aeb8f2d22c712cac9504e44271c4071f5434d2` |
| `bdsf-1.14.2.dev40+gc70103be3-cp312-cp312-linux_aarch64.whl` | `2f1fdfbecd39de93bad53e2a85258959e5114e1f049787ac15c763e8fc8f4d8d` |
| `aegeantools-2.3.5-py3-none-any.whl` | `dda95cb525e229b60bc357d3e5fc454cac20f364ee8aa10b730c2f7223da428d` |

The notebook setup downloads the two published packages from PyPI and checks
their hashes. The `master` wheel is produced by
`scripts/benchmark/build_pybdsf_master_wheel.py`; it is needed only for the
`master` target.

## Manual build

From a prepared context:

```console
podman build --target released --file Containerfile.pybdsf \
  --tag localhost/hebog-notebook-pybdsf:1.14.1 .
podman build --file Containerfile.aegean \
  --tag localhost/hebog-notebook-aegean:2.3.5 .
podman build --target master --file Containerfile.pybdsf \
  --tag localhost/hebog-pybdsf-master:c70103be3 .
```

Ubuntu package repositories and OCI layer timestamps are not
content-addressed, so every rebuild receives a new image identity. The
notebook setup records the actual image ID and dependency inventory of each
run instead of requiring a historical image.
