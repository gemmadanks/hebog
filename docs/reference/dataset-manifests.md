# Validation dataset manifests

Hebog identifies validation data through strict, versioned JSON manifests
under `config/datasets/`, with separate development, regression, and
qualification manifests. `hebog.validation` is repository tooling and is not
installed from the Hebog wheel; use it from a source checkout after
`uv sync --all-groups`. A manifest can be loaded without resolving,
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
complete tool revisions, and configuration in their own manifest.

The 30,000-square regression and 100,000-square qualification entries are
logical recipes: tests generate bounded windows and must never allocate the
whole plane. The qualification case is held out from routine tuning even
though its seed is necessarily recorded for reproducibility.

Generator version 2 leaves every version-1 recipe and checksum unchanged. It
can declare an affine, globally addressed RMS multiplier,
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
recipe SHA-256 continues to identify the shared truth recipe. Only generator
versions 3 and 4 accept them: under versions 1 and 2 two seeds give one noise
field with its pixels rearranged, so a record of those versions that lists
noise realization seeds is refused (see
[independent realizations](#independent-realizations)). The rule is checked
when a record is validated, as every manifest rule is, so
`model_copy(update=...)` skips it, and it cannot see a population built from
separate single-seed records of those versions. Draw any new population
with version 4.

`validation_strata` names possibly overlapping sets of analytic source
indices. These declarations keep SNR, shape, blend, edge, or other governed
populations explicit and let qualification code prove the required sample
count before looking at scientific results. Stratum identifiers and indices
are unique, indices are sorted and non-negative, and every index resolves to
source truth in the shared recipe. The compact qualification manifests use
200 independent noise realizations whose powered source population supplies
at least 1,600 eligible measurements in every SNR, shape, and edge stratum,
which gives the entire-confidence-interval test useful power without selecting
favourable seeds.

The `phase-4-paired-regression.json` manifest is viewable regression and TDD
data, not qualification data. Its 200 seeds are disjoint from every
qualification population. Each realization holds 33 observable groups: 32
individually resolvable sources, eight beam-compatible point sources, one
clearly resolved source, and one unresolved blend, with a distinct WCS,
background, noise gradient, invalid region, and a 180-degree mirrored layout.
No current test runs it through the finder: the tests that did ran a compact
measurement path `find_sources` never used, and were removed with it.

Manifest schema 2 also records `association_truth_groups`. Every
analytic emitter belongs to exactly one canonical group. A singleton group is
`individually-resolvable`; two or more emitters that produce one eligible
observed maximum are an `unresolved-blend`. Each group freezes its identifier,
member indices, resolution class, integrated-brightness-weighted `(x, y)`
centroid, and summed analytic Gaussian brightness. Validation recomputes the
centroid and total from emitter truth and rejects overlaps, omissions, stale
quantities, or ambiguous group strata.

`association_group_strata` names group-level qualification populations
separately from per-emitter `validation_strata`. This prevents unresolved
members from entering individual completeness, position, flux, or shape
denominators while retaining them in provenance. Qualification inputs are
frozen before any result is generated or inspected.

Generator version 3 adds an explicit elliptical Gaussian noise-correlation
function in image-pixel coordinates. It generates an expanded deterministic
white-noise window, applies an L2-normalized Gaussian filter whose
autocorrelation has the declared FWHM covariance, and crops the requested
window. The result has the requested RMS and stitches exactly across arbitrary
window layouts, including image edges. The compact datasets use the
restoring-beam covariance as this correlation function; generator versions 1 and 2 and their
checksums remain unchanged.

Generator version 4 gives every seed an independent noise realization, with
or without a noise correlation. It accepts every version 2 and version 3
field, and its checksum covers the whole recipe, including whether the noise
is correlated. Use it for every new population; earlier versions remain so
that their frozen recipes rebuild exactly.

## Independent realizations

Every pixel's noise is a hash of the seed and the pixel address. Versions 1
and 2 address the plane row by row and combine that address with the seed by
XOR before hashing. Two seeds that differ by `d` in their bits then give one
field, with the value at address `a` moved to address `a ^ d`: seeds 1000 and
1001 swap neighbouring pixels, and seeds whose XOR is below 16 give identical
sums over aligned 16-pixel blocks. A source's measured flux error is
therefore correlated between such images, and they are not independent
samples. The 23 September flux-calibration population drew its white-noise
images this way, with seeds 2 apart; `m1-flux-calibration.json` holds its
replacement, drawn with version 4.

Version 3 hashes the row and the column separately before combining them
with the seed, so the address is a pseudo-random 64-bit value and a seed
difference moves a pixel's value to an address that almost never belongs to
the same image. Version 4 hashes the seed as well, so seeds that differ in a
few bits enter the hash as unrelated keys. For both versions the unit tests
check that nearby seeds share no noise value and that their 16-pixel block
sums are uncorrelated.

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
