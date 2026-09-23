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
| Input | One two-dimensional FITS image; leading axes of length one are allowed. |
| Units | `BUNIT=Jy/beam`. |
| Coordinates | ICRS or FK5 J2000 celestial WCS. A header with `EQUINOX = 2000` and no `RADESYS`, as written by WSClean, is FK5 J2000. Catalogue positions are always ICRS. Other frames are rejected. |
| Beam and frequency | Finite positive `BMAJ` and `BMIN`, a `BPA`, and a positive reference frequency. The request can supply a value the header omits, never one it already has. |
| Image size | At most 3,000 pixels on each side. Larger images fail before analysis. |
| Invalid pixels | NaN pixels are excluded from estimation, detection and measurement. |
| Profiles | `continuum` (default), or `compact`, which omits extended-source association and reports `extended-emission-incomplete`. |
| Thresholds | Caller-set detection and island thresholds (island below detection), minimum and optional maximum island size. |
| Execution | `SerialExecutor`, `ThreadExecutor`, or `DaskExecutor` with a client you own. Dask workers need the image and the output directory's parent on shared storage. All must give the same products. |
| Output | A new directory with `catalogue.fits`, `rms.fits`, `source-mask.fits` and `diagnostics.json`. Existing directories are never overwritten. |

Every scientific step already runs on bounded tiles through the executor, and
an image larger than 2,048 pixels on either side is reconciled across several
tiles rather than held as one. The size limit remains because the driver still
assembles some complete image planes; raising it is current work.

## Scientific status

Hebog is suitable for demonstrations, integration work, algorithm inspection
and bounded evaluation. It is **not** yet suitable for claiming
interchangeability with PyBDSF or readiness for a survey.

In the most recent synthetic comparison campaign, no comparison against
released PyBDSF, PyBDSF `master` or Aegean failed, and 19 of 676 PyBDSF
comparisons were statistically inconclusive. The campaign was nevertheless
recorded as a fail, because 32 comparisons regressed slightly against an
earlier Hebog version, mainly in uncertainty calibration and in some centroid
and flux tails. Later changes have focused regression, Serial/Dask and
packaging evidence only. The
[scientific campaign overview](scientific-campaign-overview.md) lists every
non-passing comparison. All of this is development evidence, not
qualification.

Known limitations when interpreting results:

- Uncertainties are not yet calibrated across all morphologies and
  signal-to-noise ratios.
- Extended-source flux-error tails and centroid offsets are worse than in an
  earlier Hebog candidate.
- Faint extended emission is sensitive to association, mask-boundary and
  aperture decisions.
- A detection whose Gaussian fit fails has no Gaussian-component row.
- An image with no usable positive RMS yields an all-NaN RMS product, an empty
  catalogue and a zero mask. This is not evidence of an empty sky.
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
