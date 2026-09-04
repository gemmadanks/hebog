import marimo

__generated_with = "0.23.16"
app = marimo.App(width="full")


@app.cell(hide_code=True)
def _():
    import marimo as mo

    return (mo,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Hebog public source-finder demonstration

    This notebook runs Hebog through its supported, scheduler-independent
    public interface. It writes a deterministic synthetic radio-continuum
    image to FITS, creates `SourceFinderRequest` and `SourceFinderConfig`
    records, and executes the complete source finder with
    `hebog.find_sources()`.

    The result is one atomic product bundle containing a source catalogue, a
    local-RMS image, a source mask, and provenance-rich diagnostics. The
    notebook reads those published products rather than composing Hebog's
    internal scientific stages itself.
    """)
    return


@app.cell
def _():
    import pathlib
    import tempfile

    import astropy.wcs as astropy_wcs
    import matplotlib.pyplot as plt
    import numpy as np
    from astropy.io import fits

    import hebog
    import hebog.executors as hebog_executors
    from hebog.io import (
        read_catalogue_fits_product,
        read_diagnostics_product,
    )

    return (
        astropy_wcs,
        fits,
        hebog,
        hebog_executors,
        np,
        pathlib,
        plt,
        read_catalogue_fits_product,
        read_diagnostics_product,
        tempfile,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 1. Prepare a supported FITS image

    The scene is a noisy four-lobe shell. Each lobe is compact enough to
    produce a Gaussian component, while the continuum profile can associate
    the connected emission into one astronomical source.

    A public input carries the physical metadata needed to interpret its
    pixels: `Jy/beam` units, an ICRS celestial WCS, a restoring beam, and a
    reference frequency. The temporary workspace keeps this demonstration
    self-contained and gives each notebook session a fresh output directory.
    """)
    return


@app.cell
def _(astropy_wcs, fits, np, pathlib, tempfile):
    demonstration_workspace = tempfile.TemporaryDirectory(
        prefix="hebog-public-demo-"
    )
    demonstration_directory = pathlib.Path(demonstration_workspace.name)
    input_path = demonstration_directory / "continuum-image.fits"
    output_directory = demonstration_directory / "hebog-products"

    image_shape_yx = (81, 81)
    y_pixels, x_pixels = np.mgrid[: image_shape_yx[0], : image_shape_yx[1]]
    x_offset = x_pixels - 40.0
    y_offset = y_pixels - 40.0
    radius = np.hypot(x_offset, y_offset)
    angle = np.arctan2(y_offset, x_offset)

    shell = np.exp(-((radius - 10.0) ** 2) / 2.0)
    shell *= 1.0 + 8.0 * np.clip(np.cos(4.0 * angle), 0.0, None)
    random_noise = np.random.default_rng(42).normal(
        0.0,
        0.5,
        image_shape_yx,
    )
    input_image = np.asarray(
        0.001 * (shell + random_noise),
        dtype=np.float64,
    )

    input_header = fits.Header()
    input_header["BUNIT"] = "Jy/beam"
    input_header["BMAJ"] = 4.0 / 3600.0
    input_header["BMIN"] = 4.0 / 3600.0
    input_header["BPA"] = 0.0
    input_header["RADESYS"] = "ICRS"
    input_header["CTYPE1"] = "RA---TAN"
    input_header["CTYPE2"] = "DEC--TAN"
    input_header["CRPIX1"] = image_shape_yx[1] / 2 + 1
    input_header["CRPIX2"] = image_shape_yx[0] / 2 + 1
    input_header["CRVAL1"] = 180.0
    input_header["CRVAL2"] = -30.0
    input_header["CDELT1"] = -1.0 / 3600.0
    input_header["CDELT2"] = 1.0 / 3600.0
    input_header["CUNIT1"] = "deg"
    input_header["CUNIT2"] = "deg"
    input_header["RESTFRQ"] = 150_000_000.0

    fits.PrimaryHDU(data=input_image, header=input_header).writeto(input_path)
    input_wcs = astropy_wcs.WCS(input_header).celestial
    truth_lobes_xy = (
        (30.0, 40.0),
        (40.0, 30.0),
        (40.0, 50.0),
        (50.0, 40.0),
    )
    return input_image, input_path, input_wcs, output_directory, truth_lobes_xy


@app.cell
def _(input_image, mo, np, plt, truth_lobes_xy):
    _minimum, _maximum = np.percentile(input_image, (1.0, 99.8))
    _input_figure, _input_axis = plt.subplots(figsize=(7.0, 5.5))
    _input_artist = _input_axis.imshow(
        1_000.0 * input_image,
        origin="lower",
        cmap="gray",
        vmin=1_000.0 * _minimum,
        vmax=1_000.0 * _maximum,
    )
    for _x_pixel, _y_pixel in truth_lobes_xy:
        _input_axis.plot(
            _x_pixel,
            _y_pixel,
            marker="+",
            color="tab:cyan",
            markersize=9,
            markeredgewidth=1.5,
        )
    _input_axis.set(
        title="Deterministic four-lobe continuum scene",
        xlabel="x pixel",
        ylabel="y pixel",
    )
    _input_figure.colorbar(
        _input_artist,
        ax=_input_axis,
        label="Brightness (mJy/beam)",
        shrink=0.82,
    )
    _input_figure.tight_layout()

    mo.vstack(
        [
            mo.md(
                f"**Shape:** `{input_image.shape[0]} x "
                f"{input_image.shape[1]}` pixels  "
                "**Noise RMS:** `0.5 mJy/beam`  "
                "**Restoring beam:** `4 x 4 arcsec`"
            ),
            _input_figure,
            mo.md(
                "Cyan markers show the analytic lobe centres. They are "
                "context for the visualization only and are not supplied "
                "to the source finder."
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 2. Call the public interface

    These are the complete caller-owned inputs. The configuration selects the
    Phase 5 reference continuum profile with its explicit 5-sigma detection
    threshold, 3-sigma island threshold, and seven-pixel minimum island size.
    Other valid values also execute and are marked `custom-unqualified` in the
    diagnostics. The serial executor is the deterministic reference
    implementation; a workflow that already owns a Dask client can pass
    `DaskExecutor(client)` at the same boundary.
    """)
    return


@app.cell
def _(
    fits,
    hebog,
    hebog_executors,
    input_path,
    np,
    output_directory,
    read_catalogue_fits_product,
    read_diagnostics_product,
):
    source_finder_request = hebog.SourceFinderRequest(
        image_path=input_path,
        output_directory=output_directory,
        run_id="public-source-finder-demo",
    )
    source_finder_config = hebog.SourceFinderConfig(
        detection_threshold_sigma=4.0,
        island_threshold_sigma=3.0,
        minimum_island_pixels=7,
        profile="continuum",
    )

    source_finder_result = hebog.find_sources(
        source_finder_request,
        source_finder_config,
        hebog_executors.SerialExecutor(),
    )

    source_catalogue = read_catalogue_fits_product(
        source_finder_result.catalogue
    )
    source_finder_diagnostics = read_diagnostics_product(
        source_finder_result.diagnostics
    )
    rms_image = np.asarray(
        fits.getdata(source_finder_result.rms_path),
        dtype=np.float64,
    )
    source_mask = np.asarray(
        fits.getdata(source_finder_result.mask_path),
        dtype=np.bool_,
    )
    return (
        rms_image,
        source_catalogue,
        source_finder_diagnostics,
        source_finder_result,
        source_mask,
    )


@app.cell
def _(mo, source_finder_diagnostics, source_finder_result):
    _statistics = mo.hstack(
        [
            mo.stat(
                label="Astronomical sources",
                value=str(source_finder_result.source_count),
            ),
            mo.stat(
                label="Gaussian components",
                value=str(source_finder_result.gaussian_component_count),
            ),
            mo.stat(
                label="Detection islands",
                value=str(source_finder_result.island_count),
            ),
            mo.stat(
                label="Wall time",
                value=f"{source_finder_result.wall_seconds:.3f} s",
            ),
        ],
        widths="equal",
    )

    _products = (
        source_finder_result.catalogue,
        source_finder_result.rms,
        source_finder_result.mask,
        source_finder_result.diagnostics,
    )
    _product_rows = "\n".join(
        f"| `{_product.product_role}` | `{_product.path.name}` | "
        f"{_product.byte_count:,} | `{_product.content_sha256[:12]}...` | "
        f"{_product.scientific_status} |"
        for _product in _products
    )
    _product_table = mo.md(
        "| Product role | File | Bytes | SHA-256 prefix | Status |\n"
        "| --- | --- | ---: | --- | --- |\n"
        f"{_product_rows}"
    )
    _profile_note = mo.md(
        f"**Profile:** `{source_finder_diagnostics.profile}`  "
        "**Configuration:** "
        f"`{source_finder_diagnostics.configuration_qualification}`  "
        f"**Result schema:** `{source_finder_result.schema_version}`  "
        "**Diagnostic schema:** "
        f"`{source_finder_diagnostics.schema_version}`"
    )
    mo.vstack([_statistics, _profile_note, _product_table])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 3. Inspect the published scientific products

    `SourceFinderResult` carries closed product identities and paths. The
    catalogue and diagnostics are read with Hebog's validating readers. The
    image panels below use the published RMS and source-mask FITS products;
    no private stage result is retained or inspected.
    """)
    return


@app.cell
def _(
    input_image,
    input_wcs,
    mo,
    np,
    plt,
    rms_image,
    source_catalogue,
    source_mask,
):
    _source_world = np.asarray(
        [
            (
                _source.position.right_ascension_degrees,
                _source.position.declination_degrees,
            )
            for _source in source_catalogue.sources
        ],
        dtype=np.float64,
    )
    _component_world = np.asarray(
        [
            (
                _component.position.right_ascension_degrees,
                _component.position.declination_degrees,
            )
            for _component in source_catalogue.gaussian_components
        ],
        dtype=np.float64,
    )
    _source_pixels = (
        input_wcs.all_world2pix(_source_world, 0)
        if _source_world.size
        else np.empty((0, 2), dtype=np.float64)
    )
    _component_pixels = (
        input_wcs.all_world2pix(_component_world, 0)
        if _component_world.size
        else np.empty((0, 2), dtype=np.float64)
    )

    _minimum, _maximum = np.percentile(input_image, (1.0, 99.8))
    _product_figure, _product_axes = plt.subplots(
        2,
        2,
        figsize=(11.5, 9.0),
        constrained_layout=True,
    )
    _input_artist = _product_axes[0, 0].imshow(
        1_000.0 * input_image,
        origin="lower",
        cmap="gray",
        vmin=1_000.0 * _minimum,
        vmax=1_000.0 * _maximum,
    )
    if np.any(source_mask):
        _product_axes[0, 0].contour(
            source_mask,
            levels=[0.5],
            colors="tab:orange",
            linewidths=1.1,
        )
    _product_axes[0, 0].set_title("Input with published mask boundary")
    _product_figure.colorbar(
        _input_artist,
        ax=_product_axes[0, 0],
        label="mJy/beam",
        shrink=0.8,
    )

    _rms_artist = _product_axes[0, 1].imshow(
        1_000.0 * rms_image,
        origin="lower",
        cmap="cividis",
    )
    _product_axes[0, 1].set_title("Published local RMS")
    _product_figure.colorbar(
        _rms_artist,
        ax=_product_axes[0, 1],
        label="mJy/beam",
        shrink=0.8,
    )

    _mask_artist = _product_axes[1, 0].imshow(
        source_mask,
        origin="lower",
        cmap="binary",
        vmin=0,
        vmax=1,
    )
    _product_axes[1, 0].set_title("Published source-support mask")
    _product_figure.colorbar(
        _mask_artist,
        ax=_product_axes[1, 0],
        ticks=[0, 1],
        shrink=0.8,
    )

    _product_axes[1, 1].imshow(
        1_000.0 * input_image,
        origin="lower",
        cmap="gray",
        vmin=1_000.0 * _minimum,
        vmax=1_000.0 * _maximum,
    )
    if _component_pixels.size:
        _product_axes[1, 1].scatter(
            _component_pixels[:, 0],
            _component_pixels[:, 1],
            s=70,
            facecolors="none",
            edgecolors="tab:cyan",
            linewidths=1.4,
            label="Gaussian component",
        )
    if _source_pixels.size:
        _product_axes[1, 1].scatter(
            _source_pixels[:, 0],
            _source_pixels[:, 1],
            s=130,
            marker="*",
            color="tab:orange",
            edgecolors="black",
            linewidths=0.5,
            label="Associated source",
        )
    _product_axes[1, 1].set_title("Validated catalogue positions")
    if _source_pixels.size or _component_pixels.size:
        _product_axes[1, 1].legend(loc="upper right")

    for _axis in _product_axes.flat:
        _axis.set(xlabel="x pixel", ylabel="y pixel")

    mo.vstack([_product_figure])
    return


@app.cell
def _(mo, source_catalogue):
    _component_counts = {
        _source.source_id: sum(
            _component.source_id == _source.source_id
            for _component in source_catalogue.gaussian_components
        )
        for _source in source_catalogue.sources
    }
    _source_rows = "\n".join(
        f"| `{_source.source_id}` | `{_source.island_id}` | "
        f"{_component_counts[_source.source_id]} | "
        f"{_source.position.right_ascension_degrees:.6f} | "
        f"{_source.position.declination_degrees:.6f} | "
        f"{1_000.0 * _source.flux.integrated_flux_jy:.3f} |"
        for _source in source_catalogue.sources
    )
    if not _source_rows:
        _source_rows = "| _No accepted sources_ | - | - | - | - | - |"

    _component_rows = "\n".join(
        f"| `{_component.gaussian_component_id}` | "
        f"`{_component.source_id}` | `{_component.island_id}` | "
        f"{1_000.0 * _component.flux.peak_flux_jy_per_beam:.3f} | "
        f"{3_600.0 * _component.fitted_shape.major_fwhm_degrees:.3f} | "
        f"{3_600.0 * _component.fitted_shape.minor_fwhm_degrees:.3f} |"
        for _component in source_catalogue.gaussian_components
    )
    if not _component_rows:
        _component_rows = "| _No fitted components_ | - | - | - | - | - |"

    _source_table = mo.md(
        "### Astronomical sources\n\n"
        "| Source | Island | Components | RA (deg) | Dec (deg) | "
        "Integrated flux (mJy) |\n"
        "| --- | --- | ---: | ---: | ---: | ---: |\n"
        f"{_source_rows}"
    )
    _component_table = mo.md(
        "### Gaussian components\n\n"
        "| Component | Source | Island | Peak (mJy/beam) | "
        "Major FWHM (arcsec) | Minor FWHM (arcsec) |\n"
        "| --- | --- | --- | ---: | ---: | ---: |\n"
        f"{_component_rows}"
    )
    mo.vstack([_source_table, _component_table])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## What this demonstrates

    The notebook crosses the same public boundary available to external
    Python callers: FITS input and small serializable records in, then a
    versioned `SourceFinderResult` with four materialized products out. The
    continuum profile performs compact measurement and extended-emission
    association behind that boundary, so the four fitted lobes can belong to
    one source without notebook code coordinating those stages.

    The current scientific preview accepts images no larger than 1,024 pixels
    on either spatial axis. The values shown above identify the evaluated
    Phase 5 reference; callers can choose other valid thresholds without
    inheriting that evidence. Output directories are caller-owned and must not
    already exist. Hebog publishes a complete bundle atomically and will not
    overwrite an earlier result.
    """).callout(kind="info")
    return


if __name__ == "__main__":
    app.run()
