# Validation dataset manifests

Hebog identifies validation data through strict, versioned JSON manifests.
The initial development manifest is
`config/datasets/phase-0-development.json`. A manifest can be loaded without
resolving, downloading, or generating any image:

```python
from pathlib import Path

from hebog.validation.datasets import load_dataset_manifest

manifest = load_dataset_manifest(
    Path("config/datasets/phase-0-development.json")
)
```

## Governance

Every dataset has exactly one role:

- `development` data supports routine red-green-refactor work;
- `regression` data preserves a reviewed defect or scientific decision;
- `qualification` data is frozen before the corresponding algorithm work and
  is held out from routine tuning.

Each entry records its purpose, provenance, redistribution status, restoring
beam, WCS, expected image statistics, complete synthetic recipe, and canonical
recipe SHA-256. Manifest angles are degrees, pixel coordinates are explicit
`(x, y)` values, array shapes are `(y, x)`, and flux densities are Jy/beam.
The schema rejects unknown fields, duplicate identifiers, invalid source
geometry, stale checksums, and inconsistent statistics.

A recipe checksum protects the generation inputs. It is not an artifact
checksum for a materialised FITS file. Frozen released-PyBDSF and
PyBDSF-`master` reference products will additionally record artifact checksums,
complete tool revisions, and configuration in their own Phase 0 manifest.

## Deterministic generation

Synthetic noise is derived from the generator version, seed, and global pixel
address. It does not depend on call order, tile shape, or worker assignment.
Consequently, independently generated windows stitch together exactly to the
same values as a one-window image:

```python
from hebog.validation.datasets import generate_synthetic_window

dataset = manifest.datasets[0]
window = generate_synthetic_window(
    dataset.recipe,
    y_start=0,
    y_stop=32,
    x_start=0,
    x_stop=32,
)
```

`generate_synthetic_image` is a convenience for bounded unit-test images and
rejects a complete allocation above its safety limit by default. Use
`generate_synthetic_window` for large planes, including the future
100,000-by-100,000 qualification recipe. Tests never regenerate expected
reference products implicitly.

::: hebog.validation.datasets
    options:
      show_symbol_type_toc: true
