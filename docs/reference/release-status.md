# Capability and status

Hebog is an **experimental** radio-continuum source finder. It runs a complete
standalone analysis on the inputs below. It is not scientifically qualified
for survey use and is not a production Rapthor backend.

This page describes the source checkout, which can be ahead of the latest
[release](https://github.com/gemmadanks/hebog/releases). Pin an exact `0.x`
version when results must be repeatable.

## Supported inputs and behaviour

| Aspect | Supported |
| --- | --- |
| Input | One two-dimensional FITS image; leading axes of length one are allowed, and a Stokes axis must select Stokes I. The [input header contract](input-header-contract.md) lists what each common imager writes and what to supply. |
| Units | `BUNIT=Jy/beam`, or a supplied unit when the header has no `BUNIT`. |
| Coordinates | ICRS or FK5 J2000 celestial WCS. A header with `EQUINOX = 2000` and no `RADESYS`, as written by WSClean, is FK5 J2000. Catalogue positions are always ICRS. Other frames are rejected. |
| Beam and frequency | Finite positive `BMAJ` and `BMIN`, a `BPA`, and a positive reference frequency. The request can supply a value the header omits, never one it already has. |
| Image size | At most 15,402 pixels on each side. Larger images fail before analysis. |
| Invalid pixels | NaN pixels are excluded from estimation, detection and measurement. |
| Profiles | `continuum` (default), or `compact`, which omits extended-source association and reports `extended-emission-incomplete`. |
| Thresholds | Caller-set detection and island thresholds (island below detection), minimum and optional maximum island size. |
| Execution | `SerialExecutor`, `ThreadExecutor`, or `DaskExecutor` with a client you own. Dask workers need the image and the output directory's parent on shared storage. All must give the same products. On Windows, threads of one process take turns at FFT convolutions, because SciPy's Windows wheels share an unlocked FFT plan cache. |
| Output | A new directory with `catalogue.fits`, `rms.fits`, `source-mask.fits` and `diagnostics.json`. Existing directories are never overwritten. |

Every scientific step already runs on bounded tiles through the executor, an
image larger than 2,048 pixels on either side is reconciled across several
tiles rather than held as one, and the driver holds no image-sized plane. The
size limit rises one tier at a time, as each tier's memory and invariance
evidence is measured. A serial run of the whole 15,402² LoTSS-DR3 mosaic 1312
allocates at most 1.7 GiB, traced in two agreeing repetitions. That peak is
one tile's working set plus records the passes keep from every tile, which
still grow about 1.7 bytes a pixel; bounding them, and an unattributed term
in background and RMS, is planned before much larger images are admitted. A
four-worker local Dask cluster finishes the 10,000² anchor in 0.61 of the
serial time with identical products; the whole mosaic has not been timed
under Dask since that was repaired. Separately, one declared limit remains:
an object wider than a task's read budget is still reduced on the driver
from its own pixels, so that memory grows with the object rather than the
tile, by up to 186 bytes an object pixel. One connected object filling a
15,402-pixel field would need about 44 GB on the driver. No object in the
real LoTSS-DR3 fields measured comes near that; the widest measured case, a
generated filament of 553,817 pixels, cost about 100 MB. The
[performance profile](performance-profile.md#what-scales-with-the-tile-and-what-with-the-image)
has the figures.

## Scientific status

Hebog is suitable for demonstrations, integration work, algorithm inspection
and bounded evaluation. It is **not** yet suitable for claiming
interchangeability with PyBDSF or readiness for a survey.

Development comparisons against PyBDSF and Aegean on simulated and public
images are recorded in the repository's
[execution log](https://github.com/gemmadanks/hebog/blob/main/LOG.md) and
[implementation plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md).
They are development evidence, not qualification.

Known limitations when interpreting results:

- Uncertainties are not yet calibrated across all morphologies and
  signal-to-noise ratios.
- Extended-source flux errors have wide tails and centroids can be offset.
- Faint extended emission is sensitive to association, mask-boundary and
  aperture decisions.
- A detection whose Gaussian fit fails has no Gaussian-component row.
- An image with no usable positive RMS yields an all-NaN RMS product, an empty
  catalogue and a zero mask. This is not evidence of an empty sky.
- In a field so crowded that no fine noise window lies clear of its sources,
  the background and RMS are the unprotected sigma-clipped coarse estimate,
  which includes the sources' wings.
- Crowded fields are associated and fitted incorrectly, a known defect the
  [implementation plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md)
  tracks. On small images a crowded field's islands can collapse into a
  few sources with no Gaussian-component row: generated fields of 160 to
  300 pixels with a source every 16 to 24 pixels did, and 119 islands of a
  240-pixel field became 2 sources. In a generated 1,024-pixel field with a
  source every 32 pixels, 962 islands became 574 sources where PyBDSF finds
  1,006, and 11% of the joint Gaussian fits were deferred at their work
  bound; with a source every 24 pixels nearly all were.
- The `compact` profile is not a general continuum catalogue.
- Completeness, reliability, astrometry and photometry must be evaluated on
  data representative of your use.

Always read `diagnostics.json` with the catalogue. It records every detected
source and component, including those without a catalogue row. Its
`configuration_qualification` field reads `development-unqualified` for the
example 5σ/3σ/seven-pixel settings and `custom-unqualified` otherwise; both
describe validation status, not whether the run succeeded.

## Integration status

The standalone API is implemented and tested as an independent library.
Requests and results hold paths and small serializable records, never open
files, image arrays or scheduler clients. Distinct exception types separate
invalid input, unsupported metadata, oversized images and existing output
directories.

One call analyses one image. Hebog does **not**:

- combine primary-beam-corrected and flat-noise images;
- filter or group a sky model;
- write Rapthor or LSMTool file names or tables;
- manage retries, scheduling or cluster resources; or
- provide a qualified replacement for Rapthor's complete `filter_skymodel`
  step.

See [Integrate Hebog into a pipeline](../how-to/integrate-into-a-pipeline.md).

## Compatibility between releases

Hebog promises no backward compatibility between `0.x` releases. An API,
output schema or measurement can change directly. Products carry schema
versions, and Hebog's readers reject unsupported versions and verify each
file's role, size and SHA-256. Schema numbers are listed in the
[output reference](public-products.md); they are software checks, not
scientific maturity levels.

`hebog.validation` is development tooling for this repository's comparison
scripts. It is not part of the public API and is not installed from a wheel.

## Release boundaries

A release has a tested public workflow, an installable package, current
documentation and stated limitations. It does **not** imply scientific
equivalence with another finder, qualification for a survey, support beyond
the table above, Rapthor integration, a demonstrated speed advantage, or
compatibility with later releases.

Releases are tagged on GitHub and uploaded to TestPyPI to exercise
[publishing](../how-to/publish-releases.md). Uploads will move to PyPI once
the size limit is useful beyond cut-outs.
