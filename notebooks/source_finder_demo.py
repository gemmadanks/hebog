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
    # Hebog compact source-finding demonstration

    This notebook runs the capabilities implemented through **Phase 4 Step 3**
    on a small, deterministic synthetic radio image. It estimates background
    and RMS noise, detects connected source islands, reconciles an island that
    crosses tile boundaries, deblends compact peaks, and calculates exact-label
    owned-pixel photometry and moment fit initializers.

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

    import matplotlib.patches as mpl_patches
    import matplotlib.pyplot as plt
    import numpy as np
    from scipy import ndimage

    import hebog.algorithms.partitioning as partitioning_algorithms
    import hebog.config as hebog_config
    import hebog.data_models as hebog_models
    import hebog.data_models.measurement as measurement_models
    import hebog.executors as hebog_executors
    import hebog.io as hebog_io
    import hebog.stages.deblending as deblending_stage
    import hebog.stages.detection as detection_stage
    import hebog.stages.measurement as measurement_stage
    import hebog.validation.datasets as validation_datasets

    return (
        deblending_stage,
        detection_stage,
        hebog_config,
        hebog_executors,
        hebog_io,
        hebog_models,
        measurement_models,
        measurement_stage,
        mpl_patches,
        ndimage,
        np,
        partitioning_algorithms,
        pathlib,
        plt,
        tempfile,
        validation_datasets,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 1. A governed synthetic radio image

    The checked-in development recipe contains Gaussian noise, a negative
    background, sources around the 3- and 5-sigma thresholds, a close unequal
    pair, and a bright source touching the image edge. This visual variant
    replaces the close pair with two equal compact sources seven pixels apart
    across a four-tile corner so the reconciliation and deblending results are
    easy to see; the frozen qualification recipe is not changed. Noise is
    generated from global pixel coordinates, so reading the image in
    different windows always produces exactly the same pixels.
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
        "peak_flux_jy_per_beam": 0.003,
        "major_sigma_pixels": 2.2,
        "minor_sigma_pixels": 1.4,
        "rotation_degrees_counterclockwise_from_x": 0.0,
    }
    _demonstration_sources[4] = _demonstration_sources[4].model_copy(
        update={**_pair_update, "x_pixel": 92.5}
    )
    _demonstration_sources[5] = _demonstration_sources[5].model_copy(
        update={**_pair_update, "x_pixel": 99.5}
    )
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
    ## 2. Run the bounded Phase 3 stages

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
    demonstration_dataset,
    detection_stage,
    hebog_config,
    measurement_models,
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
            minimum_island_pixels=6,
        ),
    )
    deblend_configuration = hebog_config.CompactDeblendConfig(
        minimum_peak_signal_to_noise=5.0,
        minimum_peak_separation_pixels=1,
        minimum_saddle_depth_sigma=0.5,
        maximum_compact_island_pixels=250_000,
        maximum_compact_bounds_pixels=1_000_000,
        maximum_batch_pixels=4_000_000,
    )
    moment_configuration = hebog_config.CompactMomentConfig(
        minimum_shape_pixels=3,
        covariance_relative_tolerance=1e-12,
    )
    _pixel_scales_degrees = demonstration_dataset.wcs.pixel_scale_degrees_xy
    _pixel_solid_angle = abs(
        np.deg2rad(_pixel_scales_degrees[0])
        * np.deg2rad(_pixel_scales_degrees[1])
    )
    _beam = demonstration_dataset.beam
    measurement_geometry = measurement_models.CompactMeasurementGeometry(
        pixel_solid_angle_steradians=_pixel_solid_angle,
        restoring_beam_solid_angle_steradians=(
            np.pi
            * _beam.major_fwhm_pixels
            * _beam.minor_fwhm_pixels
            * _pixel_solid_angle
            / (4.0 * np.log(2.0))
        ),
    )
    return (
        deblend_configuration,
        detection_configuration,
        measurement_geometry,
        moment_configuration,
    )


@app.cell
def _(
    deblend_configuration,
    deblending_stage,
    demonstration_recipe,
    detection_configuration,
    detection_stage,
    hebog_executors,
    hebog_io,
    image_source,
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
        return detection, deblending, moments, sink

    (
        one_tile_detection,
        one_tile_deblending,
        one_tile_moments,
        one_tile_sink,
    ) = execute_detection(
        demonstration_recipe.shape_yx,
        "one-tile",
    )
    (
        tiled_detection,
        tiled_deblending,
        tiled_moments,
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
        one_tile_sink,
        tiled_deblending,
        tiled_detection,
        tiled_moments,
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
    np,
    one_tile_background,
    one_tile_deblending,
    one_tile_detection,
    one_tile_mask,
    one_tile_moments,
    one_tile_rms,
    source_filtering_mask,
    tiled_deblending,
    tiled_detection,
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
    ## 6. Partition invariance

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
    ## What this does—and does not—demonstrate

    Hebog can currently locate compact emission, reconcile it across tiles,
    split admitted compact islands into deterministic regions, and calculate
    exact-label owned-pixel photometry and moment fit initializers. It also
    persists restartable background, RMS, and source-mask products.

    **The notebook does not produce a source catalogue.** Nonlinear Gaussian
    fitting, sky-coordinate and beam-deconvolved shapes, calibrated
    uncertainties, Rapthor/LSMTool catalogue compatibility, extended or
    multiscale recovery, and the final `filter_skymodel` decision remain later
    work. Hebog is not yet a drop-in PyBDSF replacement or a production-ready
    Rapthor backend.
    """).callout(kind="warn")
    return


if __name__ == "__main__":
    app.run()
