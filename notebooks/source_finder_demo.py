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
    # Hebog staged source-finding demonstration

    This notebook runs the qualified compact-source path from **Phase 4** and
    the implemented multiscale scientific kernels from **Phase 5** on small,
    deterministic synthetic radio images. The compact path estimates
    background and RMS noise, detects connected source islands, reconciles an
    island that crosses tile boundaries, deblends compact peaks, calculates
    exact-label moments, fits Gaussian components, transforms them to sky
    coordinates, deconvolves the beam, and builds a Rapthor-compatible
    catalogue. A separate residual example shows how the Phase 5 matched-filter
    seed aid and residual B3 à trous representation recover extended emission
    whose brightest original pixel is below the direct detection threshold.

    The example uses Hebog's window-readable synthetic source and serial
    executor so it is quick and completely redistributable. Production inputs
    use the same stage boundaries with FITS and can supply an existing Dask
    executor.
    """)
    return


@app.cell
def _():
    import pathlib
    import tempfile

    import astropy.wcs as astropy_wcs
    import matplotlib.patches as mpl_patches
    import matplotlib.pyplot as plt
    import numpy as np
    from scipy import ndimage

    import hebog.adapters.rapthor_catalogue as rapthor_catalogue_adapter
    import hebog.algorithms.astrometry as astrometry_algorithms
    import hebog.algorithms.catalogue as catalogue_algorithms
    import hebog.algorithms.multiscale as multiscale_algorithms
    import hebog.algorithms.partitioning as partitioning_algorithms
    import hebog.config as hebog_config
    import hebog.data_models as hebog_models
    import hebog.data_models.measurement as measurement_models
    import hebog.executors as hebog_executors
    import hebog.io as hebog_io
    import hebog.stages.catalogue as catalogue_stage
    import hebog.stages.deblending as deblending_stage
    import hebog.stages.detection as detection_stage
    import hebog.stages.measurement as measurement_stage
    import hebog.validation.datasets as validation_datasets

    return (
        astrometry_algorithms,
        astropy_wcs,
        catalogue_algorithms,
        catalogue_stage,
        deblending_stage,
        detection_stage,
        hebog_config,
        hebog_executors,
        hebog_io,
        hebog_models,
        measurement_models,
        measurement_stage,
        mpl_patches,
        multiscale_algorithms,
        ndimage,
        np,
        partitioning_algorithms,
        pathlib,
        plt,
        rapthor_catalogue_adapter,
        tempfile,
        validation_datasets,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 1. A governed synthetic radio image

    The checked-in development recipe contains Gaussian noise, a negative
    background, threshold-crossing sources, blends, and an image-edge source.
    This visual variant keeps five high-confidence interior sources and
    replaces the close pair with two equal compact sources fifteen pixels apart
    across a four-tile corner. That keeps every admitted region eligible for a
    complete catalogue while making reconciliation and deblending easy to see;
    no governed regression or qualification recipe is changed. Noise is
    generated from global pixel coordinates, so reading the image in different
    windows always produces exactly the same pixels.
    """)
    return


@app.cell
def _(
    hebog_io,
    hebog_models,
    np,
    pathlib,
    validation_datasets,
):
    project_root = pathlib.Path(__file__).resolve().parents[1]
    development_manifest = validation_datasets.load_dataset_manifest(
        project_root / "config/datasets/phase-3-development.json"
    )
    demonstration_dataset = development_manifest.datasets[0]
    _demonstration_sources = list(demonstration_dataset.recipe.sources)
    _pair_update = {
        "y_pixel": 96.0,
        "peak_flux_jy_per_beam": 0.005,
        "major_sigma_pixels": 2.5,
        "minor_sigma_pixels": 1.7,
        "rotation_degrees_counterclockwise_from_x": 0.0,
    }
    _demonstration_sources[4] = _demonstration_sources[4].model_copy(
        update={**_pair_update, "x_pixel": 88.5}
    )
    _demonstration_sources[5] = _demonstration_sources[5].model_copy(
        update={**_pair_update, "x_pixel": 103.5}
    )
    _demonstration_sources = [
        source.model_copy(
            update={
                "peak_flux_jy_per_beam": max(
                    source.peak_flux_jy_per_beam,
                    0.002,
                )
            }
        )
        for source in _demonstration_sources[2:7]
    ]
    demonstration_recipe = demonstration_dataset.recipe.model_copy(
        update={"sources": tuple(_demonstration_sources)}
    )
    input_image = validation_datasets.generate_synthetic_image(
        demonstration_recipe
    )

    class SyntheticWindowSource:
        """Read deterministic bounded windows from one synthetic recipe."""

        def __init__(self, recipe):
            self._recipe = recipe

        def read_window(self, bounds):
            values = validation_datasets.generate_synthetic_window(
                self._recipe,
                y_start=bounds.y_start,
                y_stop=bounds.y_stop,
                x_start=bounds.x_start,
                x_stop=bounds.x_stop,
            )
            return hebog_io.ImageWindow(
                bounds=bounds,
                values=values,
                valid_pixels=np.isfinite(values),
            )

        def read_windows(self, bounds_collection):
            return tuple(
                self.read_window(bounds) for bounds in bounds_collection
            )

    image_source = SyntheticWindowSource(demonstration_recipe)
    full_image_bounds = hebog_models.ImageBounds(
        0,
        demonstration_recipe.shape_yx[0],
        0,
        demonstration_recipe.shape_yx[1],
    )
    return (
        demonstration_dataset,
        demonstration_recipe,
        full_image_bounds,
        image_source,
        input_image,
    )


@app.cell
def _(demonstration_dataset, demonstration_recipe, input_image, mo, np, plt):
    _minimum, _maximum = np.percentile(input_image, (1.0, 99.8))
    _figure, _axis = plt.subplots(figsize=(7.0, 5.5))
    _image_artist = _axis.imshow(
        input_image,
        origin="lower",
        cmap="gray",
        vmin=_minimum,
        vmax=_maximum,
    )
    _axis.set(
        title=f"Synthetic input: {demonstration_dataset.identifier}",
        xlabel="x pixel",
        ylabel="y pixel",
    )
    _figure.colorbar(
        _image_artist,
        ax=_axis,
        label="Brightness (Jy/beam)",
        shrink=0.82,
    )
    _figure.tight_layout()
    mo.vstack(
        [
            mo.md(
                f"**Shape:** `{input_image.shape[0]} x "
                f"{input_image.shape[1]}` pixels · "
                f"**Known analytic sources:** "
                f"`{len(demonstration_recipe.sources)}`"
            ),
            _figure,
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 2. Run the bounded compact stages

    The scientific thresholds are explicit: an island includes pixels at or
    above 3 sigma and must contain a seed strictly above 5 sigma. The
    six-pixel minimum suppresses isolated noise pixels. A high-significance
    scan at 50 sigma requests a finer local RMS grid near a bright source. For
    this visual example, compact peaks at least one pixel apart remain
    separate when the weaker peak is at least 0.5 sigma above their saddle.

    We execute the same image twice:

    1. as one 192 x 192 tile; and
    2. as four 96 x 96 tiles, placing the close central blend at a four-tile
       corner.
    """)
    return


@app.cell
def _(
    astrometry_algorithms,
    astropy_wcs,
    demonstration_dataset,
    detection_stage,
    hebog_config,
    hebog_models,
    np,
):
    rms_statistics = hebog_config.RmsWindowStatisticsConfig(
        clipping_sigma=3.0,
        maximum_iterations=10,
        minimum_samples=6,
    )
    detection_configuration = detection_stage.DetectionStageConfig(
        background_rms=hebog_config.BackgroundRmsConfig(
            coarse=hebog_config.RmsGridConfig(
                window_shape_yx=(150, 150),
                step_yx=(50, 50),
                statistics=rms_statistics,
                maximum_batch_cells=32,
            ),
            adaptive=hebog_config.AdaptiveRmsConfig(
                grid=hebog_config.RmsGridConfig(
                    window_shape_yx=(35, 35),
                    step_yx=(7, 7),
                    statistics=rms_statistics,
                    maximum_batch_cells=32,
                ),
                candidate_threshold_sigma=50.0,
                influence_radius_pixels=75.0,
                transition_width_pixels=20.0,
            ),
            maximum_spatial_window_fraction=0.25,
            maximum_constant_map_pixels=2048 * 2048,
        ),
        source_finder=hebog_config.SourceFinderConfig(
            detection_threshold_sigma=5.0,
            island_threshold_sigma=3.0,
            minimum_island_pixels=7,
        ),
    )
    deblend_configuration = hebog_config.CompactDeblendConfig(
        minimum_peak_signal_to_noise=5.0,
        minimum_peak_separation_pixels=1,
        minimum_saddle_depth_sigma=0.5,
        minimum_region_pixels=7,
        maximum_compact_island_pixels=250_000,
        maximum_compact_bounds_pixels=1_000_000,
        target_batch_pixels=250_000,
        maximum_batch_pixels=4_000_000,
    )
    moment_configuration = hebog_config.CompactMomentConfig(
        minimum_shape_pixels=3,
        covariance_relative_tolerance=1e-12,
    )
    fit_configuration = hebog_config.CompactGaussianFitConfig(
        minimum_fit_pixels=7,
        maximum_function_evaluations=300,
        minimum_sigma_pixels=0.2,
        maximum_sigma_pixels=30.0,
        maximum_amplitude_factor=5.0,
        center_margin_pixels=1.0,
        convergence_tolerance=1e-8,
        maximum_axis_ratio=30.0,
    )
    catalogue_configuration = hebog_config.CompactCatalogueConfig(
        maximum_catalogue_records=10_000,
        deconvolution_relative_tolerance=1e-10,
        extension_significance_sigma=5.0,
    )
    _pixel_scales_degrees = demonstration_dataset.wcs.pixel_scale_degrees_xy
    _reference_x, _reference_y = demonstration_dataset.wcs.reference_pixel_xy
    _sky_ra, _sky_dec = demonstration_dataset.wcs.reference_sky_degrees
    _rotation = np.deg2rad(
        demonstration_dataset.wcs.rotation_degrees_counterclockwise
    )
    _celestial_wcs = astropy_wcs.WCS(naxis=2)
    _celestial_wcs.wcs.ctype = ["RA---SIN", "DEC--SIN"]
    _celestial_wcs.wcs.cunit = ["deg", "deg"]
    _celestial_wcs.wcs.crpix = [_reference_x + 1.0, _reference_y + 1.0]
    _celestial_wcs.wcs.crval = [_sky_ra, _sky_dec]
    _celestial_wcs.wcs.cd = [
        [
            _pixel_scales_degrees[0] * np.cos(_rotation),
            -_pixel_scales_degrees[1] * np.sin(_rotation),
        ],
        [
            _pixel_scales_degrees[0] * np.sin(_rotation),
            _pixel_scales_degrees[1] * np.cos(_rotation),
        ],
    ]
    _beam = demonstration_dataset.beam
    image_metadata = hebog_models.ImageMetadata(
        shape_yx=demonstration_dataset.recipe.shape_yx,
        unit="Jy/beam",
        beam=hebog_models.RestoringBeam(
            major_fwhm_degrees=(
                _beam.major_fwhm_pixels * abs(_pixel_scales_degrees[0])
            ),
            minor_fwhm_degrees=(
                _beam.minor_fwhm_pixels * abs(_pixel_scales_degrees[1])
            ),
            position_angle_degrees=_beam.position_angle_degrees,
        ),
        celestial_wcs=hebog_models.CelestialWcs(
            fits_header=_celestial_wcs.to_header().tostring(
                sep="\n",
                endcard=False,
                padding=False,
            ),
            coordinate_frame="icrs",
        ),
        reference_frequency_hz=150_000_000.0,
    )
    measurement_geometry = astrometry_algorithms.compact_geometry_at_pixel(
        image_metadata,
        (
            demonstration_dataset.recipe.shape_yx[1] / 2.0,
            demonstration_dataset.recipe.shape_yx[0] / 2.0,
        ),
    )
    return (
        catalogue_configuration,
        deblend_configuration,
        detection_configuration,
        fit_configuration,
        image_metadata,
        measurement_geometry,
        moment_configuration,
    )


@app.cell
def _(
    catalogue_algorithms,
    catalogue_configuration,
    catalogue_stage,
    deblend_configuration,
    deblending_stage,
    demonstration_recipe,
    detection_configuration,
    detection_stage,
    hebog_executors,
    hebog_io,
    image_source,
    fit_configuration,
    image_metadata,
    measurement_geometry,
    measurement_stage,
    moment_configuration,
    partitioning_algorithms,
    pathlib,
    tempfile,
):
    demonstration_workspace = tempfile.TemporaryDirectory(
        prefix="hebog-marimo-"
    )

    def execute_detection(tile_shape_yx, run_name):
        manifest = partitioning_algorithms.plan_image_partitions(
            image_shape_yx=demonstration_recipe.shape_yx,
            tile_core_shape_yx=tile_shape_yx,
            halo_yx=(0, 0),
        )
        sink = hebog_io.ZarrProductSink(
            pathlib.Path(demonstration_workspace.name) / f"{run_name}.zarr",
            manifest,
            generation_id=f"marimo-{run_name}",
        )
        executor = hebog_executors.SerialExecutor()
        detection = detection_stage.run_detection_stage(
            image_source,
            manifest,
            detection_configuration,
            executor,
            sink,
        )
        deblending = deblending_stage.run_compact_deblend_stage(
            image_source,
            detection,
            deblend_configuration,
            executor,
            sink,
        )
        moments = measurement_stage.run_compact_moment_stage(
            image_source,
            detection,
            deblend_configuration,
            moment_configuration,
            measurement_geometry,
            executor=executor,
            sink=sink,
        )
        catalogue_shards = catalogue_stage.run_compact_catalogue_stage(
            image_source,
            detection,
            deblend_config=deblend_configuration,
            moment_config=moment_configuration,
            fit_config=fit_configuration,
            catalogue_config=catalogue_configuration,
            geometry=measurement_geometry,
            metadata=image_metadata,
            executor=executor,
            sink=sink,
        )
        completed_catalogue = catalogue_algorithms.complete_compact_catalogue(
            catalogue_id="marimo-compact-demo",
            metadata=image_metadata,
            shards=catalogue_shards.records,
            deferred_island_ids=tuple(
                item.island.island_id
                for item in catalogue_shards.deferred_islands
            ),
            config=catalogue_configuration,
        )
        return (
            detection,
            deblending,
            moments,
            catalogue_shards,
            completed_catalogue,
            sink,
        )

    (
        one_tile_detection,
        one_tile_deblending,
        one_tile_moments,
        one_tile_catalogue_shards,
        one_tile_catalogue,
        one_tile_sink,
    ) = execute_detection(
        demonstration_recipe.shape_yx,
        "one-tile",
    )
    (
        tiled_detection,
        tiled_deblending,
        tiled_moments,
        tiled_catalogue_shards,
        tiled_catalogue,
        tiled_sink,
    ) = execute_detection(
        (96, 96),
        "four-tiles",
    )
    return (
        demonstration_workspace,
        one_tile_deblending,
        one_tile_detection,
        one_tile_moments,
        one_tile_catalogue,
        one_tile_catalogue_shards,
        one_tile_sink,
        tiled_deblending,
        tiled_detection,
        tiled_moments,
        tiled_catalogue,
        tiled_catalogue_shards,
        tiled_sink,
    )


@app.cell
def _(
    full_image_bounds,
    one_tile_sink,
    tiled_sink,
):
    background_plane = tiled_sink.read_completed_window(
        "background",
        full_image_bounds,
    )
    rms_plane = tiled_sink.read_completed_window("rms", full_image_bounds)
    source_filtering_mask = tiled_sink.read_completed_window(
        "source-filtering-mask",
        full_image_bounds,
    )
    one_tile_background = one_tile_sink.read_completed_window(
        "background",
        full_image_bounds,
    )
    one_tile_rms = one_tile_sink.read_completed_window(
        "rms",
        full_image_bounds,
    )
    one_tile_mask = one_tile_sink.read_completed_window(
        "source-filtering-mask",
        full_image_bounds,
    )
    return (
        background_plane,
        one_tile_background,
        one_tile_mask,
        one_tile_rms,
        rms_plane,
        source_filtering_mask,
    )


@app.cell(hide_code=True)
def _(
    background_plane,
    input_image,
    mo,
    np,
    plt,
    rms_plane,
    source_filtering_mask,
):
    _figure, _axes = plt.subplots(
        1, 4, figsize=(16.0, 4.0), constrained_layout=True
    )
    _minimum, _maximum = np.percentile(input_image, (1.0, 99.8))
    _panels = (
        (input_image, "Input", "gray", _minimum, _maximum),
        (background_plane, "Estimated background", "coolwarm", None, None),
        (rms_plane, "Estimated RMS", "viridis", None, None),
        (source_filtering_mask, "Accepted source mask", "gray_r", 0, 1),
    )
    for _axis, (_values, _title, _cmap, _vmin, _vmax) in zip(
        _axes,
        _panels,
        strict=True,
    ):
        _artist = _axis.imshow(
            _values,
            origin="lower",
            cmap=_cmap,
            vmin=_vmin,
            vmax=_vmax,
        )
        _axis.set(title=_title, xlabel="x pixel")
        _figure.colorbar(_artist, ax=_axis, shrink=0.72)
    _axes[0].set_ylabel("y pixel")
    mo.vstack(
        [
            mo.md("## 3. Background, noise, and accepted emission"),
            _figure,
        ]
    )
    return


@app.cell
def _(ndimage, np, source_filtering_mask, tiled_deblending):
    island_label_plane, visual_island_count = ndimage.label(
        source_filtering_mask,
        structure=np.ones((3, 3), dtype=np.bool_),
    )
    region_rows = tuple(
        {
            "island": summary.island_id,
            "status": summary.status,
            "region": region.region_id,
            "pixels": region.pixel_count,
            "peak S/N": round(region.peak_signal_to_noise, 2),
            "peak (y, x)": str(region.peak_position_yx),
        }
        for summary in tiled_deblending.islands
        for region in summary.regions
    )
    return island_label_plane, region_rows, visual_island_count


@app.cell(hide_code=True)
def _(
    input_image,
    island_label_plane,
    mpl_patches,
    mo,
    np,
    plt,
    region_rows,
    tiled_deblending,
    tiled_detection,
    visual_island_count,
):
    _figure, (_label_axis, _region_axis) = plt.subplots(
        1,
        2,
        figsize=(12.0, 5.5),
        constrained_layout=True,
    )
    _label_axis.imshow(island_label_plane, origin="lower", cmap="tab20")
    _label_axis.set(
        title="Eight-connected detected islands",
        xlabel="x pixel",
        ylabel="y pixel",
    )
    _minimum, _maximum = np.percentile(input_image, (1.0, 99.8))
    _region_axis.imshow(
        input_image,
        origin="lower",
        cmap="gray",
        vmin=_minimum,
        vmax=_maximum,
    )
    _colours = plt.colormaps["tab10"]
    for _region_index, _row in enumerate(region_rows):
        _summary = next(
            item
            for item in tiled_deblending.islands
            if item.island_id == _row["island"]
        )
        _region = next(
            item
            for item in _summary.regions
            if item.region_id == _row["region"]
        )
        _bounds = _region.bounds
        _colour = _colours(_region_index % 10)
        _region_axis.add_patch(
            mpl_patches.Rectangle(
                (_bounds.x_start, _bounds.y_start),
                _bounds.x_stop - _bounds.x_start,
                _bounds.y_stop - _bounds.y_start,
                fill=False,
                edgecolor=_colour,
                linewidth=1.8,
            )
        )
        _region_axis.plot(
            _region.peak_position_yx[1],
            _region.peak_position_yx[0],
            marker="+",
            color=_colour,
            markersize=8,
        )
    _region_axis.set(
        title="Compact deblended region bounds and peaks",
        xlabel="x pixel",
        ylabel="y pixel",
    )
    _statistics = mo.hstack(
        [
            mo.stat(
                label="Detected islands",
                value=str(len(tiled_detection.islands)),
            ),
            mo.stat(
                label="Visual label count",
                value=str(visual_island_count),
            ),
            mo.stat(label="Deblended regions", value=str(len(region_rows))),
            mo.stat(
                label="Deferred islands",
                value=str(len(tiled_deblending.deferred_islands)),
            ),
        ],
        widths="equal",
    )
    mo.vstack(
        [
            mo.md("## 4. Connected islands and compact deblending"),
            _statistics,
            _figure,
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo, region_rows):
    _header = "| Island | Result | Region | Pixels | Peak S/N | Peak (y, x) |"
    _separator = "| --- | --- | --- | ---: | ---: | --- |"
    _rows = "\n".join(
        "| {island} | {status} | {region} | {pixels} | {peak S/N:.2f} | "
        "{peak (y, x)} |".format(**row)
        for row in region_rows
    )
    mo.md(f"""
    ### Compact deblending summaries

    The executor returns these bounded summaries—not per-pixel label arrays—to
    keep scheduler payloads small. The rectangles in the plot are read and
    planning bounds, not membership masks: rectangles may overlap or contain
    pixels assigned to another watershed region. Phase 4 measurement uses the
    worker-local region processor, which sees the exact labels before reducing
    them to compact records.

    {_header}
    {_separator}
    {_rows}
    """)
    return


@app.cell(hide_code=True)
def _(measurement_models, mo, tiled_moments):
    _region_measurements = tuple(
        record
        for record in tiled_moments.records
        if record.target.object_kind == "deblended-region"
    )
    _header = (
        "| Region | Moment shape | Peak (mJy/beam) | "
        "Owned-pixel flux (mJy) | Centroid (x, y) |"
    )

    def _row(record):
        if isinstance(record, measurement_models.UnavailableMomentMeasurement):
            _status = f"unavailable: {record.reason}"
            return f"| {record.target.object_id} | {_status} | — | — | — |"
        _photometry = record.photometry
        if isinstance(record, measurement_models.ValidMomentMeasurement):
            _shape = (
                f"{record.initializer.major_sigma_pixels:.2f} x "
                f"{record.initializer.minor_sigma_pixels:.2f} px at "
                f"{record.initializer.major_axis_angle_degrees:.1f}°"
            )
            _centroid = (
                f"({record.initializer.centroid_xy[0]:.2f}, "
                f"{record.initializer.centroid_xy[1]:.2f})"
            )
        else:
            _shape = f"unavailable: {record.reason}"
            _centroid = "—"
        return (
            f"| {record.target.object_id} | {_shape} | "
            f"{1e3 * _photometry.peak_brightness_jy_per_beam:.3f} | "
            f"{1e3 * _photometry.owned_pixel_integrated_flux_jy:.3f} | "
            f"{_centroid} |"
        )

    _rows = "\n".join(_row(record) for record in _region_measurements)
    mo.md(f"""
    ## 5. Exact-label moment measurements

    {_header}
    | --- | --- | ---: | ---: | --- |
    {_rows}

    These are deterministic measurements of only the pixels assigned to each
    watershed region. The shape is a brightness-weighted pixel-space moment
    initializer, not a fitted or beam-deconvolved source size. Owned-pixel flux
    is likewise distinct from the infinite-area flux of a fitted Gaussian.
    """)
    return


@app.cell
def _(
    demonstration_workspace,
    pathlib,
    rapthor_catalogue_adapter,
    tiled_catalogue,
):
    rapthor_catalogue_path = (
        pathlib.Path(demonstration_workspace.name) / "source_catalog.fits"
    )
    rapthor_catalogue_product = (
        rapthor_catalogue_adapter.write_rapthor_catalogue_fits(
            rapthor_catalogue_path,
            tiled_catalogue.catalogue,
        )
    )
    rapthor_catalogue_table = (
        rapthor_catalogue_adapter.read_rapthor_catalogue_fits(
            rapthor_catalogue_path
        )
    )
    return rapthor_catalogue_product, rapthor_catalogue_table


@app.cell(hide_code=True)
def _(mo, rapthor_catalogue_product, rapthor_catalogue_table, tiled_catalogue):
    _sources = tiled_catalogue.catalogue.sources

    def _deconvolved(source):
        if source.deconvolved_shape is None:
            return "unresolved"
        return f"{3600 * source.deconvolved_shape.major_fwhm_degrees:.2f}"

    _rows = "\n".join(
        (
            f"| {source.source_id} | "
            f"{source.position.right_ascension_degrees:.5f} | "
            f"{source.position.declination_degrees:.5f} | "
            f"{1e3 * source.flux.peak_flux_jy_per_beam:.3f} | "
            f"{1e3 * source.flux.integrated_flux_jy:.3f} | "
            f"{3600 * source.fitted_shape.major_fwhm_degrees:.2f} | "
            f"{_deconvolved(source)} | "
            f"{', '.join(source.quality_flags)} |"
        )
        for source in _sources
    )
    _columns = ", ".join(rapthor_catalogue_table.colnames)
    _catalogue_header = (
        "| Source | RA (deg) | Dec (deg) | Peak (mJy/beam) | "
        "Total (mJy) | Fitted major (arcsec) | "
        "Deconvolved major (arcsec) | Quality flags |"
    )
    _catalogue_separator = (
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |"
    )
    mo.md(f"""
    ## 6. Fitted sky catalogue and Rapthor view

    {_catalogue_header}
    {_catalogue_separator}
    {_rows}

    The fitted pixel ellipses have been transformed through the local WCS and
    deconvolved from the restoring beam. An unresolved result has no internal
    physical size; the compatibility writer alone translates it to
    `DC_Maj = 0`.

    The deterministic FITS product contains **{len(rapthor_catalogue_table)}
    rows**, **{rapthor_catalogue_product.byte_count} bytes**, and exactly the
    columns Rapthor reads directly: `{_columns}`.
    """)
    return


@app.cell
def _(
    np,
    one_tile_background,
    one_tile_catalogue,
    one_tile_catalogue_shards,
    one_tile_deblending,
    one_tile_detection,
    one_tile_mask,
    one_tile_moments,
    one_tile_rms,
    source_filtering_mask,
    tiled_deblending,
    tiled_detection,
    tiled_catalogue,
    tiled_catalogue_shards,
    tiled_moments,
    background_plane,
    rms_plane,
):
    partition_checks = {
        "Background is identical": np.array_equal(
            one_tile_background,
            background_plane,
        ),
        "RMS is identical": np.array_equal(one_tile_rms, rms_plane),
        "Source mask is identical": np.array_equal(
            one_tile_mask,
            source_filtering_mask,
        ),
        "Island summaries are identical": (
            one_tile_detection.islands == tiled_detection.islands
        ),
        "Deblended summaries are identical": (
            one_tile_deblending == tiled_deblending
        ),
        "Moment records are identical": one_tile_moments == tiled_moments,
        "Catalogue shards are identical": (
            one_tile_catalogue_shards == tiled_catalogue_shards
        ),
        "Completed catalogues are identical": (
            one_tile_catalogue == tiled_catalogue
        ),
    }
    return (partition_checks,)


@app.cell(hide_code=True)
def _(mo, partition_checks, tiled_detection):
    _rows = "\n".join(
        f"| {name} | {'✅' if passed else '❌'} |"
        for name, passed in partition_checks.items()
    )
    _candidate_positions = (
        ", ".join(
            str(item)
            for item in tiled_detection.adaptive_candidate_positions_yx
        )
        or "none"
    )
    mo.md(f"""
    ## 7. Partition invariance

    | Check | Result |
    | --- | --- |
    {_rows}

    The four-tile run used a deterministic hierarchical boundary reduction.
    Its automatically discovered adaptive-RMS candidate positions were:
    `{_candidate_positions}`.

    This small serial comparison exercises the same scheduler-independent
    contract used by the Dask executor; the integration suite separately
    verifies serial/Dask equality, retries, and task-order invariance.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 8. Recover an extended residual across scales

    Phase 5 first removes or excludes accepted compact emission. This isolated
    example therefore starts from a compact-clean residual containing one
    broad Gaussian with a peak of only 4 sigma. The original residual remains
    the measurement and mask support: multiscale responses may seed an island,
    but they do not replace the observed pixels or invent filtered flux.

    Hebog uses two deliberately separate multiscale roles:

    1. a beam-aware matched-filter bank provides sensitive seed evidence; and
    2. a three-level residual B3 à trous transform supplies persistent,
       auditable scale support.

    Seeds above 5 sigma grow through eight-connected original residual pixels
    at or above 3 sigma. A retained scale response also needs at least 50%
    valid filter support.
    """)
    return


@app.cell
def _(demonstration_dataset, hebog_config, multiscale_algorithms, np):
    multiscale_shape_yx = (129, 129)
    _y_grid, _x_grid = np.indices(multiscale_shape_yx, dtype=np.float64)
    multiscale_rms_jy_per_beam = 0.001
    multiscale_residual = 0.004 * np.exp(
        -0.5
        * (
            np.square((_x_grid - 64.0) / 10.0)
            + np.square((_y_grid - 64.0) / 7.0)
        )
    )
    multiscale_beam = multiscale_algorithms.BeamShapePixels(
        major_fwhm_pixels=demonstration_dataset.beam.major_fwhm_pixels,
        minor_fwhm_pixels=demonstration_dataset.beam.minor_fwhm_pixels,
        position_angle_degrees=(
            demonstration_dataset.beam.position_angle_degrees
        ),
    )
    _prepared_multiscale = multiscale_algorithms.prepare_scale_filter_inputs(
        multiscale_residual,
        np.ones(multiscale_shape_yx, dtype=np.bool_),
        np.zeros(multiscale_shape_yx, dtype=np.float64),
        np.full(
            multiscale_shape_yx,
            multiscale_rms_jy_per_beam,
            dtype=np.float64,
        ),
    )
    _matched_plan = multiscale_algorithms.build_scale_filter_bank(
        multiscale_beam,
        family="beam-aware-matched-filter",
        scales=((1, 1.0), (2, 2.0), (3, 4.0)),
        noise_correlation=multiscale_beam,
    )
    multiscale_matched = multiscale_algorithms.evaluate_scale_filter_bank(
        _prepared_multiscale,
        _matched_plan,
        minimum_support_fraction=0.5,
    )
    _atrous_plan = multiscale_algorithms.build_residual_atrous_plan(
        multiscale_beam,
        noise_correlation=multiscale_beam,
    )
    multiscale_atrous = multiscale_algorithms.evaluate_residual_atrous(
        _prepared_multiscale,
        _atrous_plan,
        minimum_support_fraction=0.5,
    )
    multiscale_detection = (
        multiscale_algorithms.detect_residual_multiscale_islands(
            _prepared_multiscale,
            multiscale_matched,
            multiscale_atrous,
            multiscale_beam,
            hebog_config.ResidualMultiscaleDetectionConfig(
                detection_threshold_sigma=5.0,
                island_threshold_sigma=3.0,
                minimum_scale_support_fraction=0.5,
                minimum_island_area_beams=1.0,
            ),
        )
    )
    multiscale_direct_snr = multiscale_residual / multiscale_rms_jy_per_beam
    return (
        multiscale_atrous,
        multiscale_detection,
        multiscale_direct_snr,
        multiscale_matched,
        multiscale_residual,
    )


@app.cell(hide_code=True)
def _(
    mo,
    multiscale_atrous,
    multiscale_detection,
    multiscale_direct_snr,
    multiscale_matched,
    np,
    plt,
):
    _figure, _axes = plt.subplots(1, 3, figsize=(13.0, 4.0))
    _direct_artist = _axes[0].imshow(
        multiscale_direct_snr,
        origin="lower",
        cmap="magma",
        vmin=0.0,
        vmax=5.0,
    )
    _axes[0].set_title("Original residual S/N")
    _combined_artist = _axes[1].imshow(
        multiscale_detection.combined_snr,
        origin="lower",
        cmap="magma",
        vmin=0.0,
        vmax=float(np.max(multiscale_detection.combined_snr)),
    )
    _axes[1].set_title("Maximum seed evidence")
    _axes[2].imshow(
        multiscale_detection.retained_mask,
        origin="lower",
        cmap="gray_r",
        vmin=0,
        vmax=1,
    )
    _axes[2].set_title("Original-pixel retained support")
    for _axis in _axes:
        _axis.set(xlabel="x pixel", ylabel="y pixel")
    _figure.colorbar(_direct_artist, ax=_axes[0], shrink=0.8)
    _figure.colorbar(_combined_artist, ax=_axes[1], shrink=0.8)
    _figure.tight_layout()
    _matched_peak_snrs = tuple(
        float(
            np.nanmax(
                response.response_jy_per_beam
                / response.effective_rms_jy_per_beam
            )
        )
        for response in multiscale_matched.responses
    )
    _atrous_peak_snrs = tuple(
        float(
            np.nanmax(
                response.response_jy_per_beam
                / response.effective_rms_jy_per_beam
            )
        )
        for response in multiscale_atrous.responses
    )
    _retained_count = int(np.count_nonzero(multiscale_detection.retained_mask))
    _statistics = mo.hstack(
        [
            mo.stat(
                label="Direct peak",
                value=(f"{float(np.max(multiscale_direct_snr)):.2f} sigma"),
            ),
            mo.stat(
                label="Matched-filter peaks (1/2/4 beams)",
                value=" / ".join(
                    f"{value:.2f}" for value in _matched_peak_snrs
                ),
            ),
            mo.stat(
                label="B3 peaks (levels 1/2/3)",
                value=" / ".join(
                    f"{value:.2f}" for value in _atrous_peak_snrs
                ),
            ),
            mo.stat(
                label="Retained support",
                value=f"{_retained_count} pixels",
            ),
        ],
        widths="equal",
    )
    mo.vstack([_statistics, _figure])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## What this does—and does not—demonstrate

    Hebog can currently locate compact and multiscale emission, reconcile it
    across bounded tiles, retain exact compact catalogue products when no
    extended evidence changes an association, measure accepted extended
    support on original pixels, and record the contributing scales and visible
    support. Compact Gaussian uncertainties are calibrated where the Phase 4
    contract permits them; shape and marginally resolved flux uncertainties
    remain explicitly report-only or unavailable rather than fabricated.

    This notebook demonstrates scientific stages, not the final public
    pipeline. Per-channel catalogue fields, `find_sources` orchestration, the
    complete Rapthor `filter_skymodel` decision, the controlled incremental
    performance gate, untouched Phase 5 qualification, and independent human
    review remain open. Hebog is therefore not yet a drop-in PyBDSF replacement
    or a production-ready Rapthor backend.
    """).callout(kind="warn")
    return


if __name__ == "__main__":
    app.run()
