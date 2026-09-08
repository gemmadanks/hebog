# Find radio-continuum sources in a FITS image

This tutorial runs Hebog as a standalone scientific library. It uses no
Rapthor, Prefect, LSMTool, or private Dask cluster.

The interface is currently a bounded Phase 5 scientific preview. The code is
implemented, but the current source-catalogue repairs are development science.
Earlier PyBDSF parity results do not qualify this changed implementation. It
requires joint development checks, candidate-bound cumulative evidence, fresh
held-out qualification and independent acceptance.

## Prepare the input

Use one two-dimensional FITS image, or a FITS image with only singleton axes
before its final two spatial axes. The image must have:

- pixel values in `Jy/beam`;
- an ICRS celestial WCS;
- finite positive `BMAJ` and `BMIN` restoring-beam axes (`BPA` defaults to zero);
- a positive reference frequency in `RESTFRQ`, `RESTFREQ`, or a frequency WCS
  axis; and
- no more than 1,024 pixels along either spatial axis.

NaN pixels are allowed and are excluded from the analysis. Missing or invalid
physical metadata fails clearly before any output bundle is published.

## Run the development continuum profile

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

`continuum` is the default profile. The values 5 sigma, 3 sigma, and seven
pixels retain the Phase 5 reference thresholds. The repaired implementation
reports `configuration_qualification="development-unqualified"`: matching
historical thresholds does not transfer qualification to changed science.

Callers may select other valid thresholds and island-size limits. Hebog uses
those values throughout background masking, direct and multiscale detection,
island growth, and final size filtering. Custom runs report
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

The returned `SourceFinderResult` contains closed paths, byte counts, SHA-256
identities, scientific status, and schema versions for four files:

| Product | Meaning |
| --- | --- |
| `catalogue.fits` | Source-level catalogue plus its Gaussian components and parent islands. |
| `rms.fits` | Candidate-owned local RMS estimate in `Jy/beam`; an empty image may report this as scientifically unavailable. |
| `source-mask.fits` | Binary source-support mask aligned with the input image. |
| `diagnostics.json` | Counts, configuration qualification, profile limitations, input/configuration identities, and the exact scientific-composition identity. |

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
print(diagnostics.provenance.scientific_composition_sha256)
print(diagnostics.configuration_qualification)
print(diagnostics.deblended_parent_count)
print(diagnostics.deferred_deblend_parent_count)
```

Those provenance identities make it possible to establish which input,
configuration, reviewed profile, and implementation produced the result.
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

Compact positions, fluxes and shapes use bounded joint Gaussian fits to the
original background-subtracted pixels, including signed background context.
Irregular extended flux uses a signed, non-overlapping source-owned aperture.
Its centroid can lie between peaks or inside a shell's hole. A denoised
position fallback is explicitly flagged; positive-only pixels never silently
replace a failed signed flux estimate. An aperture shape is unavailable,
not a claimed fitted Gaussian or an unresolved source.

`diagnostics.measurement_dispositions` retains every component and associated
source, including unavailable or bounded-work-deferred measurements. Each
entry gives its estimator or failure reason, source membership and whether
a catalogue row was published. A failed fit does not discard its detection
or abort an unrelated valid source. Missing uncertainty remains unavailable,
not zero. The current catalogue JSON, catalogue FITS and public diagnostics
schemas are versions 3, 4 and 6 respectively; stale versions fail clearly.

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
scheduler state. Serial and existing-Dask execution are required to publish
byte-identical scientific products.

## Current limits

The 1,024-pixel cap is deliberate: the evaluated terminal composition still
materializes one complete preview plane after its bounded detection stage.
Larger out-of-core and distributed images remain Phase 7 work and are rejected
rather than extrapolated. Rapthor-specific dual-image composition, sky-model
filtering, compatibility filenames, and the minimum end-to-end runtime gate
belong to Phase 6.
