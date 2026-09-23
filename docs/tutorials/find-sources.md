# Find sources in a FITS image

In this tutorial you run Hebog on one radio-continuum image and read the
catalogue it produces. It takes a few minutes and needs only
[an installed Hebog](index.md) and a FITS image.

No image to hand? From a [source checkout](../how-to/index.md#set-up-a-source-checkout),
`uv run marimo edit notebooks/source_finder_demo.py` generates a small
synthetic field and runs the same steps.

## Prepare the input

Hebog accepts one two-dimensional FITS image. Extra axes, such as frequency
and Stokes, are fine if each has length one. The image needs:

- pixel values in `Jy/beam` (`BUNIT`);
- an ICRS or FK5 J2000 celestial WCS;
- a restoring beam: `BMAJ`, `BMIN` and `BPA`;
- a reference frequency: `RESTFRQ`, `RESTFREQ` or a frequency axis; and
- at most 3,000 pixels on each side. Cut out a region of a larger image, for
  example with `astropy.nddata.Cutout2D`.

NaN pixels are allowed and ignored. If anything is missing, Hebog stops with
an error that names the problem before writing any output.

### Supply missing header values

Some published images omit a keyword. LOFAR-HD mosaics carry no reference
frequency, and the SKA Science Data Challenge 1 images have no `BPA`. Supply
only what is missing:

```python
supplied = hebog.SuppliedImageMetadata(reference_frequency_hz=144e6)
```

and pass `supplied_metadata=supplied` to the request below. The accepted
fields are `reference_frequency_hz`, `beam_major_fwhm_degrees`,
`beam_minor_fwhm_degrees` and `beam_position_angle_degrees`. Hebog never
overrides a value the header already has; supplying one is an error. Supplied
values are recorded in the diagnostics.

Images written by WSClean declare `EQUINOX = 2000` without `RADESYS`, which
means FK5 J2000. Hebog accepts them and reports all positions in ICRS.

## Run the finder

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
print(f"wall time: {result.wall_seconds:.1f} s")
```

The three settings mean: an island must contain emission above 5σ, it grows
outwards to 3σ, and it must cover at least seven pixels.
[Choose thresholds and a profile](../how-to/configure-a-run.md) explains the
options.

The output directory must not exist yet. Hebog never overwrites results, and
the directory appears only when all products are complete.

## Look at the products

`hebog-products/` now contains four files:

| File | Contents |
| --- | --- |
| `catalogue.fits` | Three tables: `SOURCES`, `GAUSSIAN_COMPONENTS` and `ISLANDS` |
| `rms.fits` | The local noise map in `Jy/beam`, aligned with the input |
| `source-mask.fits` | 1 where a detection was kept, 0 elsewhere, aligned with the input |
| `diagnostics.json` | Provenance, counts, and the fate of every detection, including those without a catalogue row |

You can open the FITS files in any viewer, such as DS9, CARTA or TOPCAT.
In Python, use Hebog's readers, which check that each file is intact and of a
supported version:

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
    print(component.gaussian_component_id, component.source_id)

print(diagnostics.configuration_qualification)
```

## Understand what you are looking at

Hebog publishes three related populations:

- an **island** is a connected region of the mask;
- a **Gaussian component** is one successfully fitted Gaussian; and
- a **source** groups one or more components that Hebog considers a single
  object.

Two points often surprise new users:

1. **Source flux is not a sum of Gaussians.** It is the sum of
   background-subtracted pixels in an aperture owned by that source. Gaussian
   components carry their own model fluxes.
2. **Some sources have no Gaussian.** If a fit fails Hebog's quality checks,
   the source can still be published with its aperture measurement. The
   diagnostics say why.

So when you compare with a PyBDSF Gaussian list or an Aegean component list,
use `catalogue.gaussian_components`, not `catalogue.sources`.

`diagnostics.configuration_qualification` reads `development-unqualified` for
the settings above and `custom-unqualified` for any others. Both mean the same
thing: Hebog has not yet been qualified for survey use.

## If the catalogue is empty

An empty catalogue with `result.rms.scientific_status == "unavailable"` means
Hebog found no usable noise estimate, which usually means a noiseless
simulated image. It does **not** mean the sky is empty. Add realistic noise
and run again.

## Next steps

- [Choose thresholds and a profile](../how-to/configure-a-run.md), including
  running on a Dask cluster.
- [How Hebog finds sources](../explanation/how-hebog-works.md).
- [Output reference](../reference/public-products.md) for every column, unit
  and quality flag.
- [Capability and status](../reference/release-status.md) for current limits.
