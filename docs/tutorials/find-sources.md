# Find radio-continuum sources in a FITS image

This tutorial runs Hebog as a standalone scientific library. It uses no
Rapthor, Prefect, LSMTool, or private Dask cluster.

The interface is experimental and scientifically unqualified. A successful
run does not by itself qualify Hebog for a survey; see
[current capability and release status](../reference/release-status.md).

## Prepare the input

Use one two-dimensional FITS image, or a FITS image with only singleton axes
before its final two spatial axes. The image must have:

- pixel values in `Jy/beam`;
- an ICRS celestial WCS (`RADESYS = 'ICRS'`);
- finite positive `BMAJ` and `BMIN` restoring-beam axes and a `BPA` position angle;
- a positive reference frequency in `RESTFRQ`, `RESTFREQ`, or a frequency WCS
  axis; and
- no more than 1,024 pixels along either spatial axis.

NaN pixels are allowed and are excluded from the analysis. Missing or invalid
physical metadata fails clearly before any output bundle is published.

A header with `EQUINOX = 2000` but no `RADESYS` keyword, as written by some
imagers including WSClean, declares an FK5 frame under the FITS WCS standard.
Hebog currently rejects it with
`hebog.UnsupportedSourceFinderConfigurationError`. Add `RADESYS = 'ICRS'` only
if treating those coordinates as ICRS is acceptable for your science; FK5
J2000 and ICRS differ by tens of milliarcseconds.

## Run the continuum profile

The output directory must not already exist. Hebog treats it as one atomic,
caller-owned product bundle.

```python
from pathlib import Path

import hebog
from hebog.executors import SerialExecutor

request = hebog.SourceFinderRequest(
    image_path=Path("continuum-image.fits"),
    output_directory=Path("hebog-products"),
    run_id="observation-001",
)
config = hebog.SourceFinderConfig(
    detection_threshold_sigma=5.0,
    island_threshold_sigma=3.0,
    minimum_island_pixels=7,
)

result = hebog.find_sources(request, config, SerialExecutor())

print(f"sources: {result.source_count}")
print(f"Gaussian components: {result.gaussian_component_count}")
print(f"wall time: {result.wall_seconds:.3f} s")
print(result.catalogue_path)
```

`continuum` is the default profile. The example uses a 5-sigma detection
threshold, a 3-sigma island-growth threshold, and a seven-pixel minimum.
Diagnostics report `configuration_qualification="development-unqualified"`:
the configuration is supported for evaluation but is not survey-qualified.

For spatially admitted continuum images, background and noise have different
resolution policies. Background retains its coarse/source-protected and
bright-region estimates; RMS uses the source-protected 35/7 fine grid even
away from bright sources. Source-overlapping noise windows are excluded,
missing cells are interpolated globally and fine RMS edge values are extended
without extrapolating to zero. An absence of clean noise samples remains
unavailable. This does not lower detection thresholds or imply that noise
structure below the estimator resolution is measured accurately.

At physical image edges, background and coarse-RMS slopes use mesh samples
separated by at least the distance being extrapolated (or the full available
span on a short grid). This avoids amplifying small errors between nearly
coincident final windows. It preserves genuine affine backgrounds instead of
flattening them at the edge; interior interpolation and the constant extension
of fine RMS values are unchanged. A singleton grid still supplies a constant
estimate, not an independently measured spatial gradient.

Callers may select other valid thresholds and island-size limits. Hebog uses
those values throughout background masking, direct and multiscale detection,
island growth, and final size filtering. The continuum background stage retains
its private 75-sigma bright-candidate trigger when that exceeds the caller's
island threshold. Otherwise it uses the caller's detection threshold, which is
validated to exceed the island threshold, so refinement seeds lie within their
protected support. This does not alter the caller's detection/growth thresholds
or the standard 5/3-sigma profile. Custom runs report
`configuration_qualification="custom-unqualified"` so they cannot be confused
with the reference evidence:

```python
custom_config = hebog.SourceFinderConfig(
    detection_threshold_sigma=6.0,
    island_threshold_sigma=4.0,
    minimum_island_pixels=10,
)

custom_result = hebog.find_sources(
    hebog.SourceFinderRequest(
        image_path=Path("continuum-image.fits"),
        output_directory=Path("custom-hebog-products"),
        run_id="observation-001-custom",
    ),
    custom_config,
    SerialExecutor(),
)
```

## Interpret the products

For the full field-by-field contract, units, null handling, diagnostic census,
and evaluation checklist, see
[Public source-finder outputs](../reference/public-products.md). The summary
below introduces the distinctions needed for this example.

The returned `SourceFinderResult` contains closed paths, byte counts, SHA-256
identities, scientific status, and schema versions for four files:

| Product | Meaning |
| --- | --- |
| `catalogue.fits` | Source-level catalogue plus its Gaussian components and parent islands. |
| `rms.fits` | Hebog's local RMS estimate in `Jy/beam`; an empty image may report this as scientifically unavailable. |
| `source-mask.fits` | Binary source-support mask aligned with the input image. |
| `diagnostics.json` | Counts, configuration qualification, profile limitations, input/configuration identities, and the exact implementation identity. |

Read validated products through Hebog rather than assuming FITS extension or
column details:

```python
from hebog.io import read_catalogue_fits_product, read_diagnostics_product

catalogue = read_catalogue_fits_product(result.catalogue)
diagnostics = read_diagnostics_product(result.diagnostics)

for source in catalogue.sources:
    print(
        source.source_id,
        source.position.right_ascension_degrees,
        source.position.declination_degrees,
        source.flux.integrated_flux_jy,
    )

for component in catalogue.gaussian_components:
    print(
        component.gaussian_component_id,
        component.source_id,
        component.position.right_ascension_degrees,
        component.position.declination_degrees,
    )

print(diagnostics.provenance.input_sha256)
print(diagnostics.configuration_qualification)
print(diagnostics.deblended_parent_count)
print(diagnostics.deferred_deblend_parent_count)
```

Those provenance identities make it possible to establish which input,
configuration, science profile, and implementation produced the result. Treat
the implementation label as opaque; compare its SHA-256 when exact identity
matters.
The three catalogue populations have deliberately different meanings:

- a support island is one connected detected footprint in the mask;
- a detection component has a stable owned region and may or may not admit a
  Gaussian fit; only successful fits appear in `gaussian_components`; and
- a source is an image-domain association hypothesis. It can contain several
  components and span several disconnected islands; two independent compact
  sources can also share one island.

`source.island_id` and `source.additional_island_ids` enumerate its detected
islands. They do not describe the larger, source-owned measurement aperture.
The published mask contains detections, not every pixel used for photometry.

Gaussian components use bounded joint fits to original background-subtracted
pixels, with the configured beam/free selection and likelihood support.
Their flux is the full Gaussian model integral, including any off-image tail.
Every associated source instead uses a signed, non-overlapping aperture on
finite valid image pixels, including compact singletons. Source positions use
the unexpanded source-owned footprint, not measurement-only flux wings.
A source centroid can lie between peaks or inside a shell's hole. A denoised
position fallback is explicitly flagged; positive-only pixels never silently
replace a failed signed flux estimate. An aperture shape is unavailable,
not a claimed fitted Gaussian or an unresolved source.

`diagnostics.measurement_dispositions` retains every component and associated
source, including unavailable or bounded-work-deferred measurements. Each
entry gives its estimator or failure reason, source membership and whether
a catalogue row was published. Component diagnostics retain the fitted model,
likelihood pixel count, GLS fallback reason, covariance basis and competing
association group IDs. Source diagnostics retain both signed-original and
denoised centroids, their selection rule, position/aperture counts and signed
flux. Source `association_evidence` records each admitted multi-component
merge's reason, scale IDs, component IDs and overridden compact protection.
An unconfirmed hierarchy remainder is not positive source evidence: its
components remain independent. Fit batches follow interacting measurement
contexts, not associated-source membership; an inseparable over-budget fit
still reports its unavailable disposition. These are attribution records,
not new scientific scores.
A failed fit does not discard its detection
or abort an unrelated valid source. Missing uncertainty remains unavailable,
not zero. The current catalogue JSON, catalogue FITS and public diagnostics
schemas are versions 3, 4 and 8 respectively; stale versions fail clearly.
Precision-limited noise uses stable local arithmetic without an invented RMS
floor. Source-protected regions with no positive RMS remain unavailable for
sigma-based detection. A noiseless image containing emission can therefore
return no catalogue rows with an **unavailable RMS**; this is not evidence
that the image contains no sources. No artificial noise floor is supplied.

The continuum RMS policy is covered by source-retention and spatial-noise
tests, but it is **not survey-qualified**. Use the diagnostic provenance and
an exact package version when comparing or repeating runs.

For a component-level comparison with a PyBDSF Gaussian catalogue, compare
`catalogue.gaussian_components`, not `catalogue.sources`. Plotting one marker
per associated source can otherwise make a correctly detected multi-peak
island look as though components are missing. The two deblend disposition
counts expose how many retained parents were split and how many exceeded the
bounded deblending envelope.

## Choose compact-only output explicitly

For work that deliberately excludes extended-emission association, select the
compact profile:

```python
compact_config = hebog.SourceFinderConfig(
    detection_threshold_sigma=5.0,
    island_threshold_sigma=3.0,
    minimum_island_pixels=7,
    profile="compact",
)
```

The resulting diagnostics contain the limitation
`extended-emission-incomplete`. Compact mode must not be presented as a
general continuum-source catalogue.

## Reproducibility, retries, and cleanup

Hebog writes into a private sibling directory, validates all four products,
and renames the complete bundle into place only after success. If analysis or
publication fails, the requested output directory remains absent and the same
request can be retried.

An existing output directory is never overwritten, even when its files appear
to match. Inspect or archive it, then choose a new directory or remove it
yourself before retrying. Hebog does not delete caller-owned products.

Malformed or unreadable FITS inputs raise
`hebog.InvalidSourceFinderInputError`. Unsupported physical metadata and
images outside the bounded preview envelope use distinct public exception
types, so workflow code does not need to parse error strings.

Callers that already own a Dask client may pass `DaskExecutor(client)` instead
of `SerialExecutor()`. Hebog never creates a cluster or inspects ambient
scheduler state. Workers open the input image and write intermediate planes
beside the output directory, so on a multi-node cluster use absolute paths on
storage that every worker can read and write. Serial and existing-Dask execution are required to publish
byte-identical scientific products.

## Current limits

The 1,024-pixel cap is deliberate: measurement currently materializes one
complete image plane after tiled detection. `hebog.find_sources()` does not
perform primary-beam branch composition, filter a sky model, or emit
Rapthor/LSMTool compatibility products; an integrating pipeline must own those
steps.
