# Validation dataset manifests

Hebog identifies validation data through strict, versioned JSON manifests.
Phase 0 freezes separate development, regression, and qualification manifests
under `config/datasets/`. A manifest can be loaded without resolving,
downloading, or generating any image:

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
PyBDSF-`master` reference products additionally record artifact checksums,
complete tool revisions, and configuration in their own Phase 0 manifest.

The 30,000-square regression and 100,000-square qualification entries are
logical recipes: tests generate bounded windows and must never allocate the
whole plane. The qualification case is held out from routine tuning even
though its seed is necessarily recorded for reproducibility.

Phase 4 adds generator version 2 without changing any version-1 recipe or
checksum. Version 2 can declare an affine, globally addressed RMS multiplier,
non-overlapping half-open invalid rectangles, unequal pixel scales, and WCS
rotation metadata. Invalid rectangles materialise as NaN and are included in
the checked expected finite fraction. Both the RMS field and invalid pixels
are derived from global coordinates, so window generation remains exact.
FITS materialisation combines the signed `CDELT` scales with an explicit `PC`
matrix, preserving the declared rotation and unequal pixel scales while
leaving version-1 zero-rotation fixtures byte-identical. Its celestial linear
transform is `R(theta) @ diag(scale_x, scale_y)`: the declared angle rotates
the signed pixel-axis vectors counterclockwise in the celestial intermediate
plane. Generator-v2 beam axes and position angle likewise describe an ellipse
in the generator pixel plane. FITS materialisation transforms that covariance
through the same matrix and writes the resulting celestial `BMAJ`, `BMIN`, and
east-of-north `BPA`. This keeps beam-matched source truth physically
consistent under rotation and unequal scales.

A dataset may also record additional `noise_realization_seeds`. The base
recipe plus these seeds define one governed Monte Carlo campaign: source
truth, image geometry, background, RMS field, masks, beam, and WCS remain
identical while only the deterministic noise realization changes. Use
`iter_dataset_recipes` to expand the campaign. Seeds are unique, do not repeat
the base seed, and remain part of manifest provenance even though the base
recipe SHA-256 continues to identify the shared truth recipe.

`validation_strata` names possibly overlapping sets of analytic source
indices. These declarations keep SNR, shape, blend, edge, or other governed
populations explicit and let qualification code prove the required sample
count before looking at scientific results. Stratum identifiers and indices
are unique, indices are sorted and non-negative, and every index resolves to
source truth in the shared recipe. The Phase 4 qualification campaign freezes
200 independent deterministic noise realizations, so even its single-source
edge stratum reaches the reviewed minimum of 200 samples before any scientific
output is inspected.

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
