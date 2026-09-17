# Current capability and release status

Hebog is an **experimental** radio-continuum source finder. It can run a
complete standalone analysis for the supported inputs below, but it is not yet
scientifically qualified for general survey use and is not a production or
default Rapthor backend.

The source checkout may contain changes that have not been released. Use
[GitHub releases](https://github.com/gemmadanks/hebog/releases) to identify
published versions, and pin an exact `0.x` version when results need to be
repeatable.

## What works today

`hebog.find_sources(request, config, executor)` analyses one FITS image and
publishes four files as a single output bundle:

- a catalogue containing islands, sources, and fitted Gaussian components;
- a local RMS image;
- an image-aligned source-support mask; and
- diagnostics describing provenance, measurement availability, fitting, and
  source-association decisions.

The finder implements background and noise estimation, direct and multiscale
detection, bounded deblending, Gaussian fitting, source association, source
photometry, and atomic product publication. Start with
[Find sources](../tutorials/find-sources.md), then use
[How Hebog finds sources](../explanation/how-hebog-works.md) and the
[public-output reference](public-products.md) when evaluating results.

| Boundary | Supported behaviour |
| --- | --- |
| Input | One two-dimensional FITS image, or singleton leading axes followed by two spatial axes. |
| Physical metadata | ICRS or FK5 J2000 celestial WCS, `BUNIT=Jy/beam`, finite positive restoring-beam axes with a position angle, and a positive reference frequency. FK5 J2000 includes headers with `EQUINOX = 2000` and no `RADESYS`, as written by WSClean; catalogue positions are always converted to ICRS. Other frames and equinoxes are rejected. A request can supply a reference frequency or beam value that the header omits, but not one it already provides. |
| Image size | No more than 1,024 pixels along either spatial axis. Larger inputs fail before analysis. |
| Invalid pixels | NaN pixels are allowed and excluded from estimation, detection, and measurement. |
| Profiles | `continuum` is the default. `compact` deliberately omits extended-source association and reports `extended-emission-incomplete`. |
| Thresholds | Positive detection and island thresholds supplied by the caller, with the island threshold lower than the detection threshold; explicit minimum and optional maximum island sizes. |
| Execution | Deterministic `SerialExecutor`, or `DaskExecutor` with a Dask client owned by the caller. Hebog does not create or close a cluster. Dask workers need the input image and the output directory's parent on shared storage. |
| Publication | A new caller-owned directory containing `catalogue.fits`, `rms.fits`, `source-mask.fits`, and `diagnostics.json`. Existing directories are never overwritten. |

Background/RMS estimation uses bounded tiles. Later measurement stages operate
on the complete admitted image, which is why the public size limit applies.
Serial and existing-Dask execution are required to produce the same scientific
products.

## Scientific status

The public finder is suitable for demonstrations, integration work, algorithm
inspection, and bounded scientific evaluation. It is not yet suitable for an
unqualified statement that Hebog is interchangeable with PyBDSF or ready for a
particular survey.

In the most recent synthetic comparison campaign, no comparison against
released PyBDSF, PyBDSF `master` or Aegean failed; 19 of the 676 PyBDSF
comparisons were statistically inconclusive. The campaign was recorded as a
fail only because 32 comparisons regressed slightly against an earlier Hebog
version, mainly in uncertainty calibration and some centroid and flux tails.
Later changes, including the current composition, have focused regression,
Serial/Dask, equivalence and installed-wheel evidence only. The
[scientific campaign overview](scientific-campaign-overview.md) records every
non-passing comparison. This is development evidence: Hebog is not yet
scientifically qualified, and no release claims general parity with PyBDSF.

Diagnostics label the example 5-sigma detection, 3-sigma island, seven-pixel
configuration as `development-unqualified`. Other valid settings are labelled
`custom-unqualified`. These labels describe validation status, not whether the
software completed successfully.

Current limitations that matter when interpreting results are:

- uncertainty calibration is not yet established across the full supported
  morphology and signal-to-noise range;
- extended-source flux-error tails, signed extended-source centroid offsets
  and unresolved-axis retention are worse than for an earlier Hebog candidate;
- faint extended emission can remain sensitive to association, mask-boundary,
  and aperture-flux decisions;
- a failed or scientifically inadmissible Gaussian fit can leave a valid
  detection or source without a Gaussian-component row;
- an image with no usable positive RMS estimate returns an all-NaN RMS product,
  an empty catalogue, and a zero mask; this is not evidence that the sky
  contains no emission;
- the `compact` profile must not be presented as a general continuum-source
  catalogue; and
- completeness, reliability, astrometry, photometry, deblending, and extended
  emission performance must be evaluated on data representative of the
  intended use.

Use `diagnostics.json` with the catalogue. It records every established source
and component identity, including unavailable and deferred measurements, so a
missing catalogue row is not mistaken for a non-detection.

## Integration status

The standalone scientific API is implemented and tested as an independent
library boundary. Requests and results contain paths and small serializable
records, never open FITS handles, full mutable images, or scheduler clients.
Public exception types distinguish invalid input, unsupported physical
metadata, oversized images, and existing output destinations.

The public call analyses one scientific image. It does **not**:

- combine primary-beam-corrected and flat-noise image branches;
- filter or group an existing sky model;
- emit Rapthor/LSMTool compatibility filenames or tables;
- manage retries, workflow scheduling, or cluster resources for a parent
  pipeline; or
- provide a production-qualified complete `filter_skymodel` replacement.

An integrating pipeline must own those workflow-specific responsibilities.
Hebog's Rapthor adapter and complete-path performance have not yet met the
requirements for supported deployment or default cutover.

## Output and API compatibility

The current public result contains versioned, validated catalogue, image, and
diagnostic products. Readers reject unsupported schemas and verify a supplied
product record's role, byte count, and SHA-256 before parsing it.

Hebog does not promise backward compatibility between experimental `0.x`
releases. A release may change a public API, output schema, or scientific
meaning directly. Integrators should:

1. pin an exact Hebog version;
2. persist the complete `SourceFinderResult`, not only file paths;
3. use Hebog readers where possible;
4. preserve unknown quality flags;
5. check product scientific status explicitly; and
6. review current documentation and release notes before upgrading.

The `hebog.validation` package is development tooling for the repository's
comparison scripts and tests. It is not part of the source-finding API and is
not installed from a wheel; use a source checkout with `uv sync --all-groups`.

Schema numbers are documented in the
[public-output reference](public-products.md). They are compatibility checks
for software, not scientific maturity levels that users need to interpret.

## Release boundaries

An experimental release has a tested public workflow, installable package,
current documentation, and explicit known limitations. It does **not** imply:

- general scientific equivalence with another source finder;
- qualification for an observing programme or survey;
- support for inputs outside the table above;
- production Rapthor integration;
- a demonstrated end-to-end speed advantage; or
- long-term compatibility with a later `0.x` release.

Release Please prepares version changes, release notes, tags, and GitHub
releases. The publishing workflow builds distributions from the tagged commit
and uploads them to TestPyPI using
[Trusted Publishing](../how-to/publish-releases.md), which exercises the
release path without presenting Hebog as ready for general installation.
Uploads move to PyPI once the supported input envelope is useful beyond
cut-outs; until then a tagged GitHub release is the installable artifact. Maintainers should release
only after the intended change has passed its required pull-request checks and
the limitations on this page remain accurate.
