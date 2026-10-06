# Validation dataset manifests

Hebog identifies validation data through strict, versioned JSON manifests
under `config/datasets/`. `hebog.validation` is repository tooling, not
installed from the wheel; use it from a source checkout after
`uv sync --all-groups`. Loading a manifest validates metadata only and never
downloads or generates an image:

```python
from pathlib import Path

from hebog.validation.datasets import load_dataset_manifest

manifest = load_dataset_manifest(
    Path("config/datasets/phase-0-development.json")
)
```

## Roles and governance

Every dataset has exactly one role: `development` for routine
red-green-refactor work, `regression` to preserve a reviewed defect or
decision, or `qualification`, frozen before the algorithm work and held out
from tuning. Each entry records purpose, provenance, redistribution status,
restoring beam, WCS, expected image statistics, the complete synthetic recipe
and the recipe's canonical SHA-256. Angles are degrees, pixel coordinates are
explicit `(x, y)`, shapes are `(y, x)` and flux densities are Jy/beam. The
schema rejects unknown fields, duplicate identifiers, invalid geometry, stale
checksums and inconsistent statistics.

A recipe checksum protects the generation inputs, not a materialised FITS
file; the frozen PyBDSF reference products record artifact checksums, tool
revisions and configuration in their own manifest under `config/baselines/`.
The 30,000² regression and 100,000² qualification entries are logical
recipes: tests generate bounded windows and never allocate the plane.

`validation_strata` name possibly overlapping sets of source indices (SNR,
shape, blend, edge) so that qualification code can prove sample counts before
looking at results. Manifest schema 2 adds `association_truth_groups`: every
emitter belongs to one group, `individually-resolvable` or
`unresolved-blend`, with a frozen centroid and summed brightness that
validation recomputes, and `association_group_strata` keep unresolved members
out of individual completeness and flux denominators. New populations must
be seed-disjoint from every existing manifest.

## Generator versions

| Version | Adds | Use |
| --- | --- | --- |
| 1 | Analytic Gaussian sources, uniform RMS and deterministic per-pixel noise | Frozen recipes only |
| 2 | An affine, globally addressed RMS multiplier; half-open invalid rectangles materialised as NaN; unequal pixel scales and WCS rotation, written as signed `CDELT` with an explicit `PC` matrix, through which the beam ellipse is also transformed | Frozen recipes only |
| 3 | An elliptical Gaussian noise-correlation function in pixel coordinates (the compact datasets use the restoring-beam covariance) and `noise_realization_seeds`, which define one Monte Carlo campaign over a shared truth recipe | Frozen recipes only |
| 4 | An independent noise realization for every seed, correlated or not; the checksum covers the whole recipe | Every new population |

Earlier versions remain so that their frozen recipes rebuild exactly; their
checksums never change. `iter_dataset_recipes` expands a campaign's seeds.

### Independent realizations

Every pixel's noise is a hash of the seed and the pixel address. Versions 1
and 2 combine the row-major address with the seed by XOR before hashing, so
two seeds that differ by `d` give one noise field with pixel `a` moved to
`a ^ d`: seeds 1000 and 1001 swap neighbouring pixels, and seeds whose XOR is
below 16 share every aligned 16-pixel block sum. Such images are not
independent samples, so a version 1 or 2 record that lists noise realization
seeds is refused when it is validated. Version 3 hashes row and column
separately, and version 4 hashes the seed as well, so nearby seeds share no
noise value and their block sums are uncorrelated, which unit tests check.
The 23 September flux-calibration population was drawn under version 2 with
seeds 2 apart; `m1-flux-calibration.json` is its replacement under
version 4.

## Deterministic generation

Synthetic noise depends only on the generator version, seed and global pixel
address, never on call order, tile shape or worker assignment, so
independently generated windows stitch exactly into the one-window image:

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

`generate_synthetic_image` is a convenience for bounded test images and
refuses a complete allocation above its safety limit; use
`generate_synthetic_window` for large planes. Tests never regenerate frozen
expected products implicitly.

::: hebog.validation.datasets
    options:
      show_symbol_type_toc: true
