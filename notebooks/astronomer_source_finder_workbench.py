# ruff: noqa: E501

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
    # Hebog astronomer's source-finding workbench

    Run Hebog on a radio-continuum FITS image through its supported public
    interface, tune the caller-owned detection parameters, and inspect the
    returned catalogue, local-RMS image, diagnostics, and final source mask.

    This workbench always uses the continuum profile. Compact measurement,
    multiscale processing, and source association happen inside Hebog. The
    notebook does not coordinate internal algorithms or stages.

    Public LoTSS inputs are cached under `benchmark-results/notebook-data`.
    Run `uv run python scripts/benchmark/download_notebook_data.py` from the
    repository root to fetch all three small fields before opening the app,
    or download a selected field on demand. These are exploratory inputs;
    individual notebook runs do not need a frozen campaign identity.
    """)
    return


@app.cell
def _():
    import datetime as datetime_module
    import hashlib
    import json
    import pathlib
    import re
    import urllib.parse as urllib_parse
    import urllib.request as urllib_request

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
        datetime_module,
        fits,
        hashlib,
        hebog,
        hebog_executors,
        json,
        np,
        pathlib,
        plt,
        read_catalogue_fits_product,
        read_diagnostics_product,
        re,
        urllib_parse,
        urllib_request,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 1. Select a radio image

    The synthetic fields support reproducible threshold experiments. The
    representative LoTSS field is useful for population-level inspection,
    while M51 stresses diffuse-emission recovery and source association.

    A custom input must contain one logical two-dimensional Stokes-I plane, an
    ICRS celestial WCS, Jy/beam units, restoring-beam metadata, and a reference
    frequency.
    """)
    return


@app.cell
def _(mo):
    image_selector = mo.ui.dropdown(
        options={
            "Synthetic commissioning field (offline)": "synthetic",
            "Synthetic 100-source survey field (offline)": "synthetic-survey",
            "LoTSS DR2: representative ~100-source field (22 arcmin)": (
                "lotss-survey-100"
            ),
            "LoTSS DR2: 3C 295 bright-source field (12 arcmin)": (
                "lotss-3c295"
            ),
            "LoTSS DR2: M51 extended-source field (20 arcmin)": ("lotss-m51"),
            "My FITS image": "custom",
        },
        value="Synthetic commissioning field (offline)",
        label="Image",
    )
    custom_image_path = mo.ui.text(
        value="",
        placeholder="/absolute/path/to/restored-image.fits",
        label="Custom FITS path",
        full_width=True,
    )
    load_image = mo.ui.run_button(label="Load selected image")
    mo.vstack(
        [
            mo.hstack([image_selector, load_image], widths=[3, 1]),
            custom_image_path,
            mo.callout(
                "LoTSS fields use the downloaded notebook-data cache, or "
                "download on demand when absent. Choose My FITS image to "
                "use another image, including a saved campaign input.",
                kind="info",
            ),
        ]
    )
    return custom_image_path, image_selector, load_image


@app.cell(hide_code=True)
def _(fits, np):
    def _header(_shape, *, _beam_arcsec, _frequency_hz, _sky):
        _value = fits.Header()
        _value["BUNIT"] = "Jy/beam"
        _value["BMAJ"] = _beam_arcsec[0] / 3600.0
        _value["BMIN"] = _beam_arcsec[1] / 3600.0
        _value["BPA"] = _beam_arcsec[2]
        _value["RESTFRQ"] = _frequency_hz
        _value["RADESYS"] = "ICRS"
        _value["CTYPE1"] = "RA---SIN"
        _value["CTYPE2"] = "DEC--SIN"
        _value["CUNIT1"] = "deg"
        _value["CUNIT2"] = "deg"
        _value["CRPIX1"] = _shape[1] / 2 + 0.5
        _value["CRPIX2"] = _shape[0] / 2 + 0.5
        _value["CRVAL1"] = _sky[0]
        _value["CRVAL2"] = _sky[1]
        _value["CDELT1"] = -1.5 / 3600.0
        _value["CDELT2"] = 1.5 / 3600.0
        return _value

    def write_commissioning_image(_path):
        _rng = np.random.default_rng(20260827)
        _shape = (512, 512)
        _y, _x = np.indices(_shape, dtype=np.float64)
        _image = _rng.normal(0.0, 1.0e-4, _shape)
        _image += 2.0e-8 * (_x - _shape[1] / 2.0)
        for _x0, _y0, _peak, _sx, _sy in (
            (110.0, 380.0, 8.0e-4, 2.2, 1.8),
            (245.0, 270.0, 1.8e-3, 2.4, 2.0),
            (256.0, 272.0, 1.4e-3, 2.4, 2.0),
            (398.0, 132.0, 1.2e-2, 2.2, 1.8),
            (165.0, 155.0, 8.5e-4, 13.0, 5.0),
        ):
            _image += _peak * np.exp(
                -0.5 * (((_x - _x0) / _sx) ** 2 + ((_y - _y0) / _sy) ** 2)
            )
        _radius = np.hypot(_x - 398.0, _y - 132.0)
        _image += 3.0e-4 * np.cos(_radius / 2.8) * np.exp(-_radius / 42.0)
        _image[28:46, 450:476] = np.nan
        fits.PrimaryHDU(
            data=_image,
            header=_header(
                _shape,
                _beam_arcsec=(6.0, 5.0, 18.0),
                _frequency_hz=150.0e6,
                _sky=(212.835, 52.2028),
            ),
        ).writeto(_path, overwrite=True)

    def write_survey_image(_path):
        _rng = np.random.default_rng(20260828)
        _shape = (1024, 1024)
        _y, _x = np.indices(_shape, dtype=np.float64)
        _noise_rms = 8.0e-5
        _image = _rng.normal(0.0, 1.0, _shape) * (
            _noise_rms * (0.75 + 0.50 * _x / (_shape[1] - 1))
        )
        _image += 1.5e-5 * np.sin(_y / 180.0)
        _centres = [
            [
                55.0 + 101.0 * _column + _rng.uniform(-18.0, 18.0),
                55.0 + 101.0 * _row + _rng.uniform(-18.0, 18.0),
            ]
            for _row in range(10)
            for _column in range(10)
        ]
        for _pair_index in range(0, 10, 2):
            _centres[_pair_index + 1] = [
                _centres[_pair_index][0] + _rng.uniform(7.0, 11.0),
                _centres[_pair_index][1] + _rng.uniform(-2.0, 2.0),
            ]
        _peak_snrs = np.geomspace(4.0, 80.0, 100)
        _rng.shuffle(_peak_snrs)
        _compact_source_count = 94
        for _index, ((_x0, _y0), _peak_snr) in enumerate(
            zip(_centres, _peak_snrs, strict=True)
        ):
            _local_rms = _noise_rms * (0.75 + 0.50 * _x0 / (_shape[1] - 1))
            _scale = (
                _rng.uniform(1.8, 4.0)
                if _index >= _compact_source_count
                else 1.0
            )
            _sx = _rng.uniform(1.7, 2.2) * _scale
            _sy = _rng.uniform(1.3, 1.8) * _scale
            _image += float(_peak_snr * _local_rms) * np.exp(
                -0.5 * (((_x - _x0) / _sx) ** 2 + ((_y - _y0) / _sy) ** 2)
            )
        _image[470:502, 805:850] = np.nan
        fits.PrimaryHDU(
            data=_image,
            header=_header(
                _shape,
                _beam_arcsec=(7.0, 5.0, 27.0),
                _frequency_hz=144.0e6,
                _sky=(180.0, 45.0),
            ),
        ).writeto(_path, overwrite=True)

    return write_commissioning_image, write_survey_image


@app.cell(hide_code=True)
def _(
    astropy_wcs,
    custom_image_path,
    fits,
    hashlib,
    image_selector,
    load_image,
    mo,
    np,
    pathlib,
    urllib_parse,
    urllib_request,
    write_commissioning_image,
    write_survey_image,
):
    mo.stop(
        not load_image.value,
        mo.md("Select an image and press **Load selected image**."),
    )
    _project_root = pathlib.Path(__file__).resolve().parents[1]
    _cache = _project_root / "benchmark-results" / "notebook-data"
    _cache.mkdir(parents=True, exist_ok=True)

    _download_examples = {
        "lotss-survey-100": (
            "LoTSS DR2 representative survey field",
            "12:00:00 +45:00:00",
            22,
            "lotss-dr2-survey-field-22arcmin.fits",
        ),
        "lotss-m51": (
            "LoTSS DR2 M51 extended-source field",
            "M51",
            20,
            "lotss-dr2-m51-20arcmin.fits",
        ),
        "lotss-3c295": (
            "LoTSS DR2 3C 295 field",
            "3C 295",
            12,
            "lotss-dr2-3c295-12arcmin.fits",
        ),
    }
    if image_selector.value == "synthetic":
        selected_input_path = _cache / "synthetic-commissioning-field.fits"
        write_commissioning_image(selected_input_path)
        selected_input_label = "Synthetic commissioning field"
        selected_input_provenance = (
            "Deterministic notebook image; seed 20260827."
        )
    elif image_selector.value == "synthetic-survey":
        selected_input_path = _cache / "synthetic-100-source-survey.fits"
        write_survey_image(selected_input_path)
        selected_input_label = "Synthetic 100-source survey field"
        selected_input_provenance = (
            "Deterministic image with 100 injected sources; seed 20260828."
        )
    elif image_selector.value == "custom":
        selected_input_path = pathlib.Path(
            custom_image_path.value
        ).expanduser()
        mo.stop(
            not custom_image_path.value.strip(),
            mo.callout("Enter a FITS path before loading.", kind="warn"),
        )
        mo.stop(
            not selected_input_path.is_file(),
            mo.callout(
                f"No file exists at {selected_input_path}.",
                kind="danger",
            ),
        )
        selected_input_label = selected_input_path.name
        selected_input_provenance = "User-supplied FITS image."
    else:
        _label, _position, _size, _filename = _download_examples[
            image_selector.value
        ]
        selected_input_path = _cache / _filename
        if not selected_input_path.exists():
            _query = urllib_parse.urlencode({"pos": _position, "size": _size})
            _url = f"https://lofar-surveys.org/dr2-cutout.fits?{_query}"
            try:
                with urllib_request.urlopen(_url, timeout=120) as _response:
                    selected_input_path.write_bytes(_response.read())
            except Exception as _error:
                selected_input_path.unlink(missing_ok=True)
                mo.stop(
                    True,
                    mo.callout(
                        f"The LoTSS cutout could not be downloaded: {_error}",
                        kind="danger",
                    ),
                )
        selected_input_label = _label
        selected_input_provenance = (
            f"LoTSS DR2 cutout; position {_position}, size {_size} arcmin."
        )

    selected_input_sha256 = hashlib.sha256(
        selected_input_path.read_bytes()
    ).hexdigest()
    try:
        with fits.open(selected_input_path, memmap=False) as _hdul:
            selected_input_image = np.squeeze(
                np.asarray(_hdul[0].data, dtype=np.float64)
            )
            selected_input_header = _hdul[0].header.copy()
        _image_dimensions = 2
        if selected_input_image.ndim != _image_dimensions:
            raise ValueError("the FITS input does not reduce to one 2D plane")
        selected_input_wcs = astropy_wcs.WCS(
            selected_input_header,
            relax=True,
        ).celestial
    except Exception as _error:
        mo.stop(
            True,
            mo.callout(
                f"The selected FITS image could not be read: {_error}",
                kind="danger",
            ),
        )
    return (
        selected_input_header,
        selected_input_image,
        selected_input_label,
        selected_input_path,
        selected_input_provenance,
        selected_input_sha256,
        selected_input_wcs,
    )


@app.cell(hide_code=True)
def _(
    mo,
    np,
    plt,
    selected_input_header,
    selected_input_image,
    selected_input_label,
    selected_input_path,
    selected_input_provenance,
    selected_input_sha256,
):
    _finite = selected_input_image[np.isfinite(selected_input_image)]
    _lower, _upper = (
        np.percentile(_finite, (1.0, 99.7)) if _finite.size else (0.0, 1.0)
    )
    _figure, _axis = plt.subplots(figsize=(8.0, 6.2))
    _artist = _axis.imshow(
        selected_input_image,
        origin="lower",
        cmap="gray",
        vmin=_lower,
        vmax=_upper,
    )
    _axis.set(
        title=selected_input_label,
        xlabel="x pixel",
        ylabel="y pixel",
    )
    _figure.colorbar(
        _artist,
        ax=_axis,
        label=str(selected_input_header.get("BUNIT", "brightness")),
        shrink=0.82,
    )
    _figure.tight_layout()
    mo.vstack(
        [
            mo.md(
                f"**Path:** {selected_input_path}  \n"
                f"**Shape:** {selected_input_image.shape[0]} x "
                f"{selected_input_image.shape[1]} pixels  \n"
                f"**SHA-256:** {selected_input_sha256}  \n"
                f"**Provenance:** {selected_input_provenance}"
            ),
            _figure,
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 2. Configure the continuum run

    - **Detection threshold:** significance required to seed a source.
      Increasing it generally improves reliability but reduces completeness.
    - **Island threshold:** lower significance used to grow emission around a
      seed. Lower values include more wings but can bridge neighbours.
    - **Minimum island pixels:** rejects tiny noise structures. Compare this
      with the restoring-beam area before increasing it.

    The continuum profile owns the reviewed background, RMS, compact,
    multiscale, and association policies behind the public boundary. Custom
    thresholds are allowed, but diagnostics mark them as custom-unqualified.
    """)
    return


@app.cell
def _(mo, pathlib):
    detection_threshold = mo.ui.slider(
        start=3.5,
        stop=10.0,
        step=0.25,
        value=5.0,
        label="Detection / seed threshold (sigma)",
        show_value=True,
    )
    island_threshold = mo.ui.slider(
        start=2.0,
        stop=6.0,
        step=0.25,
        value=3.0,
        label="Island / flood threshold (sigma)",
        show_value=True,
    )
    minimum_island_pixels = mo.ui.dropdown(
        options={str(_value): _value for _value in (3, 5, 7, 10, 15, 25)},
        value="7",
        label="Minimum island pixels",
    )
    run_label = mo.ui.text(value="experiment", label="Run label")
    output_root = mo.ui.text(
        value=str(
            pathlib.Path(__file__).resolve().parents[1]
            / "benchmark-results"
            / "notebook-runs"
        ),
        label="Output root",
        full_width=True,
    )
    run_hebog = mo.ui.run_button(label="Run Hebog continuum finder")
    mo.vstack(
        [
            mo.hstack(
                [
                    detection_threshold,
                    island_threshold,
                    minimum_island_pixels,
                ],
                widths="equal",
            ),
            mo.hstack([run_label, run_hebog], widths=[3, 1]),
            output_root,
        ]
    )
    return (
        detection_threshold,
        island_threshold,
        minimum_island_pixels,
        output_root,
        run_hebog,
        run_label,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### The complete source-finding interface

        config = hebog.SourceFinderConfig(5.0, 3.0, 7, profile="continuum")
        request = hebog.SourceFinderRequest(image_path, output_directory, run_id)
        result = hebog.find_sources(request, config, SerialExecutor())

    Everything else in this notebook loads inputs, presents controls, or
    visualizes the four published products.
    """)
    return


@app.cell(hide_code=True)
def _(
    datetime_module,
    detection_threshold,
    fits,
    hebog,
    hebog_executors,
    island_threshold,
    minimum_island_pixels,
    mo,
    np,
    output_root,
    pathlib,
    read_catalogue_fits_product,
    read_diagnostics_product,
    re,
    run_hebog,
    run_label,
    selected_input_path,
):
    mo.stop(
        not run_hebog.value,
        mo.md(
            "Set the parameters, then press **Run Hebog continuum finder**."
        ),
    )
    mo.stop(
        float(island_threshold.value) >= float(detection_threshold.value),
        mo.callout(
            "The island threshold must be below the detection threshold.",
            kind="danger",
        ),
    )
    _domain_label = re.sub(
        r"[^a-z0-9]+",
        "-",
        run_label.value.strip().lower(),
    ).strip("-")
    if not _domain_label or not _domain_label[0].isalpha():
        _domain_label = f"run-{_domain_label or 'experiment'}"
    _timestamp = datetime_module.datetime.now(datetime_module.UTC).strftime(
        "%Y%m%d-%H%M%S%f"
    )
    _run_id = f"{_domain_label}-{_timestamp}"
    _output_parent = pathlib.Path(output_root.value).expanduser().resolve()
    _output_parent.mkdir(parents=True, exist_ok=True)

    source_finder_config = hebog.SourceFinderConfig(
        detection_threshold_sigma=float(detection_threshold.value),
        island_threshold_sigma=float(island_threshold.value),
        minimum_island_pixels=int(minimum_island_pixels.value),
        profile="continuum",
    )
    source_finder_request = hebog.SourceFinderRequest(
        image_path=selected_input_path,
        output_directory=_output_parent / _run_id,
        run_id=_run_id,
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
    source_rms = np.asarray(
        fits.getdata(source_finder_result.rms_path),
        dtype=np.float64,
    )
    final_source_mask = np.asarray(
        fits.getdata(source_finder_result.mask_path),
        dtype=np.bool_,
    )
    return (
        final_source_mask,
        source_catalogue,
        source_finder_config,
        source_finder_diagnostics,
        source_finder_request,
        source_finder_result,
        source_rms,
    )


@app.cell(hide_code=True)
def _(
    final_source_mask,
    mo,
    source_finder_diagnostics,
    source_finder_result,
):
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
                label="Final mask pixels",
                value=f"{final_source_mask.sum():,}",
            ),
            mo.stat(
                label="Wall time",
                value=f"{source_finder_result.wall_seconds:.2f} s",
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
        f"| {_product.product_role} | {_product.path.name} | "
        f"{_product.byte_count:,} | {_product.content_sha256[:12]}... | "
        f"{_product.scientific_status} |"
        for _product in _products
    )
    mo.vstack(
        [
            mo.md("## 3. Public continuum result"),
            _statistics,
            mo.md(
                f"**Profile:** {source_finder_diagnostics.profile}  "
                "**Configuration status:** "
                f"{source_finder_diagnostics.configuration_qualification}  "
                f"**Output:** {source_finder_result.mask.path.parent}"
            ),
            mo.md(
                "| Product role | File | Bytes | SHA-256 prefix | Status |\n"
                "| --- | --- | ---: | --- | --- |\n"
                f"{_product_rows}"
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(
    final_source_mask,
    mo,
    np,
    plt,
    selected_input_image,
    selected_input_label,
    selected_input_wcs,
    source_catalogue,
    source_rms,
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
        selected_input_wcs.all_world2pix(_source_world, 0)
        if _source_world.size
        else np.empty((0, 2), dtype=np.float64)
    )
    _component_pixels = (
        selected_input_wcs.all_world2pix(_component_world, 0)
        if _component_world.size
        else np.empty((0, 2), dtype=np.float64)
    )
    _finite = selected_input_image[np.isfinite(selected_input_image)]
    _lower, _upper = (
        np.percentile(_finite, (1.0, 99.7)) if _finite.size else (0.0, 1.0)
    )
    _figure, _axes = plt.subplots(
        2,
        2,
        figsize=(13.0, 10.5),
        constrained_layout=True,
        sharex=True,
        sharey=True,
    )
    _input_artist = _axes[0, 0].imshow(
        selected_input_image,
        origin="lower",
        cmap="gray",
        vmin=_lower,
        vmax=_upper,
    )
    if np.any(final_source_mask):
        _axes[0, 0].contour(
            final_source_mask,
            levels=[0.5],
            colors="tab:orange",
            linewidths=0.9,
        )
    _axes[0, 0].set_title("Input with returned final-mask boundary")
    _figure.colorbar(_input_artist, ax=_axes[0, 0], shrink=0.8)

    _rms_artist = _axes[0, 1].imshow(
        source_rms,
        origin="lower",
        cmap="cividis",
    )
    _axes[0, 1].set_title("Returned local RMS")
    _figure.colorbar(_rms_artist, ax=_axes[0, 1], shrink=0.8)

    _mask_artist = _axes[1, 0].imshow(
        final_source_mask,
        origin="lower",
        cmap="binary",
        vmin=0,
        vmax=1,
    )
    _axes[1, 0].set_title("Returned final continuum source mask")
    _figure.colorbar(
        _mask_artist,
        ax=_axes[1, 0],
        ticks=[0, 1],
        shrink=0.8,
    )

    _axes[1, 1].imshow(
        selected_input_image,
        origin="lower",
        cmap="gray",
        vmin=_lower,
        vmax=_upper,
    )
    if _component_pixels.size:
        _axes[1, 1].scatter(
            _component_pixels[:, 0],
            _component_pixels[:, 1],
            s=28,
            facecolors="none",
            edgecolors="tab:cyan",
            linewidths=0.8,
            label="Gaussian component",
        )
    if _source_pixels.size:
        _axes[1, 1].scatter(
            _source_pixels[:, 0],
            _source_pixels[:, 1],
            s=55,
            marker="*",
            color="tab:orange",
            linewidths=0.4,
            label="Associated source",
        )
    _axes[1, 1].set_title("Returned catalogue positions")
    if _source_pixels.size or _component_pixels.size:
        _axes[1, 1].legend(loc="upper right")
    for _axis in _axes.flat:
        _axis.set(xlabel="x pixel", ylabel="y pixel")
    mo.vstack(
        [
            mo.md(f"### Final products for {selected_input_label}"),
            mo.mpl.interactive(_figure),
            mo.callout(
                "The lower-left panel is loaded directly from "
                "source_finder_result.mask_path. It is the final continuum "
                "publication mask, not a compact-stage or intermediate "
                "multiscale mask.",
                kind="info",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo, source_catalogue):
    _rows = [
        {
            "source_id": _source.source_id,
            "island_id": _source.island_id,
            "ra_deg": _source.position.right_ascension_degrees,
            "dec_deg": _source.position.declination_degrees,
            "peak_jy_per_beam": _source.flux.peak_flux_jy_per_beam,
            "integrated_flux_jy": _source.flux.integrated_flux_jy,
            "local_rms_jy_per_beam": _source.flux.local_rms_jy_per_beam,
            "quality_flags": ", ".join(_source.quality_flags),
        }
        for _source in source_catalogue.sources
    ]
    catalogue_browser = mo.ui.table(
        _rows,
        selection=None,
        page_size=15,
    )
    mo.vstack([mo.md("### Associated-source catalogue"), catalogue_browser])
    return (catalogue_browser,)


@app.cell(hide_code=True)
def _(
    json,
    mo,
    source_finder_config,
    source_finder_diagnostics,
    source_finder_result,
):
    _configuration = {
        "detection_threshold_sigma": (
            source_finder_config.detection_threshold_sigma
        ),
        "island_threshold_sigma": source_finder_config.island_threshold_sigma,
        "minimum_island_pixels": source_finder_config.minimum_island_pixels,
        "maximum_island_pixels": source_finder_config.maximum_island_pixels,
        "profile": source_finder_config.profile,
    }
    _current_composition = (
        source_finder_diagnostics.provenance.scientific_composition_sha256
    )
    mo.vstack(
        [
            mo.md("## Run details and interpretation"),
            mo.accordion(
                {
                    "Show caller-owned configuration": mo.md(
                        "    "
                        + json.dumps(
                            _configuration,
                            indent=2,
                            sort_keys=True,
                        ).replace("\n", "\n    ")
                    )
                }
            ),
            mo.md(
                f"**Mask SHA-256:** {source_finder_result.mask.content_sha256}  \n"
                "**Scientific profile SHA-256:** "
                f"{source_finder_diagnostics.provenance.scientific_profile_sha256}  \n"
                f"**Scientific composition SHA-256:** {_current_composition}"
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Reading the final mask

    **Too much support around a bright source:** inspect the returned RMS map
    first. The continuum profile owns adaptive background/RMS policy. Raising
    the global detection threshold also removes faint sources in quiet areas.

    **Faint compact sources are missing:** lower the detection threshold in
    0.25-sigma steps and quantify completeness and reliability with injections
    or a deeper external catalogue.

    **Source wings are missing:** lower the island threshold while keeping the
    detection threshold fixed. Watch for neighbours or artifacts becoming
    connected.

    **Comparing M51 with the comparison notebook:** the downloaded cutout can
    differ from the campaign's prepared input, and settings or Hebog code may
    also differ. Use the saved campaign inputs when investigating a difference;
    ordinary workbench experiments do not need to reproduce campaign results.
    See the notebook guide for the comparison refresh commands.

    **Commissioning use:** cross-match bright isolated sources against a
    trusted catalogue. Inspect astrometric offsets, measured/reference flux
    ratios, local RMS, source density, and integrated-to-peak flux ratio across
    the field.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Scope and limitations

    - The current public scientific preview accepts ICRS Jy/beam images no
      larger than 1,024 pixels on either spatial axis.
    - The continuum profile is a development candidate. Its diagnostics do not
      claim production or publication readiness.
    - The catalogue and mask are not primary-beam corrected, cross-matched, or
      associated with optical or infrared host galaxies.
    - LoTSS observations are useful stress cases but contain no injected
      truth. Agreement with another finder is not ground truth.
    - Follow the LoTSS data-release citation and credit guidance if a cutout
      contributes to science.
    """).callout(kind="warn")
    return


if __name__ == "__main__":
    app.run()
