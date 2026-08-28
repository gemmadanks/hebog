# ruff: noqa: C901, E501, PLR0915

import marimo

__generated_with = "0.23.15"
app = marimo.App(width="full")


@app.cell(hide_code=True)
def _():
    import marimo as mo

    return (mo,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Hebog radio source-finding workbench

    Use this notebook to inspect a radio-continuum FITS image, tune Hebog's
    compact-source finder, run it, and examine the catalogue and detection
    diagnostics. It is intended for two closely related activities:

    - **research catalogues:** balance completeness and reliability, measure
      positions and flux densities, and identify blends;
    - **commissioning and image QA:** map the achieved noise, find bright-source
      artifacts, inspect source masks, and produce a sky model for comparison
      with an external catalogue.

    Start with the offline synthetic image or one of the official **LoTSS DR2**
    cutouts. Then load your own restored Stokes-I FITS image. Every scientific
    parameter used for a run is written beside its output catalogue.

    > This notebook exercises Hebog's implemented bounded compact-source and
    > multiscale-support stages directly. The package-level
    > `hebog.pipeline.find_sources()` entry point is not implemented yet. See
    > **Scope and limitations** before using the products in a publication or
    > commissioning decision.
    """)
    return


@app.cell
def _():
    import datetime as datetime_module
    import json
    import pathlib
    import re
    import tempfile
    import time
    import urllib.parse as urllib_parse
    import urllib.request as urllib_request

    import matplotlib.pyplot as plt
    import numpy as np
    from astropy.io import fits

    import hebog.adapters.rapthor_catalogue as catalogue_adapter
    import hebog.algorithms.astrometry as astrometry_algorithms
    import hebog.algorithms.catalogue as catalogue_algorithms
    import hebog.algorithms.multiscale as multiscale_algorithms
    import hebog.algorithms.partitioning as partitioning_algorithms
    import hebog.config as hebog_config
    import hebog.data_models as hebog_models
    import hebog.executors as hebog_executors
    import hebog.io as hebog_io
    import hebog.stages.catalogue as catalogue_stage
    import hebog.stages.detection as detection_stage
    import hebog.stages.multiscale as multiscale_stage
    from hebog.algorithms import phase_five_execution

    return (
        astrometry_algorithms,
        catalogue_adapter,
        catalogue_algorithms,
        catalogue_stage,
        datetime_module,
        detection_stage,
        fits,
        hebog_config,
        hebog_executors,
        hebog_io,
        hebog_models,
        json,
        multiscale_algorithms,
        multiscale_stage,
        np,
        pathlib,
        partitioning_algorithms,
        phase_five_execution,
        plt,
        re,
        tempfile,
        time,
        urllib_parse,
        urllib_request,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## What astronomers usually do with a source finder

    Radio source finding usually follows four stages: estimate and subtract
    the background, identify significant emission, characterize components,
    and publish a catalogue. In practice, the catalogue is often an
    intermediate product rather than the final scientific result.

    | Activity | What to inspect here | Typical follow-up |
    | --- | --- | --- |
    | Blind survey catalogue | Completeness near the threshold, blends, flux and position distributions | Injection/recovery tests and cross-match to a deeper reference |
    | Commissioning / image QA | RMS uniformity, bright-source neighborhoods, edge behavior, source density | Astrometric and flux-scale offsets versus a trusted catalogue |
    | Calibration or subtraction sky model | Reliable bright components and fitted sizes | Convert to the calibration pipeline's sky-model schema |
    | Source masks for imaging or diffuse science | Island extent and unmasked source residuals | Dilate/review masks before background or diffuse-emission analysis |
    | Multi-epoch variability / transients | Stable positions, epoch-to-epoch fluxes, false positives | Cross-match catalogues or use forced photometry |
    | Extended and complex emission | Persistent scale support, fragmentation, and emission outside the compact mask | Run multiscale support, then inspect model/residual products before publication |

    The controls below emphasize the quantities repeatedly identified in
    source-finder literature and operational documentation:

    - the **seed threshold** controls the main completeness/reliability trade;
    - the lower **island threshold** controls how much connected emission is
      measured around a detection;
    - the **RMS window scale** must follow instrumental noise/artifact changes
      without treating real emission as noise;
    - **deblending** determines whether neighboring peaks become one source or
      several components.

    Useful background reading: [Hancock et al. on compact radio source
    finding](https://arxiv.org/abs/1202.4500), [PyBDSF parameter
    guidance](https://pybdsf.readthedocs.io/en/latest/process_image.html),
    [PyBDSF artifact and extended-emission
    examples](https://github.com/lofar-astron/PyBDSF/blob/master/doc/source/examples.rst),
    and [Aegean forced-fitting
    guidance](https://aegeantools.readthedocs.io/en/dev-aegean/includes/aegean.html#priorized-fitting).
    """)
    return


@app.cell
def _(mo):
    image_selector = mo.ui.dropdown(
        options={
            "Synthetic commissioning field (offline)": "synthetic",
            "Synthetic 100-source survey field (offline)": (
                "synthetic-survey"
            ),
            "LoTSS DR2: representative ~100-source field (22 arcmin)": (
                "lotss-survey-100"
            ),
            "LoTSS DR2: 3C 295 bright-source field (12 arcmin)": (
                "lotss-3c295"
            ),
            "LoTSS DR2: M51 complex-emission field (20 arcmin)": ("lotss-m51"),
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
            mo.md("## 1. Choose an image"),
            mo.hstack([image_selector, load_image], widths=[3, 1]),
            custom_image_path,
            mo.callout(
                mo.md(
                    "LoTSS examples are downloaded on demand from the "
                    "[official cutout API]"
                    "(https://lofar-surveys.org/cutout_api_details.html) "
                    "and cached in the operating system's temporary "
                    "directory. The synthetic image requires no network."
                ),
                kind="info",
            ),
        ]
    )
    return custom_image_path, image_selector, load_image


@app.cell
def _(
    custom_image_path,
    fits,
    hebog_io,
    load_image,
    mo,
    np,
    pathlib,
    tempfile,
    urllib_parse,
    urllib_request,
    image_selector,
):
    mo.stop(
        not load_image.value,
        mo.md("Select an image and press **Load selected image**."),
    )

    _examples = {
        "lotss-survey-100": {
            "label": "LoTSS DR2 representative survey field",
            "position": "12:00:00 +45:00:00",
            "size_arcmin": 22,
            "filename": "lotss-dr2-survey-field-22arcmin.fits",
        },
        "lotss-3c295": {
            "label": "LoTSS DR2 3C 295 field",
            "position": "14:11:20.6 +52:12:10",
            "size_arcmin": 12,
            "filename": "lotss-dr2-3c295-12arcmin.fits",
        },
        "lotss-m51": {
            "label": "LoTSS DR2 M51 field",
            "position": "13:29:52.7 +47:11:43",
            "size_arcmin": 20,
            "filename": "lotss-dr2-m51-20arcmin.fits",
        },
    }
    _cache = pathlib.Path(tempfile.gettempdir()) / "hebog-marimo-images"
    _cache.mkdir(parents=True, exist_ok=True)

    def _write_synthetic_image(_path):
        _rng = np.random.default_rng(20260827)
        _shape = (512, 512)
        _y, _x = np.indices(_shape, dtype=np.float64)
        _noise_rms = 1.0e-4
        _image = _rng.normal(0.0, _noise_rms, _shape)
        _image += 2.0e-8 * (_x - _shape[1] / 2.0)

        def _add_gaussian(_x0, _y0, _peak, _sx, _sy):
            _image[:] += _peak * np.exp(
                -0.5 * (((_x - _x0) / _sx) ** 2 + ((_y - _y0) / _sy) ** 2)
            )

        _sources = (
            (110.0, 380.0, 8.0e-4, 2.2, 1.8),
            (245.0, 270.0, 1.8e-3, 2.4, 2.0),
            (256.0, 272.0, 1.4e-3, 2.4, 2.0),
            (398.0, 132.0, 1.2e-2, 2.2, 1.8),
            (165.0, 155.0, 8.5e-4, 13.0, 5.0),
        )
        for _source in _sources:
            _add_gaussian(*_source)

        _radius = np.hypot(_x - 398.0, _y - 132.0)
        _image += 3.0e-4 * np.cos(_radius / 2.8) * np.exp(-_radius / 42.0)
        _image[28:46, 450:476] = np.nan

        _header = fits.Header()
        _header["BUNIT"] = "Jy/beam"
        _header["BMAJ"] = 6.0 / 3600.0
        _header["BMIN"] = 5.0 / 3600.0
        _header["BPA"] = 18.0
        _header["RESTFRQ"] = 150.0e6
        _header["CTYPE1"] = "RA---SIN"
        _header["CTYPE2"] = "DEC--SIN"
        _header["CUNIT1"] = "deg"
        _header["CUNIT2"] = "deg"
        _header["CRPIX1"] = 256.5
        _header["CRPIX2"] = 256.5
        _header["CRVAL1"] = 212.835
        _header["CRVAL2"] = 52.2028
        _header["CDELT1"] = -1.5 / 3600.0
        _header["CDELT2"] = 1.5 / 3600.0
        fits.PrimaryHDU(data=_image, header=_header).writeto(
            _path,
            overwrite=True,
        )
        return {
            "sources": _sources,
            "noise_rms_base": _noise_rms,
            "noise_rms_intercept": 1.0,
            "noise_rms_x_slope": 0.0,
            "image_width": _shape[1],
            "excluded_features": (
                "the injected bright-source rings, noise, and invalid "
                "rectangle"
            ),
        }

    def _write_synthetic_survey_image(_path):
        _rng = np.random.default_rng(20260828)
        _shape = (1024, 1024)
        _y, _x = np.indices(_shape, dtype=np.float64)
        _noise_rms_base = 8.0e-5
        _noise_scale = 0.75 + 0.50 * _x / (_shape[1] - 1)
        _image = _rng.normal(0.0, 1.0, _shape) * (
            _noise_rms_base * _noise_scale
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
        _sources = []
        _extended_source_start = 94
        for _source_index, ((_x0, _y0), _peak_snr) in enumerate(
            zip(_centres, _peak_snrs, strict=True)
        ):
            _local_rms = _noise_rms_base * (
                0.75 + 0.50 * _x0 / (_shape[1] - 1)
            )
            _size_scale = (
                _rng.uniform(1.8, 4.0)
                if _source_index >= _extended_source_start
                else 1.0
            )
            _sigma_x = _rng.uniform(1.7, 2.2) * _size_scale
            _sigma_y = _rng.uniform(1.3, 1.8) * _size_scale
            _peak = float(_peak_snr * _local_rms)
            _sources.append(
                (
                    float(_x0),
                    float(_y0),
                    _peak,
                    float(_sigma_x),
                    float(_sigma_y),
                )
            )
            _image += _peak * np.exp(
                -0.5
                * (((_x - _x0) / _sigma_x) ** 2 + ((_y - _y0) / _sigma_y) ** 2)
            )
        _image[470:502, 805:850] = np.nan

        _header = fits.Header()
        _header["BUNIT"] = "Jy/beam"
        _header["BMAJ"] = 7.0 / 3600.0
        _header["BMIN"] = 5.0 / 3600.0
        _header["BPA"] = 27.0
        _header["RESTFRQ"] = 144.0e6
        _header["CTYPE1"] = "RA---SIN"
        _header["CTYPE2"] = "DEC--SIN"
        _header["CUNIT1"] = "deg"
        _header["CUNIT2"] = "deg"
        _header["CRPIX1"] = 512.5
        _header["CRPIX2"] = 512.5
        _header["CRVAL1"] = 180.0
        _header["CRVAL2"] = 45.0
        _header["CDELT1"] = -1.5 / 3600.0
        _header["CDELT2"] = 1.5 / 3600.0
        fits.PrimaryHDU(data=_image, header=_header).writeto(
            _path,
            overwrite=True,
        )
        return {
            "sources": tuple(_sources),
            "noise_rms_base": _noise_rms_base,
            "noise_rms_intercept": 0.75,
            "noise_rms_x_slope": 0.50,
            "image_width": _shape[1],
            "excluded_features": "noise and the invalid rectangle",
        }

    if image_selector.value == "synthetic":
        selected_input_path = _cache / "synthetic-commissioning-field.fits"
        selected_truth_model = _write_synthetic_image(selected_input_path)
        selected_input_label = "Synthetic commissioning field"
        selected_input_provenance = (
            "Generated deterministically in this notebook; noise seed "
            "20260827."
        )
    elif image_selector.value == "synthetic-survey":
        selected_input_path = _cache / "synthetic-100-source-survey.fits"
        selected_truth_model = _write_synthetic_survey_image(
            selected_input_path
        )
        selected_input_label = "Synthetic 100-source survey field"
        selected_input_provenance = (
            "Generated deterministically in this notebook with exactly 100 "
            "injected sources spanning 4 to 80 sigma, five close pairs, six "
            "extended sources, spatially varying noise, and noise seed "
            "20260828."
        )
    elif image_selector.value == "custom":
        selected_truth_model = None
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
                f"No file exists at `{selected_input_path}`.",
                kind="danger",
            ),
        )
        selected_input_label = selected_input_path.name
        selected_input_provenance = "User-supplied FITS image."
    else:
        selected_truth_model = None
        _record = _examples[image_selector.value]
        selected_input_path = _cache / _record["filename"]
        if not selected_input_path.exists():
            _query = urllib_parse.urlencode(
                {
                    "pos": _record["position"],
                    "size": _record["size_arcmin"],
                }
            )
            _url = f"https://lofar-surveys.org/dr2-cutout.fits?{_query}"
            try:
                with urllib_request.urlopen(_url, timeout=120) as _response:
                    selected_input_path.write_bytes(_response.read())
            except Exception as _error:
                selected_input_path.unlink(missing_ok=True)
                mo.stop(
                    True,
                    mo.callout(
                        "The LoTSS cutout could not be downloaded. Check "
                        f"network access and retry. Details: `{_error}`",
                        kind="danger",
                    ),
                )
        selected_input_label = _record["label"]
        selected_input_provenance = (
            "LoTSS DR2 cutout from https://lofar-surveys.org/; "
            f"position {_record['position']}, size "
            f"{_record['size_arcmin']} arcmin."
        )
        if image_selector.value == "lotss-survey-100":
            selected_input_provenance += (
                " The field is expected to contain roughly 100 catalogue "
                "sources from the DR2-wide mean density of about 780 sources "
                "per square degree; the observed count varies with local "
                "sensitivity, morphology, and catalogue association."
            )

    try:
        source_reader = hebog_io.FitsImageSource(selected_input_path)
        source_metadata = source_reader.metadata()
    except Exception as _error:
        mo.stop(
            True,
            mo.callout(
                "Hebog could not use this FITS image. It needs a finite "
                "two-dimensional logical plane, celestial WCS, BUNIT, "
                "BMAJ/BMIN/BPA, and a reference frequency. Details: "
                f"`{_error}`",
                kind="danger",
            ),
        )
    return (
        selected_input_label,
        selected_input_path,
        selected_input_provenance,
        selected_truth_model,
        source_metadata,
        source_reader,
    )


@app.cell
def _(mo, source_metadata):
    _height, _width = source_metadata.shape_yx
    preview_center_x = mo.ui.number(
        start=0,
        stop=max(0, _width - 1),
        step=1,
        value=_width // 2,
        label="Preview centre x",
    )
    preview_center_y = mo.ui.number(
        start=0,
        stop=max(0, _height - 1),
        step=1,
        value=_height // 2,
        label="Preview centre y",
    )
    preview_size = mo.ui.dropdown(
        options={
            "256 px": 256,
            "512 px": 512,
            "1024 px": 1024,
            "1536 px": 1536,
        },
        value="512 px",
        label="Preview width",
    )
    mo.vstack(
        [
            mo.md("### Bounded preview"),
            mo.hstack(
                [preview_center_x, preview_center_y, preview_size],
                widths="equal",
            ),
            mo.md(
                "The analysis can cover the complete image, but plots read "
                "only this bounded window so a large survey mosaic is not "
                "materialized in the notebook process."
            ),
        ]
    )
    return preview_center_x, preview_center_y, preview_size


@app.cell
def _(
    hebog_models,
    preview_center_x,
    preview_center_y,
    preview_size,
    source_metadata,
    source_reader,
):
    _height, _width = source_metadata.shape_yx
    _requested = int(preview_size.value)
    _preview_width = min(_requested, _width)
    _preview_height = min(_requested, _height)
    _x_start = max(
        0,
        min(
            _width - _preview_width,
            int(preview_center_x.value) - _preview_width // 2,
        ),
    )
    _y_start = max(
        0,
        min(
            _height - _preview_height,
            int(preview_center_y.value) - _preview_height // 2,
        ),
    )
    preview_bounds = hebog_models.ImageBounds(
        y_start=_y_start,
        y_stop=_y_start + _preview_height,
        x_start=_x_start,
        x_stop=_x_start + _preview_width,
    )
    preview_values = source_reader.read_window(preview_bounds).values
    return preview_bounds, preview_values


@app.cell
def _(
    mo,
    np,
    plt,
    preview_bounds,
    preview_values,
    selected_input_label,
    selected_input_path,
    selected_input_provenance,
    source_metadata,
):
    _finite = preview_values[np.isfinite(preview_values)]
    _lower, _upper = (
        np.percentile(_finite, (1.0, 99.7)) if _finite.size else (0.0, 1.0)
    )
    _figure, _axis = plt.subplots(figsize=(8.0, 6.0))
    _artist = _axis.imshow(
        preview_values,
        origin="lower",
        cmap="gray",
        vmin=_lower,
        vmax=_upper,
        extent=(
            preview_bounds.x_start,
            preview_bounds.x_stop,
            preview_bounds.y_start,
            preview_bounds.y_stop,
        ),
    )
    _axis.set(
        title=selected_input_label,
        xlabel="x pixel",
        ylabel="y pixel",
    )
    _figure.colorbar(
        _artist,
        ax=_axis,
        label=source_metadata.unit,
        shrink=0.82,
    )
    _figure.tight_layout()
    _beam = source_metadata.beam
    mo.vstack(
        [
            mo.md(
                f"**Path:** `{selected_input_path}`  \n"
                f"**Shape:** `{source_metadata.shape_yx[0]} x "
                f"{source_metadata.shape_yx[1]}` pixels  \n"
                f"**Unit:** `{source_metadata.unit}`  \n"
                f"**Restoring beam:** "
                f"`{3600 * _beam.major_fwhm_degrees:.2f} x "
                f"{3600 * _beam.minor_fwhm_degrees:.2f} arcsec`, "
                f"PA `{_beam.position_angle_degrees:.1f} deg`  \n"
                f"**Reference frequency:** "
                f"`{source_metadata.reference_frequency_hz / 1e6:.3f} MHz`  "
                f"\n**Provenance:** {selected_input_provenance}"
            ),
            _figure,
        ]
    )
    return


@app.cell
def _(mo):
    workflow_presets = {
        "survey": {
            "detection": 5.0,
            "island": 3.0,
            "minimum_pixels": 7,
            "rms_window": 150,
            "adaptive": True,
            "adaptive_threshold": 75.0,
            "fine_window": 35,
            "deblend_separation": 2,
            "saddle_depth": 1.0,
        },
        "commissioning": {
            "detection": 6.0,
            "island": 4.0,
            "minimum_pixels": 7,
            "rms_window": 96,
            "adaptive": True,
            "adaptive_threshold": 40.0,
            "fine_window": 31,
            "deblend_separation": 2,
            "saddle_depth": 1.5,
        },
        "completeness": {
            "detection": 4.5,
            "island": 3.0,
            "minimum_pixels": 5,
            "rms_window": 192,
            "adaptive": True,
            "adaptive_threshold": 75.0,
            "fine_window": 35,
            "deblend_separation": 2,
            "saddle_depth": 0.75,
        },
        "crowded-survey": {
            "detection": 5.0,
            "island": 3.0,
            "minimum_pixels": 7,
            "rms_window": 192,
            "adaptive": True,
            "adaptive_threshold": 75.0,
            "fine_window": 35,
            "deblend_separation": 2,
            "saddle_depth": 1.0,
        },
    }
    workflow_selector = mo.ui.dropdown(
        options={
            "Balanced survey catalogue": "survey",
            "Commissioning / artifact triage": "commissioning",
            "Completeness experiment": "completeness",
            "Crowded survey / source-count QA": "crowded-survey",
        },
        value="Balanced survey catalogue",
        label="Starting preset",
    )
    mo.vstack(
        [
            mo.md("## 2. Choose a starting point"),
            workflow_selector,
            mo.md(
                "A preset only initializes the controls. Treat it as a "
                "hypothesis to test, not as a survey-independent default."
            ),
        ]
    )
    return workflow_presets, workflow_selector


@app.cell
def _(
    mo,
    pathlib,
    tempfile,
    workflow_presets,
    workflow_selector,
):
    _preset = workflow_presets[workflow_selector.value]
    detection_threshold = mo.ui.slider(
        start=3.5,
        stop=10.0,
        step=0.25,
        value=_preset["detection"],
        label="Detection / seed threshold (sigma)",
        show_value=True,
    )
    island_threshold = mo.ui.slider(
        start=2.0,
        stop=6.0,
        step=0.25,
        value=_preset["island"],
        label="Island / flood threshold (sigma)",
        show_value=True,
    )
    minimum_island_pixels = mo.ui.dropdown(
        options={str(_value): _value for _value in (3, 5, 7, 10, 15, 25)},
        value=str(_preset["minimum_pixels"]),
        label="Minimum island pixels",
    )
    rms_window = mo.ui.dropdown(
        options={
            f"{_value} px": _value
            for _value in (32, 48, 64, 96, 128, 150, 192, 256, 384)
        },
        value=f"{_preset['rms_window']} px",
        label="Coarse RMS window",
    )
    adaptive_rms = mo.ui.checkbox(
        value=_preset["adaptive"],
        label="Use a finer RMS grid around bright candidates",
    )
    adaptive_candidate_threshold = mo.ui.slider(
        start=20.0,
        stop=300.0,
        step=5.0,
        value=_preset["adaptive_threshold"],
        label="Bright-candidate threshold (sigma)",
        show_value=True,
    )
    adaptive_window = mo.ui.dropdown(
        options={
            f"{_value} px": _value for _value in (15, 21, 31, 35, 47, 63, 95)
        },
        value=f"{_preset['fine_window']} px",
        label="Fine RMS window",
    )
    deblend_peak_separation = mo.ui.slider(
        start=1,
        stop=10,
        step=1,
        value=_preset["deblend_separation"],
        label="Minimum peak separation (pixels)",
        show_value=True,
    )
    deblend_saddle_depth = mo.ui.slider(
        start=0.25,
        stop=5.0,
        step=0.25,
        value=_preset["saddle_depth"],
        label="Minimum saddle depth (sigma)",
        show_value=True,
    )
    tile_size = mo.ui.dropdown(
        options={
            "128 px": 128,
            "256 px": 256,
            "512 px": 512,
            "1024 px": 1024,
        },
        value="256 px",
        label="Tile core",
    )
    run_multiscale = mo.ui.checkbox(
        value=True,
        label="Run bounded multiscale support analysis",
    )
    multiscale_detection_threshold = mo.ui.slider(
        start=3.5,
        stop=10.0,
        step=0.25,
        value=5.0,
        label="Multiscale seed threshold (sigma)",
        show_value=True,
    )
    multiscale_island_threshold = mo.ui.slider(
        start=2.0,
        stop=6.0,
        step=0.25,
        value=3.0,
        label="Multiscale island threshold (sigma)",
        show_value=True,
    )
    multiscale_support_fraction = mo.ui.slider(
        start=0.3,
        stop=0.9,
        step=0.05,
        value=0.5,
        label="Minimum valid scale support fraction",
        show_value=True,
    )
    multiscale_minimum_area_beams = mo.ui.slider(
        start=0.25,
        stop=4.0,
        step=0.25,
        value=1.0,
        label="Minimum island area (beams)",
        show_value=True,
    )
    multiscale_tiles_per_batch = mo.ui.dropdown(
        options={
            "1 tile": 1,
            "2 tiles": 2,
            "4 tiles": 4,
            "8 tiles": 8,
        },
        value="2 tiles",
        label="Multiscale tiles per task",
    )
    run_label = mo.ui.text(
        value="experiment",
        label="Run label",
    )
    output_directory = mo.ui.text(
        value=str(
            pathlib.Path(tempfile.gettempdir()) / "hebog-workbench-output"
        ),
        label="Output root",
        full_width=True,
    )
    run_hebog = mo.ui.run_button(label="Run Hebog")

    mo.vstack(
        [
            mo.md("## 3. Tune and run"),
            mo.md("### Detection and island extent"),
            mo.hstack(
                [
                    detection_threshold,
                    island_threshold,
                    minimum_island_pixels,
                ],
                widths="equal",
            ),
            mo.md("### Background and local noise"),
            mo.hstack(
                [rms_window, adaptive_window],
                widths="equal",
            ),
            adaptive_rms,
            adaptive_candidate_threshold,
            mo.md("### Deblending and execution"),
            mo.hstack(
                [
                    deblend_peak_separation,
                    deblend_saddle_depth,
                    tile_size,
                ],
                widths="equal",
            ),
            mo.md("### Multiscale / diffuse-support exploration"),
            run_multiscale,
            mo.hstack(
                [
                    multiscale_detection_threshold,
                    multiscale_island_threshold,
                    multiscale_support_fraction,
                ],
                widths="equal",
            ),
            mo.hstack(
                [
                    multiscale_minimum_area_beams,
                    multiscale_tiles_per_batch,
                ],
                widths="equal",
            ),
            mo.callout(
                mo.md(
                    "This runs Hebog's beam-aware matched-filter and "
                    "three-level B3 a trous stage on the "
                    "background-subtracted image. It publishes support and "
                    "topology evidence, not yet a combined "
                    "compact-plus-extended catalogue."
                ),
                kind="info",
            ),
            mo.hstack([run_label, run_hebog], widths=[3, 1]),
            output_directory,
        ]
    )
    return (
        adaptive_candidate_threshold,
        adaptive_rms,
        adaptive_window,
        deblend_peak_separation,
        deblend_saddle_depth,
        detection_threshold,
        island_threshold,
        minimum_island_pixels,
        multiscale_detection_threshold,
        multiscale_island_threshold,
        multiscale_minimum_area_beams,
        multiscale_support_fraction,
        multiscale_tiles_per_batch,
        output_directory,
        rms_window,
        run_hebog,
        run_label,
        run_multiscale,
        tile_size,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### How each control changes the science

    | Control | Lower value | Higher value | First diagnostic to check |
    | --- | --- | --- | --- |
    | Detection threshold | More faint sources and more false positives | Purer but less complete catalogue | Negative image or injected-source recovery |
    | Island threshold | Includes fainter wings; may bridge neighbors | Smaller, more fragmented islands | Mask over the image and integrated flux |
    | Minimum island pixels | Admits tiny/noise islands | Rejects small real sources if too aggressive | Beam area in pixels and faint-source morphology |
    | Coarse RMS window | Follows local artifacts; may absorb source emission | Smooth noise map; may miss local dynamic-range problems | RMS panel around bright and extended sources |
    | Adaptive bright-source RMS | Raises local noise where artifacts vary rapidly | Disabled behavior uses only the coarse grid | False detections around the brightest source |
    | Peak separation | Splits close peaks more readily | Requires components to be farther apart | Known doubles and crowded islands |
    | Saddle depth | Splits shallow substructure | Keeps neighboring peaks together unless clearly distinct | Component count per island |
    | Multiscale seed/island thresholds | Recovers weaker broad structure, with more noise risk | Retains stronger scale-coherent support | Combined SNR and persistent support |
    | Scale support fraction | Admits more edge/invalid-clipped support | Requires more valid filter coverage | Image edges and invalid regions |
    | Minimum area in beams | Retains smaller detections | Rejects sub-beam or fragmented support | Retained mask and scale-island counts |

    Keep the island threshold below the detection threshold. A common first
    experiment is 5 sigma seeds and 3 sigma islands. When bright-source
    artifacts dominate, adjust the RMS scale before globally raising the seed
    threshold: a global cut also removes real faint sources from quiet parts of
    the image.
    """)
    return


@app.cell
def _(
    detection_threshold,
    island_threshold,
    mo,
    multiscale_detection_threshold,
    multiscale_island_threshold,
    output_directory,
    run_label,
    run_multiscale,
):
    _problems = []
    if island_threshold.value >= detection_threshold.value:
        _problems.append(
            "The island threshold must be below the detection threshold."
        )
    if (
        run_multiscale.value
        and multiscale_island_threshold.value
        >= multiscale_detection_threshold.value
    ):
        _problems.append(
            "The multiscale island threshold must be below its detection "
            "threshold."
        )
    if not run_label.value.strip():
        _problems.append("Give the run a non-empty label.")
    if not output_directory.value.strip():
        _problems.append("Choose a non-empty output root.")
    parameter_error = " ".join(_problems)
    if parameter_error:
        _parameter_status = mo.callout(parameter_error, kind="danger")
    else:
        _parameter_status = mo.callout(
            "Parameters are internally consistent. Press **Run Hebog** "
            "when ready.",
            kind="success",
        )
    _parameter_status  # noqa: B018
    return (parameter_error,)


@app.cell
def _(
    adaptive_candidate_threshold,
    adaptive_rms,
    adaptive_window,
    astrometry_algorithms,
    catalogue_adapter,
    catalogue_algorithms,
    catalogue_stage,
    datetime_module,
    deblend_peak_separation,
    deblend_saddle_depth,
    detection_stage,
    detection_threshold,
    hebog_config,
    hebog_executors,
    hebog_io,
    island_threshold,
    json,
    minimum_island_pixels,
    mo,
    multiscale_algorithms,
    multiscale_detection_threshold,
    multiscale_island_threshold,
    multiscale_minimum_area_beams,
    multiscale_stage,
    multiscale_support_fraction,
    multiscale_tiles_per_batch,
    np,
    output_directory,
    parameter_error,
    pathlib,
    partitioning_algorithms,
    phase_five_execution,
    re,
    rms_window,
    run_hebog,
    run_label,
    run_multiscale,
    selected_input_label,
    selected_input_path,
    selected_input_provenance,
    source_metadata,
    tile_size,
    time,
):
    mo.stop(
        not run_hebog.value,
        mo.md("Configure the experiment, then press **Run Hebog**."),
    )
    mo.stop(
        bool(parameter_error),
        mo.callout(parameter_error, kind="danger"),
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
    _output_root = pathlib.Path(output_directory.value).expanduser().resolve()
    _run_directory = _output_root / _run_id
    _run_directory.mkdir(parents=True, exist_ok=False)

    _statistics = hebog_config.RmsWindowStatisticsConfig(
        clipping_sigma=3.0,
        maximum_iterations=10,
        minimum_samples=6,
    )
    _height, _width = source_metadata.shape_yx
    _coarse_y = min(int(rms_window.value), _height)
    _coarse_x = min(int(rms_window.value), _width)
    _coarse_step = (
        max(1, _coarse_y // 4),
        max(1, _coarse_x // 4),
    )
    _fine_y = min(int(adaptive_window.value), _height)
    _fine_x = min(int(adaptive_window.value), _width)
    _fine_step = (max(1, _fine_y // 4), max(1, _fine_x // 4))
    _adaptive = None
    if adaptive_rms.value:
        _adaptive = hebog_config.AdaptiveRmsConfig(
            grid=hebog_config.RmsGridConfig(
                window_shape_yx=(_fine_y, _fine_x),
                step_yx=_fine_step,
                statistics=_statistics,
                maximum_batch_cells=32,
            ),
            candidate_threshold_sigma=float(
                adaptive_candidate_threshold.value
            ),
            influence_radius_pixels=float(max(_coarse_y, _coarse_x) / 2),
            transition_width_pixels=float(max(1, min(_fine_y, _fine_x) / 2)),
        )
    _detection_config = detection_stage.DetectionStageConfig(
        background_rms=hebog_config.BackgroundRmsConfig(
            coarse=hebog_config.RmsGridConfig(
                window_shape_yx=(_coarse_y, _coarse_x),
                step_yx=_coarse_step,
                statistics=_statistics,
                maximum_batch_cells=32,
            ),
            adaptive=_adaptive,
            maximum_spatial_window_fraction=0.25,
            maximum_constant_map_pixels=2048 * 2048,
        ),
        source_finder=hebog_config.SourceFinderConfig(
            detection_threshold_sigma=float(detection_threshold.value),
            island_threshold_sigma=float(island_threshold.value),
            minimum_island_pixels=int(minimum_island_pixels.value),
        ),
    )
    _deblend_config = hebog_config.CompactDeblendConfig(
        minimum_peak_signal_to_noise=float(detection_threshold.value),
        minimum_peak_separation_pixels=int(deblend_peak_separation.value),
        minimum_saddle_depth_sigma=float(deblend_saddle_depth.value),
        minimum_region_pixels=int(minimum_island_pixels.value),
        maximum_compact_island_pixels=250_000,
        maximum_compact_bounds_pixels=1_000_000,
        target_batch_pixels=250_000,
        maximum_batch_pixels=4_000_000,
    )
    _moment_config = hebog_config.CompactMomentConfig(
        minimum_shape_pixels=3,
        covariance_relative_tolerance=1e-12,
    )
    _fit_config = hebog_config.CompactGaussianFitConfig(
        minimum_fit_pixels=7,
        maximum_function_evaluations=300,
        minimum_sigma_pixels=0.2,
        maximum_sigma_pixels=30.0,
        maximum_amplitude_factor=5.0,
        center_margin_pixels=1.0,
        convergence_tolerance=1e-8,
        maximum_axis_ratio=30.0,
        model_selection="beam-or-free",
        position_estimator="selected-model",
        component_extension_significance_sigma=1.5,
        integrated_flux_bias_correction_sigma=0.075,
        association_aperture_radius_sigma=1.5,
    )
    _catalogue_config = hebog_config.CompactCatalogueConfig(
        maximum_catalogue_records=100_000,
        deconvolution_relative_tolerance=1e-10,
        extension_significance_sigma=5.0,
    )
    _manifest = partitioning_algorithms.plan_image_partitions(
        image_shape_yx=source_metadata.shape_yx,
        tile_core_shape_yx=(
            min(int(tile_size.value), _height),
            min(int(tile_size.value), _width),
        ),
        halo_yx=(0, 0),
    )
    _sink = hebog_io.ZarrProductSink(
        _run_directory / "products.zarr",
        _manifest,
        generation_id=_run_id,
    )
    _executor = hebog_executors.SerialExecutor()
    _source = hebog_io.FitsImageSource(selected_input_path)
    _geometry = astrometry_algorithms.compact_geometry_at_pixel(
        source_metadata,
        (_width / 2.0, _height / 2.0),
    )

    _started = time.perf_counter()
    _detection = detection_stage.run_detection_stage(
        _source,
        _manifest,
        _detection_config,
        _executor,
        _sink,
    )
    _catalogue_stage_result = catalogue_stage.run_compact_catalogue_stage(
        _source,
        _detection,
        deblend_config=_deblend_config,
        moment_config=_moment_config,
        fit_config=_fit_config,
        catalogue_config=_catalogue_config,
        geometry=_geometry,
        metadata=source_metadata,
        executor=_executor,
        sink=_sink,
    )
    _completed = catalogue_algorithms.complete_compact_catalogue(
        catalogue_id=_run_id,
        metadata=source_metadata,
        shards=_catalogue_stage_result.records,
        deferred_island_ids=tuple(
            _item.island.island_id
            for _item in _catalogue_stage_result.deferred_islands
        ),
        config=_catalogue_config,
    )
    _compact_elapsed = time.perf_counter() - _started

    _multiscale_record = None
    if run_multiscale.value:
        _covariance_values = _geometry.restoring_beam_covariance_pixels_squared
        if _covariance_values is None:
            raise ValueError(
                "multiscale analysis requires a sampled restoring beam"
            )
        _beam_covariance = np.asarray(
            (
                (_covariance_values[0], _covariance_values[1]),
                (_covariance_values[1], _covariance_values[2]),
            ),
            dtype=np.float64,
        )
        _beam_eigenvalues, _beam_eigenvectors = np.linalg.eigh(
            _beam_covariance
        )
        _major_index = int(np.argmax(_beam_eigenvalues))
        _minor_index = 1 - _major_index
        _major_vector = _beam_eigenvectors[:, _major_index]
        _fwhm_per_sigma = 2.0 * np.sqrt(2.0 * np.log(2.0))
        _multiscale_beam = multiscale_algorithms.BeamShapePixels(
            major_fwhm_pixels=float(
                _fwhm_per_sigma * np.sqrt(_beam_eigenvalues[_major_index])
            ),
            minor_fwhm_pixels=float(
                _fwhm_per_sigma * np.sqrt(_beam_eigenvalues[_minor_index])
            ),
            position_angle_degrees=float(
                np.rad2deg(np.arctan2(_major_vector[1], _major_vector[0]))
                % 180.0
            ),
        )
        _multiscale_halo = phase_five_execution.scale_filter_halo_pixels(
            _multiscale_beam
        )
        _multiscale_manifest = partitioning_algorithms.plan_image_partitions(
            image_shape_yx=source_metadata.shape_yx,
            tile_core_shape_yx=_manifest.tile_core_shape_yx,
            halo_yx=(_multiscale_halo, _multiscale_halo),
        )
        _multiscale_sink = hebog_io.ZarrProductSink(
            _run_directory / "multiscale-products.zarr",
            _multiscale_manifest,
            generation_id=f"{_run_id}-multiscale",
        )
        _multiscale_started = time.perf_counter()
        _multiscale_result = multiscale_stage.run_phase_five_multiscale_stage(
            _source,
            _sink,
            _multiscale_manifest,
            config=multiscale_stage.PhaseFiveMultiscaleStageConfig(
                beam=_multiscale_beam,
                detection=(
                    hebog_config.ResidualMultiscaleDetectionConfig(
                        detection_threshold_sigma=float(
                            multiscale_detection_threshold.value
                        ),
                        island_threshold_sigma=float(
                            multiscale_island_threshold.value
                        ),
                        minimum_scale_support_fraction=float(
                            multiscale_support_fraction.value
                        ),
                        minimum_island_area_beams=float(
                            multiscale_minimum_area_beams.value
                        ),
                    )
                ),
                maximum_tiles_per_batch=int(multiscale_tiles_per_batch.value),
            ),
            executor=_executor,
            sink=_multiscale_sink,
        )
        _multiscale_record = {
            "result": _multiscale_result,
            "sink": _multiscale_sink,
            "beam": _multiscale_beam,
            "halo_pixels": _multiscale_halo,
            "wall_seconds": time.perf_counter() - _multiscale_started,
        }
    _elapsed = time.perf_counter() - _started

    _catalogue_path = _run_directory / "sources.fits"
    _catalogue_product = catalogue_adapter.write_rapthor_catalogue_fits(
        _catalogue_path,
        _completed.catalogue,
    )
    _catalogue_table = catalogue_adapter.read_rapthor_catalogue_fits(
        _catalogue_path
    )
    _configuration = {
        "schema_version": 1,
        "run_id": _run_id,
        "input": {
            "label": selected_input_label,
            "path": str(selected_input_path),
            "provenance": selected_input_provenance,
            "shape_yx": list(source_metadata.shape_yx),
            "unit": source_metadata.unit,
        },
        "execution": {
            "executor": "serial",
            "tile_core_shape_yx": list(_manifest.tile_core_shape_yx),
            "wall_seconds": _elapsed,
        },
        "detection": {
            "detection_threshold_sigma": float(detection_threshold.value),
            "island_threshold_sigma": float(island_threshold.value),
            "minimum_island_pixels": int(minimum_island_pixels.value),
        },
        "background_rms": {
            "coarse_window_shape_yx": [_coarse_y, _coarse_x],
            "coarse_step_yx": list(_coarse_step),
            "adaptive": bool(adaptive_rms.value),
            "adaptive_candidate_threshold_sigma": (
                float(adaptive_candidate_threshold.value)
                if adaptive_rms.value
                else None
            ),
            "adaptive_window_shape_yx": (
                [_fine_y, _fine_x] if adaptive_rms.value else None
            ),
        },
        "deblending": {
            "minimum_peak_separation_pixels": int(
                deblend_peak_separation.value
            ),
            "minimum_saddle_depth_sigma": float(deblend_saddle_depth.value),
        },
        "multiscale": {
            "enabled": bool(run_multiscale.value),
            "detection_threshold_sigma": float(
                multiscale_detection_threshold.value
            ),
            "island_threshold_sigma": float(multiscale_island_threshold.value),
            "minimum_scale_support_fraction": float(
                multiscale_support_fraction.value
            ),
            "minimum_island_area_beams": float(
                multiscale_minimum_area_beams.value
            ),
            "maximum_tiles_per_batch": int(multiscale_tiles_per_batch.value),
            "beam_shape_pixels": (
                {
                    "major_fwhm": (
                        _multiscale_record["beam"].major_fwhm_pixels
                    ),
                    "minor_fwhm": (
                        _multiscale_record["beam"].minor_fwhm_pixels
                    ),
                    "position_angle_degrees": (
                        _multiscale_record["beam"].position_angle_degrees
                    ),
                }
                if _multiscale_record is not None
                else None
            ),
            "halo_pixels": (
                _multiscale_record["halo_pixels"]
                if _multiscale_record is not None
                else None
            ),
        },
        "results": {
            "island_count": len(_detection.islands),
            "source_count": len(_completed.catalogue.sources),
            "gaussian_component_count": len(
                _completed.catalogue.gaussian_components
            ),
            "deferred_island_count": len(
                _catalogue_stage_result.deferred_islands
            ),
            "multiscale_detection_island_count": (
                len(_multiscale_record["result"].detection_islands)
                if _multiscale_record is not None
                else None
            ),
            "multiscale_reconstruction_island_count": (
                len(_multiscale_record["result"].reconstruction_islands)
                if _multiscale_record is not None
                else None
            ),
        },
    }
    _configuration_path = _run_directory / "configuration.json"
    _configuration_path.write_text(
        json.dumps(_configuration, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    hebog_run_record = {
        "run_id": _run_id,
        "directory": _run_directory,
        "sink": _sink,
        "detection": _detection,
        "stage": _catalogue_stage_result,
        "completed": _completed,
        "catalogue_path": _catalogue_product.path,
        "catalogue_table": _catalogue_table,
        "configuration": _configuration,
        "configuration_path": _configuration_path,
        "compact_wall_seconds": _compact_elapsed,
        "multiscale": _multiscale_record,
        "wall_seconds": _elapsed,
    }
    return (hebog_run_record,)


@app.cell
def _(hebog_run_record, mo):
    _catalogue = hebog_run_record["completed"].catalogue
    _stage = hebog_run_record["stage"]
    _multiscale = hebog_run_record["multiscale"]
    _multiscale_summary = (
        f"- **Multiscale detection islands:** "
        f"{len(_multiscale['result'].detection_islands)}\n"
        f"- **Multiscale reconstruction islands:** "
        f"{len(_multiscale['result'].reconstruction_islands)}\n"
        f"- **Multiscale wall time:** "
        f"{_multiscale['wall_seconds']:.3f} s\n"
        if _multiscale is not None
        else "- **Multiscale stage:** disabled\n"
    )
    mo.callout(
        mo.md(
            f"### Run complete: `{hebog_run_record['run_id']}`\n\n"
            f"- **Islands:** "
            f"{len(hebog_run_record['detection'].islands)}\n"
            f"- **Sources:** {len(_catalogue.sources)}\n"
            f"- **Gaussian components:** "
            f"{len(_catalogue.gaussian_components)}\n"
            f"- **Deferred islands:** {len(_stage.deferred_islands)}\n"
            f"{_multiscale_summary}"
            f"- **Wall time:** "
            f"{hebog_run_record['wall_seconds']:.3f} s\n"
            f"- **Output directory:** "
            f"`{hebog_run_record['directory']}`"
        ),
        kind="success",
    )
    return


@app.cell
def _(
    hebog_io,
    hebog_run_record,
    mo,
    np,
    plt,
    preview_bounds,
    preview_values,
    source_metadata,
):
    _sink = hebog_run_record["sink"]
    _background = _sink.read_completed_window("background", preview_bounds)
    _rms = _sink.read_completed_window("rms", preview_bounds)
    _mask = _sink.read_completed_window(
        "source-filtering-mask",
        preview_bounds,
    )
    _snr = np.full(preview_values.shape, np.nan, dtype=np.float64)
    np.divide(
        preview_values - _background,
        _rms,
        out=_snr,
        where=np.isfinite(_rms) & (_rms > 0),
    )

    _wcs = hebog_io.celestial_wcs_from_metadata(source_metadata)
    _table = hebog_run_record["catalogue_table"]
    if len(_table):
        _global_x, _global_y = _wcs.world_to_pixel_values(
            np.asarray(_table["RA"], dtype=np.float64),
            np.asarray(_table["DEC"], dtype=np.float64),
        )
        _local_x = _global_x - preview_bounds.x_start
        _local_y = _global_y - preview_bounds.y_start
        _visible = (
            (_local_x >= 0)
            & (_local_x < preview_values.shape[1])
            & (_local_y >= 0)
            & (_local_y < preview_values.shape[0])
        )
    else:
        _local_x = np.asarray(())
        _local_y = np.asarray(())
        _visible = np.asarray((), dtype=np.bool_)

    _finite_input = preview_values[np.isfinite(preview_values)]
    _input_limits = (
        np.percentile(_finite_input, (1.0, 99.7))
        if _finite_input.size
        else (0.0, 1.0)
    )
    _finite_rms = _rms[np.isfinite(_rms)]
    _rms_limits = (
        np.percentile(_finite_rms, (1.0, 99.0))
        if _finite_rms.size
        else (0.0, 1.0)
    )
    _figure, _axes = plt.subplots(2, 2, figsize=(13.0, 11.0))
    _input_artist = _axes[0, 0].imshow(
        preview_values,
        origin="lower",
        cmap="gray",
        vmin=_input_limits[0],
        vmax=_input_limits[1],
    )
    _axes[0, 0].scatter(
        _local_x[_visible],
        _local_y[_visible],
        s=52,
        facecolors="none",
        edgecolors="#f97316",
        linewidths=1.2,
    )
    _axes[0, 0].set_title("Input with catalogue positions")
    _figure.colorbar(
        _input_artist,
        ax=_axes[0, 0],
        label=source_metadata.unit,
        shrink=0.8,
    )
    _rms_artist = _axes[0, 1].imshow(
        _rms,
        origin="lower",
        cmap="cividis",
        vmin=_rms_limits[0],
        vmax=_rms_limits[1],
    )
    _axes[0, 1].set_title("Local RMS")
    _figure.colorbar(
        _rms_artist,
        ax=_axes[0, 1],
        label=source_metadata.unit,
        shrink=0.8,
    )
    _snr_artist = _axes[1, 0].imshow(
        _snr,
        origin="lower",
        cmap="RdBu_r",
        vmin=-6.0,
        vmax=10.0,
    )
    _axes[1, 0].set_title("Background-subtracted signal-to-noise")
    _figure.colorbar(
        _snr_artist,
        ax=_axes[1, 0],
        label="sigma",
        shrink=0.8,
    )
    _axes[1, 1].imshow(
        preview_values,
        origin="lower",
        cmap="gray",
        vmin=_input_limits[0],
        vmax=_input_limits[1],
    )
    _axes[1, 1].imshow(
        np.ma.masked_where(~_mask.astype(bool), _mask),
        origin="lower",
        cmap="autumn",
        alpha=0.55,
        vmin=0,
        vmax=1,
    )
    _axes[1, 1].set_title("Accepted source-island mask")
    for _axis in _axes.flat:
        _axis.set(xlabel="preview x pixel", ylabel="preview y pixel")
    _figure.suptitle(
        f"Hebog diagnostics: {hebog_run_record['run_id']}",
        y=0.995,
    )
    _figure.tight_layout()
    diagnostic_products = {
        "background": _background,
        "rms": _rms,
        "mask": _mask,
        "snr": _snr,
    }
    mo.vstack(
        [
            mo.md("## 4. Inspect the run"),
            _figure,
            mo.md(
                f"Orange ellipses mark catalogue entries inside this "
                f"preview. The mask contains "
                f"`{int(np.count_nonzero(_mask))}` accepted pixels."
            ),
        ]
    )
    return (diagnostic_products,)


@app.cell
def _(
    diagnostic_products,
    hebog_run_record,
    mo,
    np,
    plt,
    preview_bounds,
    preview_values,
):
    _multiscale = hebog_run_record["multiscale"]
    mo.stop(
        _multiscale is None,
        mo.callout(
            "Multiscale analysis was disabled for this run.",
            kind="info",
        ),
    )
    _sink = _multiscale["sink"]
    _combined_snr = _sink.read_completed_window(
        "combined-snr",
        preview_bounds,
    )
    _reconstructed_signal = _sink.read_completed_window(
        "reconstructed-signal",
        preview_bounds,
    )
    _position_signal = _sink.read_completed_window(
        "position-signal",
        preview_bounds,
    )
    _reconstruction_mask = np.asarray(
        _sink.read_completed_window("reconstruction-mask", preview_bounds),
        dtype=np.bool_,
    )
    _retained_mask = np.asarray(
        _sink.read_completed_window("retained-mask", preview_bounds),
        dtype=np.bool_,
    )
    _scale_masks = tuple(
        np.asarray(
            _sink.read_completed_window(
                f"scale-{_order}-significant",
                preview_bounds,
            ),
            dtype=np.bool_,
        )
        for _order in (1, 2, 3)
    )
    _rms = diagnostic_products["rms"]
    _reconstructed_snr = np.full(_rms.shape, np.nan, dtype=np.float64)
    _position_snr = np.full(_rms.shape, np.nan, dtype=np.float64)
    _valid_rms = np.isfinite(_rms) & (_rms > 0)
    np.divide(
        _reconstructed_signal,
        _rms,
        out=_reconstructed_snr,
        where=_valid_rms,
    )
    np.divide(
        _position_signal,
        _rms,
        out=_position_snr,
        where=_valid_rms,
    )

    _figure, _axes = plt.subplots(2, 2, figsize=(13.0, 10.5))
    _panels = (
        (diagnostic_products["snr"], "Original background-subtracted S/N"),
        (_combined_snr, "Maximum direct/matched/B3 seed evidence"),
        (_reconstructed_snr, "Persistent B3 reconstruction / RMS"),
        (_position_snr, "Regularized position signal / RMS"),
    )
    for _axis, (_values, _title) in zip(
        _axes.flat,
        _panels,
        strict=True,
    ):
        _artist = _axis.imshow(
            _values,
            origin="lower",
            cmap="RdBu_r",
            vmin=-5.0,
            vmax=10.0,
        )
        _axis.set(
            title=_title,
            xlabel="preview x pixel",
            ylabel="preview y pixel",
        )
        _figure.colorbar(_artist, ax=_axis, label="sigma", shrink=0.8)
    _figure.tight_layout()

    _scale_figure, _scale_axes = plt.subplots(1, 3, figsize=(14.0, 4.5))
    for _axis, _mask, _order in zip(
        _scale_axes,
        _scale_masks,
        (1, 2, 3),
        strict=True,
    ):
        _axis.imshow(_mask, origin="lower", cmap="binary", vmin=0, vmax=1)
        _axis.set(
            title=f"Significant B3 support: level {_order}",
            xlabel="preview x pixel",
            ylabel="preview y pixel",
        )
    _scale_figure.tight_layout()

    _support_figure, _support_axes = plt.subplots(1, 2, figsize=(11.0, 4.8))
    _support_axes[0].imshow(
        _reconstruction_mask,
        origin="lower",
        cmap="binary",
        vmin=0,
        vmax=1,
    )
    _support_axes[0].set_title("Adjacent-scale persistent support")
    _support_axes[1].imshow(preview_values, origin="lower", cmap="gray")
    _support_axes[1].imshow(
        np.ma.masked_where(~_retained_mask, _retained_mask),
        origin="lower",
        cmap="autumn",
        alpha=0.55,
        vmin=0,
        vmax=1,
    )
    _support_axes[1].set_title("Final retained support on input")
    for _axis in _support_axes:
        _axis.set(xlabel="preview x pixel", ylabel="preview y pixel")
    _support_figure.tight_layout()

    _result = _multiscale["result"]
    multiscale_diagnostic_products = {
        "combined_snr": _combined_snr,
        "reconstructed_snr": _reconstructed_snr,
        "position_snr": _position_snr,
        "reconstruction_mask": _reconstruction_mask,
        "retained_mask": _retained_mask,
        "scale_masks": _scale_masks,
    }
    mo.vstack(
        [
            mo.md("## 5. Multiscale support diagnostics"),
            mo.md(
                f"**Beam sampled at image centre:** "
                f"`{_multiscale['beam'].major_fwhm_pixels:.2f} x "
                f"{_multiscale['beam'].minor_fwhm_pixels:.2f} pixels` · "
                f"**filter halo:** `{_multiscale['halo_pixels']} px` · "
                f"**detection islands:** "
                f"`{len(_result.detection_islands)}` · "
                f"**persistent reconstruction islands:** "
                f"`{len(_result.reconstruction_islands)}`"
            ),
            _figure,
            mo.md("### Significant support at each B3 level"),
            _scale_figure,
            mo.md("### Persistent and retained original-pixel support"),
            _support_figure,
            mo.callout(
                mo.md(
                    "Broad emission that is weak in direct S/N but coherent "
                    "in combined evidence, present on adjacent B3 levels, "
                    "and retained in the final mask is a plausible "
                    "multiscale detection. Inspect artifacts and a proper "
                    "model/residual before treating it as astrophysical."
                ),
                kind="info",
            ),
        ]
    )
    return (multiscale_diagnostic_products,)


@app.cell
def _(
    diagnostic_products,
    hebog_run_record,
    mo,
    np,
    plt,
    preview_bounds,
    selected_input_label,
    selected_truth_model,
):
    if selected_truth_model is not None:
        _local_y, _local_x = np.indices(
            diagnostic_products["mask"].shape,
            dtype=np.float64,
        )
        _global_x = _local_x + preview_bounds.x_start
        _global_y = _local_y + preview_bounds.y_start
        _injected_sources = selected_truth_model["sources"]
        _injected_signal = np.zeros_like(_global_x)
        for _x0, _y0, _peak, _sigma_x, _sigma_y in _injected_sources:
            _injected_signal += _peak * np.exp(
                -0.5
                * (
                    ((_global_x - _x0) / _sigma_x) ** 2
                    + ((_global_y - _y0) / _sigma_y) ** 2
                )
            )
        _island_sigma = hebog_run_record["configuration"]["detection"][
            "island_threshold_sigma"
        ]
        _truth_rms = selected_truth_model["noise_rms_base"] * (
            selected_truth_model["noise_rms_intercept"]
            + selected_truth_model["noise_rms_x_slope"]
            * _global_x
            / (selected_truth_model["image_width"] - 1)
        )
        _reference_mask = _injected_signal >= _island_sigma * _truth_rms
        _hebog_mask = diagnostic_products["mask"].astype(bool)
        _agreement = _reference_mask & _hebog_mask
        _extra = ~_reference_mask & _hebog_mask
        _missed = _reference_mask & ~_hebog_mask
        _union = _reference_mask | _hebog_mask
        _intersection_over_union = (
            np.count_nonzero(_agreement) / np.count_nonzero(_union)
            if np.any(_union)
            else 1.0
        )
        _comparison_rgb = np.empty((*_reference_mask.shape, 3))
        _comparison_rgb[:] = (0.08, 0.10, 0.12)
        _comparison_rgb[_agreement] = (0.16, 0.75, 0.45)
        _comparison_rgb[_extra] = (0.95, 0.45, 0.10)
        _comparison_rgb[_missed] = (0.25, 0.55, 0.95)

        _figure, _axes = plt.subplots(1, 3, figsize=(14.0, 4.8))
        _axes[0].imshow(_reference_mask, origin="lower", cmap="gray_r")
        _axes[0].set_title("Analytic injected-source support")
        _axes[1].imshow(_hebog_mask, origin="lower", cmap="gray_r")
        _axes[1].set_title("Hebog accepted mask")
        _axes[2].imshow(_comparison_rgb, origin="lower")
        _axes[2].set_title("Green: agreement | Orange: extra | Blue: missed")
        for _axis in _axes:
            _axis.set(xlabel="preview x pixel", ylabel="preview y pixel")
        _figure.tight_layout()
        _mask_quality_view = mo.vstack(
            [
                mo.md(
                    f"### Synthetic reference-mask comparison: "
                    f"{selected_input_label}"
                ),
                _figure,
                mo.md(
                    f"**Injected sources:** "
                    f"`{len(_injected_sources)}` · "
                    f"**fitted catalogue sources:** "
                    f"`{len(hebog_run_record['completed'].catalogue.sources)}`"
                    f" · "
                    f"**Pixel intersection over union:** "
                    f"`{_intersection_over_union:.3f}` · "
                    f"**extra pixels:** `{np.count_nonzero(_extra)}` · "
                    f"**missed pixels:** `{np.count_nonzero(_missed)}`\n\n"
                    "The analytic panel contains only injected Gaussian "
                    f"emission above the run's `{_island_sigma:g}` sigma "
                    "island threshold. It deliberately excludes "
                    f"{selected_truth_model['excluded_features']}. "
                    "This makes it a tuning aid, not a survey-quality truth "
                    "mask: noise can move boundary pixels across threshold. "
                    "Raw source-count agreement is not completeness because "
                    "blends and false positives can cancel missed sources."
                ),
            ]
        )
    elif selected_input_label == "LoTSS DR2 3C 295 field":
        _mask_quality_view = mo.callout(
            mo.md(r"""
            ### What to look for in the 3C 295 mask

            There is no pixel-level public truth mask in this notebook. Treat
            the image/mask overlay above as the side-by-side review:

            - the bright compact source should have one coherent central mask;
            - credible isolated field sources should have compact footprints;
            - rings, spokes, or repeated sidelobe structures around 3C 295
              should not turn into chains of accepted islands;
            - reducing the RMS window should make the RMS map follow real
              artifact scales, not carve holes into the source core.

            Catalogue positions are useful corroboration, but they do not
            define the correct pixel boundary for this particular image.
            """),
            kind="info",
        )
    elif selected_input_label == "LoTSS DR2 representative survey field":
        _mask_quality_view = mo.callout(
            mo.md(r"""
            ### What to inspect in the representative LoTSS survey field

            Select the **1024 px** preview to see most or all of this cutout.
            It should contain roughly 100 DR2 catalogue sources on average,
            but that estimate is not a truth count for this particular image.

            - inspect whether compact masks remain sensible across quiet and
              higher-RMS parts of the field;
            - look for source-count changes when moving the seed threshold by
              0.25 sigma;
            - check close pairs and multi-component islands separately from
              isolated sources;
            - compare positions and flux densities with the official LoTSS
              DR2 source and Gaussian catalogues;
            - measure completeness and reliability after matching, rather
              than using `Hebog count / 100` as a completeness estimate.
            """),
            kind="info",
        )
    elif selected_input_label == "LoTSS DR2 M51 field":
        _mask_quality_view = mo.callout(
            mo.md(r"""
            ### What to look for in the M51 mask

            M51 is intentionally a stress case for the compact path. Compact
            peaks and unrelated field sources may be masked sensibly while the
            galaxy's disk and arms are fragmented or incomplete. Compare that
            mask with the multiscale combined evidence, adjacent-level B3
            support, and final retained mask below. A scientifically useful
            diffuse result still needs model/residual inspection; it should not
            be manufactured by repeatedly lowering the compact island
            threshold until noise and neighboring sources merge.
            """),
            kind="warn",
        )
    else:
        _mask_quality_view = mo.callout(
            mo.md(r"""
            ### What a plausible compact-source mask looks like

            Look for coherent footprints around credible emission, few
            isolated noise pixels, no repeated sidelobe pattern around bright
            sources, and no mask in invalid regions. For a defensible reference,
            inject sources into representative residual data and compare with
            their known support; an external source catalogue supplies useful
            positions but not pixel-level mask truth.
            """),
            kind="info",
        )
    _mask_quality_view  # noqa: B018
    return


@app.cell
def _(hebog_run_record, mo):
    _table = hebog_run_record["catalogue_table"]
    _rows = [
        {
            "source_id": int(_row["Source_id"]),
            "ra_deg": float(_row["RA"]),
            "dec_deg": float(_row["DEC"]),
            "island_flux_jy": float(_row["Isl_Total_flux"]),
            "total_flux_jy": float(_row["Total_flux"]),
            "deconvolved_major_deg": float(_row["DC_Maj"]),
            "ra_error_deg": float(_row["E_RA"]),
            "dec_error_deg": float(_row["E_DEC"]),
        }
        for _row in _table
    ]
    catalogue_browser = mo.ui.table(
        _rows,
        selection=None,
        page_size=15,
    )
    mo.vstack(
        [
            mo.md("### Catalogue"),
            catalogue_browser,
            mo.md(
                f"The complete FITS catalogue is at "
                f"`{hebog_run_record['catalogue_path']}`. `DC_Maj = 0` "
                "means unresolved in this Rapthor-compatible view."
            ),
        ]
    )
    return (catalogue_browser,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Reading the diagnostics and deciding what to change

    Use comparisons, not a single attractive-looking overlay. Re-run into a
    new output directory after each change and keep the configuration JSON.

    **Too many detections around a bright source**

    Check whether the RMS panel rises on the same spatial scale as the
    sidelobes or calibration artifacts. Enable adaptive RMS, lower its
    bright-candidate threshold, or reduce the coarse/fine window scale. Raise
    the global detection threshold only if the false positives are widespread,
    because that also reduces completeness in quiet regions.

    **Faint real sources are missing**

    First check that the RMS is not biased upward by emission or an over-small
    window. Then lower the detection threshold in 0.25 sigma steps. Quantify
    the cost with injected-source recovery and a false-detection estimate; a
    negative-image run is a useful empirical reliability diagnostic when the
    image statistics are sufficiently symmetric.

    **Flux is missing from source wings**

    Lower the island threshold while leaving the seed threshold fixed. If
    unrelated neighbors become connected, restore the threshold and revisit
    deblending. An island threshold that is too high fragments emission and
    biases integrated flux low.

    **A double source is merged, or one source is split**

    For a merged pair, reduce minimum peak separation and/or saddle depth. For
    over-splitting, increase them. Inspect the source/component/island counts
    together; component grouping is not the same as associating radio lobes
    and cores into one astrophysical object.

    **The RMS map follows diffuse emission**

    Increase the RMS window and compare quiet regions. If extended emission
    occupies much of the field, compact-source background estimation may not
    be scientifically appropriate. Use a reviewed multiscale/diffuse workflow
    and inspect a model and residual before publishing fluxes.

    **Commissioning checks after a plausible run**

    Cross-match bright, isolated components against a trusted survey. Plot RA
    and Dec offsets across the field, measured/reference flux ratio versus
    position and SNR, local RMS versus radius, source density, and integrated
    to peak flux ratio. These expose astrometric distortion, flux-scale error,
    smearing, primary-beam problems, and dynamic-range limitations that source
    count alone cannot diagnose.

    **A field with tens to hundreds of sources**

    Do not rely on visual inspection source by source. Bin injected or
    reference-matched sources by SNR, size, distance from the field centre,
    and local RMS. Compare completeness, reliability, flux recovery,
    astrometric offsets, blends, source density, and runtime. The offline
    100-source field provides known injections for this population-level loop.
    """)
    return


@app.cell
def _(hebog_run_record, json, mo):
    _configuration_text = json.dumps(
        hebog_run_record["configuration"],
        indent=2,
        sort_keys=True,
    )
    mo.vstack(
        [
            mo.md("## Reproducibility record"),
            mo.md(
                f"Saved to `{hebog_run_record['configuration_path']}`. "
                "Record the Hebog revision and observing/image-production "
                "provenance alongside this file for scientific use."
            ),
            mo.accordion(
                {
                    "Show configuration JSON": mo.md(
                        f"```json\n{_configuration_text}\n```"
                    )
                }
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Scope and limitations

    - Input must have one two-dimensional logical radio image plane. Singleton
      Stokes/frequency axes are accepted; non-singleton cubes need an explicit
      plane-selection step before this notebook.
    - FITS metadata must include a celestial WCS, `BUNIT`, `BMAJ`, `BMIN`,
      `BPA`, and a reference frequency. Hebog does not invent missing physical
      metadata.
    - The notebook runs the serial compact and optional multiscale-support
      paths. Tiling bounds memory, but a large commissioning mosaic can take
      time. Production scale-out should use Hebog through the workflow-owned
      Dask executor rather than starting a private cluster here.
    - The catalogue is not primary-beam corrected and is not automatically
      cross-matched, classified, or associated into host galaxies.
    - Forced photometry, time-domain cross-matching, completeness
      injection, and a materialized compact model/residual image are not part
      of this workbench.
    - **Hebog supports bounded multiscale/diffuse processing.** When enabled,
      this workbench runs its matched-filter scale responses, B3 a trous
      support, tile-boundary reconciliation, and retained-support publication.
      The workbench does not yet compose compact-model subtraction, cross-scale
      association, extended-emission measurement, and a combined catalogue;
      those implemented pieces are not exposed behind one public call yet.
      Their detailed staged demonstration remains in
      `notebooks/source_finder_demo.py`.
    - M51 is included to expose the limits of a compact Gaussian catalogue on
      complex emission. Do not interpret this workbench's M51 catalogue as a
      validated diffuse-emission measurement.

    If a LoTSS cutout contributes to science, follow the [LoTSS data-release
    citation and credit guidance](https://lofar-surveys.org/cutout_api_details.html).
    The 3C 295 and M51 URLs request public DR2 cutouts but do not redistribute
    those FITS files in this repository.
    """)
    return


if __name__ == "__main__":
    app.run()
