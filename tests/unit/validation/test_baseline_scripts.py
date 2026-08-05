"""Tests for the isolated PyBDSF baseline entry points."""

from __future__ import annotations

import hashlib
import runpy
import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from hebog.data_models.partitioning import ImageBounds
from hebog.executors import SerialExecutor
from hebog.io.base import ImageWindow
from hebog.stages.background import estimate_background_rms_grids
from hebog.validation.comparison import CatalogueOutlierThresholds
from hebog.validation.datasets import (
    DatasetManifest,
    DatasetRole,
    iter_dataset_recipes,
    load_dataset_manifest,
)
from hebog.validation.phase_four_analysis import ratio_values, truth_sets


def _script(name: str) -> dict[str, Any]:
    """Load one script without invoking its command-line entry point."""
    root = Path(__file__).parents[3]
    return runpy.run_path(str(root / "scripts" / "benchmark" / name))


def _validation_script(name: str) -> dict[str, Any]:
    """Load one validation script without invoking its CLI."""
    root = Path(__file__).parents[3]
    return runpy.run_path(str(root / "scripts" / "validation" / name))


def test_paired_audit_uses_an_aggregate_reliability_ratio() -> None:
    """Whole-image resampling recomputes the canonical ratio of sums."""
    counts = {
        "catalogue-reliability": np.asarray(((33.0, 34.0), (33.0, 35.0)))
    }

    result = ratio_values(counts, np.asarray(((0, 1),), dtype=np.int64))

    assert result["catalogue-reliability"][0] == pytest.approx(66.0 / 69.0)


def test_paired_audit_truth_populations_remain_disjoint() -> None:
    """Point, clear, and blend endpoints use predeclared truth sets."""
    root = Path(__file__).parents[3]
    dataset = load_dataset_manifest(
        root / "config/datasets/phase-4-paired-regression.json"
    ).datasets[0]

    all_groups, individual, point, clear, blend = truth_sets(dataset)

    assert len(all_groups) == 33
    assert len(individual) == 32
    assert len(point) == 8
    assert len(clear) == 1
    assert len(blend) == 1
    assert point.isdisjoint(clear | blend)


def test_final_evaluator_refuses_to_overwrite_a_decision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The one-look entry point cannot replace an existing result."""
    output = tmp_path / "decision.json"
    output.write_text("already evaluated\n", encoding="utf-8")
    namespace = _validation_script("evaluate_phase4_qualification.py")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_phase4_qualification.py",
            "--campaign",
            "campaign.json",
            "--manifest",
            "manifest.json",
            "--dataset-id",
            "final",
            "--scientific-contract",
            "measurement.json",
            "--scientific-gates",
            "gates.json",
            "--comparison-protocol",
            "protocol.json",
            "--output",
            str(output),
        ],
    )

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        namespace["main"]()


def test_phase4r_qualification_freeze_changes_every_field_family(
    tmp_path: Path,
) -> None:
    """The one-look population is more than a new contiguous seed range."""
    root = Path(__file__).parents[3]
    template_path = root / "config/datasets/phase-4r-regression-2.json"
    template = load_dataset_manifest(template_path).datasets[0]
    namespace = _validation_script("freeze_phase4r_iteration.py")
    arguments = SimpleNamespace(
        template=template_path,
        output=tmp_path / "qualification.json",
        identifier="phase4r-qualification-256",
        role="qualification",
        first_seed=2026170001,
        realizations=600,
        provenance="Frozen after named review and before one-look execution.",
        reflect_x=True,
        reference_sky_degrees=(318.2, -58.4),
        pixel_scale_degrees_xy=(-0.00025, 0.00026),
        wcs_rotation_degrees=44.0,
        background=-0.00011,
    )

    document = namespace["_derived_document"](arguments)
    manifest = DatasetManifest.model_validate(document)
    frozen = manifest.datasets[0]
    recipes = iter_dataset_recipes(frozen)

    assert manifest.manifest_id == "phase-4r-qualification"
    assert frozen.role is DatasetRole.QUALIFICATION
    assert len(recipes) == 600
    assert frozen.recipe.sources[0].x_pixel == pytest.approx(
        frozen.recipe.shape_yx[1] - 1 - template.recipe.sources[0].x_pixel
    )
    assert frozen.recipe.sources[
        0
    ].rotation_degrees_counterclockwise_from_x == (
        pytest.approx(
            (
                180.0
                - template.recipe.sources[
                    0
                ].rotation_degrees_counterclockwise_from_x
            )
            % 180.0
        )
    )
    assert frozen.beam.position_angle_degrees == pytest.approx(57.0)
    assert frozen.recipe.noise_correlation is not None
    assert frozen.recipe.noise_correlation.position_angle_degrees == (
        pytest.approx(57.0)
    )
    assert frozen.recipe.noise_rms_fractional_gradient_xy == pytest.approx(
        (0.1, 0.14)
    )
    assert frozen.recipe.invalid_rectangles[0].x_start == 103
    assert frozen.recipe.invalid_rectangles[0].x_stop == 111
    assert frozen.wcs.reference_sky_degrees == pytest.approx((318.2, -58.4))
    assert frozen.wcs.pixel_scale_degrees_xy == pytest.approx(
        (-0.00025, 0.00026)
    )
    assert frozen.wcs.rotation_degrees_counterclockwise == pytest.approx(44.0)
    assert frozen.recipe.background == pytest.approx(-0.00011)
    assert frozen.expected_statistics.background_jy_per_beam == pytest.approx(
        -0.00011
    )


def test_phase4r_replacement_freeze_reflects_vertical_field(
    tmp_path: Path,
) -> None:
    """The approved replacement changes vertical geometry and identity."""
    root = Path(__file__).parents[3]
    template_path = root / "config/datasets/phase-4r-qualification.json"
    template = load_dataset_manifest(template_path).datasets[0]
    namespace = _validation_script("freeze_phase4r_iteration.py")
    arguments = SimpleNamespace(
        template=template_path,
        output=tmp_path / "qualification-replacement.json",
        manifest_id="phase-4r-qualification-replacement",
        identifier="phase4r-qualification-replacement-256",
        role="qualification",
        first_seed=2026200001,
        realizations=600,
        provenance=(
            "Frozen after replacement review and before one-look execution."
        ),
        reflect_x=False,
        reflect_y=True,
        reference_sky_degrees=(126.5, -30.8),
        pixel_scale_degrees_xy=(-0.00029, 0.00022),
        wcs_rotation_degrees=71.0,
        background=-0.00019,
    )

    document = namespace["_derived_document"](arguments)
    manifest = DatasetManifest.model_validate(document)
    frozen = manifest.datasets[0]
    height = frozen.recipe.shape_yx[0]

    assert manifest.manifest_id == "phase-4r-qualification-replacement"
    assert frozen.recipe.sources[0].x_pixel == pytest.approx(
        template.recipe.sources[0].x_pixel
    )
    assert frozen.recipe.sources[0].y_pixel == pytest.approx(
        height - 1 - template.recipe.sources[0].y_pixel
    )
    assert frozen.recipe.sources[
        0
    ].rotation_degrees_counterclockwise_from_x == pytest.approx(
        (
            180.0
            - template.recipe.sources[
                0
            ].rotation_degrees_counterclockwise_from_x
        )
        % 180.0
    )
    assert frozen.beam.position_angle_degrees == pytest.approx(123.0)
    assert frozen.recipe.noise_correlation is not None
    assert frozen.recipe.noise_correlation.position_angle_degrees == (
        pytest.approx(123.0)
    )
    assert frozen.recipe.noise_rms_fractional_gradient_xy == pytest.approx(
        (0.1, -0.14)
    )
    assert frozen.recipe.invalid_rectangles[0].y_start == 148
    assert frozen.recipe.invalid_rectangles[0].y_stop == 156
    assert frozen.association_truth_groups[0].reference_position_xy[1] == (
        pytest.approx(
            height
            - 1
            - template.association_truth_groups[0].reference_position_xy[1]
        )
    )


def test_phase4s_freezer_builds_the_reviewed_population() -> None:
    """The exact unseen truth can be reproduced without opening its noise."""
    namespace = _validation_script("freeze_phase4s_qualification.py")

    manifest = DatasetManifest.model_validate(namespace["_document"]())
    dataset = manifest.datasets[0]
    truth_sets_by_name = {
        stratum.identifier: stratum.source_indices
        for stratum in dataset.classification_strata
    }

    assert manifest.manifest_id == "phase-4s-qualification"
    assert len(iter_dataset_recipes(dataset)) == 800
    assert len(truth_sets_by_name["shape-unresolved"]) == 8
    assert len(truth_sets_by_name["shape-marginal-resolved"]) == 16
    assert len(truth_sets_by_name["shape-clear-resolved"]) == 8
    assert (
        len(
            {
                (
                    source.major_sigma_pixels,
                    source.minor_sigma_pixels,
                    source.rotation_degrees_counterclockwise_from_x,
                )
                for source in dataset.recipe.sources
            }
        )
        >= 25
    )


def test_phase4s_protocol_freezer_binds_population_counts() -> None:
    """The reviewed endpoint set is derived with explicit manifest units."""
    root = Path(__file__).parents[3]
    namespace = _validation_script("freeze_phase4s_protocol.py")

    document = namespace["_document"](
        root / "config/contracts/phase-4-paired-noninferiority.json"
    )

    assert document["contract_id"] == "phase-4s-paired-noninferiority"
    assert document["realization_count"] == 800
    assert document["minimum_familywise_interval_exclusion_power"] == 0.9
    populations = {
        endpoint["endpoint_id"]: (
            endpoint["population_unit"],
            endpoint["observations_per_realization"],
        )
        for endpoint in document["binary_endpoints"]
    }
    assert populations["compact-completeness"] == (
        "association-truth-groups",
        33,
    )
    assert populations["point-source-specificity"] == ("point-sources", 8)


def test_phase4t_freezer_builds_the_reviewed_confirmation() -> None:
    """The fresh confirmation has eight point sources in every SNR tier."""
    namespace = _validation_script("freeze_phase4t_qualification.py")

    manifest = DatasetManifest.model_validate(namespace["_document"]())
    dataset = manifest.datasets[0]
    classes = {
        stratum.identifier: set(stratum.source_indices)
        for stratum in dataset.classification_strata
    }
    validation = {
        stratum.identifier: set(stratum.source_indices)
        for stratum in dataset.validation_strata
    }

    assert manifest.manifest_id == "phase-4t-qualification"
    assert len(iter_dataset_recipes(dataset)) == 800
    assert len(dataset.recipe.sources) == 50
    assert len(dataset.association_truth_groups) == 49
    assert len(classes["shape-unresolved"]) == 32
    assert len(classes["shape-marginal-resolved"]) == 8
    assert len(classes["shape-clear-resolved"]) == 8
    assert all(
        len(classes["shape-unresolved"] & validation[f"snr-{snr}"]) == 8
        for snr in (10, 15, 25, 50)
    )


def test_phase4t_protocol_freezer_binds_absolute_power_population() -> None:
    """The follow-up protocol retains the viewed effect and frozen margin."""
    root = Path(__file__).parents[3]
    namespace = _validation_script("freeze_phase4t_protocol.py")

    document = namespace["_document"](
        root / "config/contracts/phase-4s-paired-noninferiority.json"
    )

    assert document["contract_id"] == "phase-4t-paired-noninferiority"
    checks = document["absolute_mean_power_checks"]
    assert len(checks) == 1
    assert checks[0]["observations_per_realization"] == 8
    assert checks[0]["anticipated_mean_normalized_residual"] == 0.1062
    populations = {
        endpoint["endpoint_id"]: endpoint["observations_per_realization"]
        for endpoint in document["binary_endpoints"]
    }
    assert populations["compact-completeness"] == 49
    assert populations["point-source-specificity"] == 32


def test_reference_configuration_requires_explicit_ordered_thresholds() -> (
    None
):
    """A campaign cannot silently inherit the Rapthor helper defaults."""
    pytest.importorskip(
        "resource",
        reason="the reference runner executes inside a POSIX container",
    )
    namespace = _script("pybdsf_reference_run.py")
    configuration: Callable[[float, float], dict[str, object]] = namespace[
        "_configuration"
    ]

    assert configuration(5.0, 3.0)["threshold_pixel_sigma"] == 5.0
    assert configuration(5.0, 3.0)["threshold_island_sigma"] == 3.0
    with pytest.raises(ValueError, match="0 < island <= detection"):
        configuration(3.0, 5.0)


def test_phase_four_reference_runner_freezes_exact_rapthor_profile() -> None:
    """The campaign runner cannot inherit changing PyBDSF defaults."""
    namespace = _script("run_phase4_pybdsf_campaign.py")
    configuration: Callable[[int], dict[str, object]] = namespace[
        "_pybdsf_configuration"
    ]

    assert configuration(4) == {
        "adaptive_rms_box": True,
        "adaptive_thresh": 75.0,
        "atrous_do": True,
        "atrous_jmax": 3,
        "mean_map": "zero",
        "ncores": 4,
        "rms_box": [150, 50],
        "rms_box_bright": [35, 7],
        "rms_map": True,
        "thresh": "hard",
        "thresh_isl": 3.0,
        "thresh_pix": 5.0,
    }


def test_phase_four_reference_runner_records_failures() -> None:
    """A PyBDSF exception remains a result rather than a dropped seed."""
    namespace = _script("run_phase4_pybdsf_campaign.py")
    capture: Callable[..., Any] = namespace["_failure_from_exception"]

    failure = capture(
        ValueError("fitting failed"),
        stage="pybdsf-source-finding",
        traceback_text="Traceback: fitting failed",
    )

    assert failure.stage == "pybdsf-source-finding"
    assert failure.exception_type == "ValueError"
    assert len(failure.traceback_sha256) == 64


def test_phase_four_reference_runner_keeps_failed_seed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An implementation crash returns a failure row and an auditable log."""
    namespace = _script("run_phase4_pybdsf_campaign.py")
    run_realization: Callable[..., Any] = namespace["_run_realization"]
    root = Path(__file__).parents[3]
    dataset = load_dataset_manifest(
        root / "config/datasets/phase-4-regression.json"
    ).datasets[0]
    recipe = iter_dataset_recipes(dataset)[0]

    def fail_process_image(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise IndexError("two-pixel atrous island")

    result = run_realization(
        SimpleNamespace(process_image=fail_process_image),
        recipe,
        dataset,
        tmp_path,
        namespace["_pybdsf_configuration"](4),
        implementation_identifier="pybdsf-master",
        outlier_thresholds=CatalogueOutlierThresholds(
            position_beams=0.5,
            peak_flux_fractional_difference=0.5,
            integrated_flux_fractional_difference=0.5,
            fitted_axis_fractional_difference=0.5,
            deconvolved_axis_fractional_difference=1.0,
        ),
        maximum_separation_beams=0.5,
        position_angle_minimum_axis_ratio=1.1,
    )

    assert result.status == "failure"
    assert result.seed == recipe.seed
    assert result.failure is not None
    assert result.failure.exception_type == "IndexError"
    assert "two-pixel atrous island" in capsys.readouterr().err


def test_phase_four_hebog_runner_freezes_scientific_configuration() -> None:
    """The candidate shard cannot inherit changing library defaults."""
    namespace = _script("run_phase4_hebog_campaign.py")
    configuration: Callable[[], dict[str, object]] = namespace[
        "_hebog_configuration"
    ]

    assert configuration() == {
        "adaptive_rms": {
            "candidate_threshold_sigma": 75.0,
            "influence_radius_pixels": 75.0,
            "step_yx": [7, 7],
            "transition_width_pixels": 20.0,
            "window_shape_yx": [35, 35],
        },
        "catalogue": {
            "deconvolution_axis_significance_sigma": 5.0,
            "deconvolution_relative_tolerance": 1e-10,
            "extension_significance_sigma": 5.0,
            "maximum_catalogue_records": 10000,
        },
        "coarse_rms": {
            "maximum_batch_cells": 32,
            "step_yx": [50, 50],
            "window_shape_yx": [150, 150],
        },
        "deblending": {
            "maximum_batch_pixels": 500000,
            "maximum_compact_bounds_pixels": 250000,
            "maximum_compact_island_pixels": 100000,
            "minimum_peak_separation_pixels": 2,
            "minimum_peak_signal_to_noise": 5.0,
            "minimum_region_pixels": 7,
            "minimum_saddle_depth_sigma": 1.0,
        },
        "executor": "serial",
        "fitting": {
            "association_aperture_minimum_fixed_beam_model_fraction": 0.9,
            "association_aperture_radius_sigma": 3.0,
            "background_model": "fixed-zero",
            "center_margin_pixels": 1.0,
            "context_margin_pixels": 8,
            "convergence_tolerance": 1e-8,
            "maximum_amplitude_factor": 5.0,
            "maximum_axis_ratio": 30.0,
            "maximum_background_offset_sigma": 3.0,
            "maximum_function_evaluations": 300,
            "maximum_information_condition_number": 100000000.0,
            "maximum_gls_pixels": 512,
            "maximum_sigma_pixels": 30.0,
            "model_selection": "beam-or-free",
            "minimum_fit_pixels": 7,
            "minimum_sigma_pixels": 0.2,
            "extension_significance_sigma": 5.0,
            "pixel_support": "owned-region",
            "point_estimator": "correlated-gls",
            "position_estimator": "bounded-context-free",
        },
        "image_dtype": "float64",
        "moment": {
            "covariance_relative_tolerance": 1e-12,
            "minimum_shape_pixels": 3,
        },
        "rms_statistics": {
            "clipping_sigma": 3.0,
            "maximum_iterations": 10,
            "minimum_samples": 6,
        },
        "source_finder": {
            "detection_threshold_sigma": 5.0,
            "island_threshold_sigma": 3.0,
            "minimum_island_pixels": 7,
        },
        "tile_core_shape_yx": [128, 128],
    }


def test_phase_four_hebog_runner_keeps_failed_seed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A candidate exception remains a result rather than a dropped seed."""
    namespace = _script("run_phase4_hebog_campaign.py")
    run_realization: Callable[..., Any] = namespace["_run_realization"]
    root = Path(__file__).parents[3]
    dataset = load_dataset_manifest(
        root / "config/datasets/phase-4-regression.json"
    ).datasets[0]
    recipe = iter_dataset_recipes(dataset)[0]

    def fail_candidate(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise RuntimeError("candidate fit failed")

    result = run_realization(
        recipe,
        dataset,
        tmp_path,
        implementation_identifier="hebog",
        outlier_thresholds=CatalogueOutlierThresholds(
            position_beams=0.5,
            peak_flux_fractional_difference=0.5,
            integrated_flux_fractional_difference=0.5,
            fitted_axis_fractional_difference=0.5,
            deconvolved_axis_fractional_difference=1.0,
        ),
        maximum_separation_beams=0.5,
        position_angle_minimum_axis_ratio=1.1,
        process_recipe=fail_candidate,
    )

    assert result.status == "failure"
    assert result.seed == recipe.seed
    assert result.failure is not None
    assert result.failure.stage == "hebog-source-finding"
    assert result.failure.exception_type == "RuntimeError"
    assert "candidate fit failed" in capsys.readouterr().err


def test_directory_identity_excludes_mutable_casa_lock_files(
    tmp_path: Path,
) -> None:
    """Opening a Measurement Set must not change its scientific identity."""
    namespace = _script("run_phase0_pybdsf_baseline.py")
    path_sha256: Callable[[Path], str] = namespace["_path_sha256"]
    (tmp_path / "table.dat").write_bytes(b"science")
    (tmp_path / "table.lock").write_bytes(b"first lock state")

    first = path_sha256(tmp_path)
    (tmp_path / "table.lock").write_bytes(b"second lock state")

    assert path_sha256(tmp_path) == first
    assert first != hashlib.sha256(b"science").hexdigest()


def test_phase1_io_benchmark_samples_portable_current_rss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Loading and measuring the benchmark must not require POSIX resource."""
    namespace = _script("measure_phase1_io.py")
    monkeypatch.setattr(
        namespace["psutil"],
        "Process",
        lambda: SimpleNamespace(memory_info=lambda: SimpleNamespace(rss=8192)),
    )

    sampler = namespace["_ResidentMemorySampler"]()
    sampler.start()

    assert sampler.stop() == 8192


def test_phase1_io_benchmark_records_bounded_one_and_many_tile_runs(
    tmp_path: Path,
) -> None:
    """The benchmark observes the real FITS/Zarr path and its memory bound."""
    namespace = _script("measure_phase1_io.py")
    input_path = tmp_path / "input.fits"
    generate_input: Callable[..., None] = namespace["_generate_input"]
    run_once: Callable[..., Any] = namespace["_run_once"]
    generate_input(input_path, size=5)

    one_tile = run_once(
        input_path=input_path,
        work_parent=tmp_path,
        size=5,
        tile_size=8,
        repetition_index=0,
        warmup=True,
    )
    many_tile = run_once(
        input_path=input_path,
        work_parent=tmp_path,
        size=5,
        tile_size=3,
        repetition_index=1,
        warmup=False,
    )

    assert one_tile.partition_count == 1
    assert one_tile.maximum_row_block_bytes == 5 * 5 * 8
    assert many_tile.partition_count == 4
    assert many_tile.maximum_row_block_bytes == 3 * 5 * 8
    assert many_tile.object_count > one_tile.object_count
    assert many_tile.zarr_bytes > 0
    assert many_tile.final_fits_bytes > 0
    assert tuple(stage.stage for stage in many_tile.measurement.stages) == (
        "fits-zarr-ingestion",
        "zarr-fits-materialisation",
    )
    metrics = many_tile.measurement.complete
    assert metrics.dask_task_count == 0
    assert metrics.array_copy_count is None
    assert {item.metric for item in metrics.unavailable_metrics} == {
        "array_copy_bytes",
        "array_copy_count",
    }


def test_phase2_background_benchmark_records_bounded_stage_work() -> None:
    """The benchmark measures coarse batches and interpolation separately."""
    namespace = _script("measure_phase2_background.py")
    configuration: Callable[..., Any] = namespace["_configuration"]
    run_once: Callable[..., Any] = namespace["_run_once"]
    values = np.arange(20 * 24, dtype=np.float64).reshape(20, 24)

    class ArraySource:
        """Provide bounded windows for the benchmark contract test."""

        def read_window(self, bounds: ImageBounds) -> ImageWindow:
            return ImageWindow(
                bounds=bounds,
                values=values[
                    bounds.y_start : bounds.y_stop,
                    bounds.x_start : bounds.x_stop,
                ],
                valid_pixels=np.ones(bounds.shape_yx, dtype=np.bool_),
            )

    config = configuration(
        window_size=5,
        step_size=4,
        maximum_batch_cells=4,
    )
    result = run_once(
        source=ArraySource(),
        image_shape_yx=values.shape,
        config=config,
        executor=SerialExecutor(),
        executor_kind="serial",
        tile_size=12,
        repetition_index=1,
        warmup=False,
    )

    assert result.partition_count == 4
    assert result.coarse_cell_count == 30
    assert result.maximum_tile_pixels == 12 * 12
    assert tuple(stage.stage for stage in result.measurement.stages) == (
        "coarse-rms-grid",
        "rms-interpolation",
    )
    metrics = result.measurement.complete
    assert metrics.dask_task_count == 0
    assert metrics.transfer_bytes == 0
    assert metrics.spill_bytes == 0


def test_phase3_detection_benchmark_excludes_prepared_coarse_grid(
    tmp_path: Path,
) -> None:
    """The component runner measures bounded detection and deblending."""
    namespace = _script("measure_phase3_detection.py")
    configuration: Callable[[], Any] = namespace["_configuration"]
    run_once: Callable[..., Any] = namespace["_run_once"]
    values = np.zeros((20, 24), dtype=np.float64)

    class ArraySource:
        """Provide bounded windows for the benchmark contract test."""

        def read_window(self, bounds: ImageBounds) -> ImageWindow:
            return ImageWindow(
                bounds=bounds,
                values=values[
                    bounds.y_start : bounds.y_stop,
                    bounds.x_start : bounds.x_stop,
                ],
                valid_pixels=np.ones(bounds.shape_yx, dtype=np.bool_),
            )

    source = ArraySource()
    detection_config, deblend_config = configuration()
    coarse_grids = estimate_background_rms_grids(
        source,
        values.shape,
        detection_config.background_rms,
        SerialExecutor(),
        bright_candidate_positions_yx=(),
    )

    result = run_once(
        source=source,
        coarse_grids=coarse_grids,
        detection_config=detection_config,
        deblend_config=deblend_config,
        executor=SerialExecutor(),
        executor_kind="serial",
        tile_size=12,
        work_parent=tmp_path,
        repetition_index=0,
        warmup=False,
    )

    assert result.partition_count == 4
    assert result.detected_island_count == 0
    assert result.deblended_region_count == 0
    assert tuple(stage.stage for stage in result.measurement.stages) == (
        "compact-detection",
        "compact-deblending",
    )
    assert result.measurement.complete.dask_task_count == 0


def test_phase3_benchmark_input_is_deterministic_and_density_stratified(
    tmp_path: Path,
) -> None:
    """Performance tiers use repeatable sparse, normal, and dense fields."""
    namespace = _script("generate_phase3_input.py")
    generate_values: Callable[..., Any] = namespace["_generate_values"]
    generate_input: Callable[..., None] = namespace["_generate_input"]

    sparse = generate_values(64, "empty-or-sparse")
    normal = generate_values(64, "normal")
    dense = generate_values(64, "dense-or-extended")
    repeated = generate_values(64, "dense-or-extended")
    generate_input(
        tmp_path / "dense.fits",
        size=64,
        workload="dense-or-extended",
    )

    np.testing.assert_array_equal(dense, repeated)
    assert not np.array_equal(sparse, normal)
    assert not np.array_equal(normal, dense)
    assert (tmp_path / "dense.fits").is_file()


def test_phase3_matrix_uses_serial_small_and_dask_representative() -> None:
    """The frozen matrix avoids scheduler overhead on bounded small work."""
    namespace = _script("run_phase3_matrix.py")
    execution_policy: Callable[[int], tuple[str, int]] = namespace[
        "_execution_policy"
    ]

    assert execution_policy(256) == ("serial", 256)
    assert execution_policy(1024) == ("serial", 1024)
    assert execution_policy(3000) == ("dask", 1000)
