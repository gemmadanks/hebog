# Find radio-continuum sources in a FITS image

This tutorial runs Hebog as a standalone scientific library. It uses no
Rapthor, Prefect, LSMTool, or private Dask cluster.

The interface is currently a bounded Phase 5 scientific preview. The code is
implemented, and its underlying regression evidence matches or outperforms
both governed PyBDSF references, but the exact public release candidate still
requires fresh held-out qualification and independent acceptance.

## Prepare the input

Use one two-dimensional FITS image, or a FITS image with only singleton axes
before its final two spatial axes. The image must have:

- pixel values in `Jy/beam`;
- an ICRS celestial WCS;
- finite positive `BMAJ` and `BMIN` restoring-beam axes plus `BPA`;
- a positive reference frequency in `RESTFRQ`, `RESTFREQ`, or a frequency WCS
  axis; and
- no more than 1,024 pixels along either spatial axis.

NaN pixels are allowed and are excluded from the analysis. Missing or invalid
physical metadata fails clearly before any output bundle is published.

## Run the qualified continuum profile

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

`continuum` is the default profile. In this Phase 5 preview the values
5 sigma, 3 sigma, and seven pixels are the exact qualified configuration;
Hebog rejects other values instead of silently running unevaluated science.

## Interpret the products

The returned `SourceFinderResult` contains closed paths, byte counts, SHA-256
identities, scientific status, and schema versions for four files:

| Product | Meaning |
| --- | --- |
| `catalogue.fits` | Source-level catalogue plus its Gaussian components and parent islands. |
| `rms.fits` | Candidate-owned local RMS estimate in `Jy/beam`; an empty image may report this as scientifically unavailable. |
| `source-mask.fits` | Binary source-support mask aligned with the input image. |
| `diagnostics.json` | Counts, profile limitations, input/configuration identities, and the exact scientific-composition identity. |

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

print(diagnostics.provenance.input_sha256)
print(diagnostics.provenance.scientific_composition_sha256)
```

Those provenance identities make it possible to establish which input,
configuration, reviewed profile, and implementation produced the result.

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
`hebog.InvalidSourceFinderInputError`. Unsupported scientific settings and
images outside the qualified envelope use distinct public exception types, so
workflow code does not need to parse error strings.

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
