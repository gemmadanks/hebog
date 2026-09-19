# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Per-parent component topology, against the whole-plane deblender."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
from pathlib import Path
from typing import TypeVar, cast

import numpy as np
import numpy.typing as npt
import pytest
from astropy.io import fits
from astropy.wcs import WCS
from distributed import Client
from scipy.ndimage import label as ndimage_label

from hebog.algorithms.component_measurement import (
    ComponentMeasurements,
    FitParentMeasurement,
    measure_component_models,
    reconcile_component_measurements,
)
from hebog.algorithms.component_topology import deblend_component_topology
from hebog.algorithms.labelling import (
    LocalIslandTileSummary,
    TileBoundaryLabels,
)
from hebog.algorithms.multiscale import (
    BeamShapePixels,
    build_residual_atrous_plan,
)
from hebog.algorithms.partitioning import plan_image_partitions
from hebog.algorithms.reconciliation import (
    DetectedIsland,
    ReconciledIslands,
    TileLabelMapping,
)
from hebog.config import (
    CompactDeblendConfig,
    CompactGaussianFitConfig,
    CompactMomentConfig,
)
from hebog.data_models.images import RestoringBeam
from hebog.data_models.partitioning import ImageBounds, PartitionManifest
from hebog.executors import DaskExecutor, SerialExecutor, TaskRequirement
from hebog.io.base import ImageWindow
from hebog.io.zarr import ZarrProductSink
from hebog.science.configuration import source_finder_configs
from hebog.stages.objects import (
    ComponentFitStageConfig,
    ComponentFitStageResult,
    ComponentTopologyStageConfig,
    ComponentTopologyStageResult,
    FitParentStageConfig,
    _ContextLink,
    _ContextPublicationBatch,
    _ContextTile,
    _DisjointContexts,
    _fit_parent_numbers,
    _FitBatch,
    _global_context,
    _ParentBatch,
    _SupportBatch,
    _TileBatch,
    _union_bounds,
    component_fit_product_names,
    component_topology_product_names,
    fit_parent_product_names,
    run_component_fit_stage,
    run_component_topology_stage,
    run_fit_parent_stage,
)
from hebog.validation.tiled_detection import ArrayImageSource

pytestmark = pytest.mark.integration

_Input = TypeVar("_Input")
_Output = TypeVar("_Output")
_SHAPE_YX = (48, 96)
_DETECTION_SIGMA = 5.0
_MEASUREMENT_BEAM = BeamShapePixels(4.0, 4.0, 0.0)


class _ReverseCompletionExecutor(SerialExecutor):
    """Return completed task records in reverse order."""

    def map_batches(
        self,
        function: Callable[[_Input], _Output],
        batches: Iterable[_Input],
        *,
        requirement: TaskRequirement | None = None,
    ) -> list[_Output]:
        """Evaluate canonically but expose reverse completion order."""
        return list(
            reversed(
                super().map_batches(function, batches, requirement=requirement)
            )
        )


class _DropNthMapExecutor(SerialExecutor):
    """Complete every round but one, to prove each fails closed."""

    def __init__(self, dropped_round: int) -> None:
        """Count maps so one chosen round can return nothing."""
        super().__init__()
        self._dropped_round = dropped_round
        self._call_count = 0

    def map_batches(
        self,
        function: Callable[[_Input], _Output],
        batches: Iterable[_Input],
        *,
        requirement: TaskRequirement | None = None,
    ) -> list[_Output]:
        """Run every round except the chosen one."""
        self._call_count += 1
        if self._call_count == self._dropped_round:
            return []
        return super().map_batches(function, batches, requirement=requirement)


def _labelled(mask: npt.NDArray[np.bool_]) -> npt.NDArray[np.int32]:
    """Return eight-connected labels of one analytic mask."""
    labels, _ = cast(
        tuple[npt.NDArray[np.int32], int],
        ndimage_label(mask, structure=np.ones((3, 3), dtype=np.int8)),
    )
    return labels


def _planes() -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.int32],
    npt.NDArray[np.int32],
    npt.NDArray[np.bool_],
]:
    """Return three parents: a blend, a single peak and a faint island.

    The blended parent has two well-separated peaks, so the reviewed
    watershed splits it and its measurement support has to be partitioned
    between the two new seeds. It spans several tile cores, which is what
    makes the per-parent round necessary.
    """
    yy, xx = np.mgrid[: _SHAPE_YX[0], : _SHAPE_YX[1]]
    signal = np.zeros(_SHAPE_YX, dtype=np.float64)
    for amplitude, centre_y, centre_x in (
        (12.0, 20, 30),
        (11.0, 20, 37),
        (9.0, 36, 70),
        (5.5, 8, 80),
    ):
        signal += amplitude * np.exp(
            -((yy - centre_y) ** 2 + (xx - centre_x) ** 2) / 8.0
        )
    direct = np.zeros(_SHAPE_YX, dtype=np.int32)
    measurement = np.zeros(_SHAPE_YX, dtype=np.int32)
    labelled = _labelled(signal >= 3.0)
    for index, label_value in enumerate(
        sorted({int(value) for value in np.unique(labelled) if value}),
        start=1,
    ):
        direct[labelled == label_value] = index
    support_labels = _labelled(signal >= 2.0)
    for label_value in np.unique(support_labels):
        if label_value <= 0:
            continue
        region = support_labels == label_value
        owners = {int(value) for value in np.unique(direct[region]) if value}
        if len(owners) == 1:
            measurement[region] = owners.pop()
    measurement[direct > 0] = direct[direct > 0]
    return signal, direct, measurement, np.ones(_SHAPE_YX, dtype=np.bool_)


def _publish(
    root: Path,
    products: tuple[tuple[str, npt.NDArray[np.generic], str], ...],
    *,
    generation_id: str,
) -> ZarrProductSink:
    """Publish one generation of analytic planes over 16-pixel cores."""
    manifest = plan_image_partitions(
        image_shape_yx=_SHAPE_YX,
        tile_core_shape_yx=(16, 16),
        halo_yx=(0, 0),
    )
    sink = ZarrProductSink(root, manifest, generation_id=generation_id)
    for product_name, _, dtype in products:
        sink.initialize_product(
            product_name=product_name,
            dtype=np.dtype(dtype),
        )
    sink.publish_generation(
        product_names=tuple(name for name, _, _ in products),
        chunks=[
            sink.write_chunk(
                product_name=product_name,
                tile=tile,
                values=np.asarray(
                    values[
                        tile.core_bounds.y_start : tile.core_bounds.y_stop,
                        tile.core_bounds.x_start : tile.core_bounds.x_stop,
                    ]
                ),
            )
            for tile in manifest.tiles
            for product_name, values, _ in products
        ],
    )
    return sink


def _sources(root: Path) -> tuple[ZarrProductSink, ZarrProductSink]:
    """Publish the support and detection generations this pass reads."""
    signal, direct, measurement, valid = _planes()
    return (
        _publish(
            root / "support.zarr",
            (
                ("component-labels", direct, "<i4"),
                ("measurement-labels", measurement, "<i4"),
            ),
            generation_id="support-fixture",
        ),
        _publish(
            root / "detection.zarr",
            (
                ("direct-snr", signal, "<f8"),
                ("valid-pixels", valid, "bool"),
            ),
            generation_id="detection-fixture",
        ),
    )


def _deblend_config() -> CompactDeblendConfig:
    """Return the reviewed compact deblending policy the public path uses."""
    return replace(
        source_finder_configs()[1],
        minimum_peak_signal_to_noise=float(
            np.nextafter(_DETECTION_SIGMA, -np.inf)
        ),
    )


def _manifest(core: int) -> PartitionManifest:
    """Plan one core-only component partition."""
    return plan_image_partitions(
        image_shape_yx=_SHAPE_YX,
        tile_core_shape_yx=(core, core),
        halo_yx=(0, 0),
    )


def _config(
    *,
    maximum_tiles_per_batch: int = 2,
    maximum_batch_read_pixels: int = 8192,
) -> ComponentTopologyStageConfig:
    """Return the reviewed policy with bounded task limits."""
    return ComponentTopologyStageConfig(
        deblend=_deblend_config(),
        maximum_tiles_per_batch=maximum_tiles_per_batch,
        maximum_batch_read_pixels=maximum_batch_read_pixels,
    )


def _run(
    root: Path,
    *,
    core: int = 16,
    executor: object | None = None,
    config: ComponentTopologyStageConfig | None = None,
) -> tuple[ComponentTopologyStageResult, ZarrProductSink]:
    """Execute one isolated component-topology variant."""
    root.mkdir(parents=True, exist_ok=True)
    support_source, detection_source = _sources(root)
    manifest = _manifest(core)
    sink = ZarrProductSink(
        root / "components.zarr",
        manifest,
        generation_id="components",
    )
    result = run_component_topology_stage(
        support_source,
        detection_source,
        manifest,
        config=_config() if config is None else config,
        executor=(  # type: ignore[arg-type]
            SerialExecutor() if executor is None else executor
        ),
        sink=sink,
    )
    return result, sink


def _published(
    sink: ZarrProductSink,
) -> dict[str, npt.NDArray[np.int32]]:
    """Read both published component planes over the whole image."""
    bounds = ImageBounds(0, _SHAPE_YX[0], 0, _SHAPE_YX[1])
    return {
        name: np.asarray(
            sink.read_completed_window(name, bounds),
            dtype=np.int32,
        )
        for name in component_topology_product_names()
    }


def _whole_plane_topology() -> dict[str, npt.NDArray[np.int32]]:
    """Deblend every parent over complete planes, as the oracle."""
    signal, direct, measurement, valid = _planes()
    topology = deblend_component_topology(
        np.where(valid, signal, np.nan),
        direct,
        measurement,
        valid,
        _deblend_config(),
    )
    return {
        "component-direct-labels": np.asarray(
            topology.direct_component_labels,
            dtype=np.int32,
        ),
        "component-measurement-labels": np.asarray(
            topology.measurement_component_labels,
            dtype=np.int32,
        ),
    }


def test_published_components_match_the_whole_plane_deblender(
    tmp_path: Path,
) -> None:
    """One parent per task reproduces the whole-plane component topology."""
    result, sink = _run(tmp_path / "run")

    published = _published(sink)

    expected = _whole_plane_topology()
    for name, values in expected.items():
        np.testing.assert_array_equal(published[name], values, name)
    assert result.deblended_parent_count >= 1
    assert result.component_count > result.parent_count


def test_component_topology_is_partition_and_executor_invariant(
    tmp_path: Path,
) -> None:
    """One published generation survives geometry, batching and workers."""
    expected = _published(_run(tmp_path / "reference", core=64)[1])
    variants: list[tuple[str, int, object, ComponentTopologyStageConfig]] = [
        ("cores-16", 16, SerialExecutor(), _config()),
        ("cores-24", 24, SerialExecutor(), _config(maximum_tiles_per_batch=1)),
        (
            "one-parent-per-read",
            16,
            SerialExecutor(),
            _config(maximum_batch_read_pixels=1),
        ),
        ("reverse", 16, _ReverseCompletionExecutor(), _config()),
    ]
    for name, core, executor, config in variants:
        _, sink = _run(
            tmp_path / name,
            core=core,
            executor=executor,
            config=config,
        )
        published = _published(sink)
        for product_name, values in expected.items():
            np.testing.assert_array_equal(
                published[product_name],
                values,
                f"{name}:{product_name}",
            )

    with Client(
        processes=False,
        n_workers=2,
        threads_per_worker=1,
        dashboard_address=None,
    ) as client:
        _, sink = _run(tmp_path / "dask", executor=DaskExecutor(client))
    published = _published(sink)
    for product_name, values in expected.items():
        np.testing.assert_array_equal(published[product_name], values)


def test_component_topology_defers_a_parent_above_the_compact_bound(
    tmp_path: Path,
) -> None:
    """An oversized parent stays one explicit component, never truncated."""
    config = ComponentTopologyStageConfig(
        deblend=replace(
            _deblend_config(),
            maximum_compact_island_pixels=4,
        ),
        maximum_tiles_per_batch=2,
        maximum_batch_read_pixels=8192,
    )

    result, sink = _run(tmp_path / "run", config=config)

    published = _published(sink)
    assert result.deferred_parent_count == result.parent_count
    assert result.component_count == result.parent_count
    np.testing.assert_array_equal(
        published["component-direct-labels"] > 0,
        _planes()[1] > 0,
    )


def test_component_topology_publishes_the_canonical_product_set(
    tmp_path: Path,
) -> None:
    """The generation carries exactly one chunk per product and core."""
    manifest = _manifest(16)

    result, _ = _run(tmp_path / "run")

    assert set(result.generation.product_names) == set(
        component_topology_product_names()
    )
    assert len(result.generation.chunks) == len(
        component_topology_product_names()
    ) * len(manifest.tiles)
    assert result.executor_task_count > 0
    assert result.maximum_graph_width > 0
    assert result.maximum_parent_read_pixels > 0
    assert result.parent_batch_count > 0


@pytest.mark.parametrize(
    "dropped_round, message",
    [
        (1, "no parent extent results"),
        (2, "no component deblend results"),
        (3, "no component publication results"),
    ],
)
def test_every_round_fails_closed_on_a_silent_executor(
    tmp_path: Path,
    dropped_round: int,
    message: str,
) -> None:
    """A dropped result is never published as a complete generation."""
    with pytest.raises(ValueError, match=message):
        _run(
            tmp_path / f"round-{dropped_round}",
            executor=_DropNthMapExecutor(dropped_round),
        )


def test_component_topology_rejects_a_haloed_manifest(tmp_path: Path) -> None:
    """The component write owns cores and reads no halo."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    support_source, detection_source = _sources(tmp_path)
    manifest = plan_image_partitions(
        image_shape_yx=_SHAPE_YX,
        tile_core_shape_yx=(16, 16),
        halo_yx=(2, 2),
    )

    with pytest.raises(ValueError, match="cores without a halo"):
        run_component_topology_stage(
            support_source,
            detection_source,
            manifest,
            config=_config(),
            executor=SerialExecutor(),
            sink=ZarrProductSink(
                tmp_path / "components.zarr",
                manifest,
                generation_id="components",
            ),
        )


def test_component_topology_forbids_empty_executor_work_records() -> None:
    """An empty batch is a scheduling defect, not a task to submit."""
    with pytest.raises(ValueError, match="parent batch must not be empty"):
        _ParentBatch(parents=(), read_bounds=ImageBounds(0, 1, 0, 1))
    with pytest.raises(ValueError, match="tile batch must not be empty"):
        _TileBatch(requests=())


@pytest.mark.parametrize(
    "maximum_tiles_per_batch, maximum_batch_read_pixels, message",
    [
        (0, 8192, "maximum_tiles_per_batch"),
        (2, 0, "maximum_batch_read_pixels"),
    ],
)
def test_component_topology_rejects_invalid_configuration(
    maximum_tiles_per_batch: int,
    maximum_batch_read_pixels: int,
    message: str,
) -> None:
    """Configuration is validated before any product is initialized."""
    with pytest.raises(ValueError, match=message):
        ComponentTopologyStageConfig(
            deblend=_deblend_config(),
            maximum_tiles_per_batch=maximum_tiles_per_batch,
            maximum_batch_read_pixels=maximum_batch_read_pixels,
        )


def test_component_topology_publishes_an_image_with_no_parent(
    tmp_path: Path,
) -> None:
    """An image with no admitted island publishes a complete core set."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    signal, _, _, valid = _planes()
    empty = np.zeros(_SHAPE_YX, dtype=np.int32)
    support_source = _publish(
        tmp_path / "support.zarr",
        (
            ("component-labels", empty, "<i4"),
            ("measurement-labels", empty, "<i4"),
        ),
        generation_id="support-fixture",
    )
    detection_source = _publish(
        tmp_path / "detection.zarr",
        (("direct-snr", signal, "<f8"), ("valid-pixels", valid, "bool")),
        generation_id="detection-fixture",
    )
    manifest = _manifest(16)
    sink = ZarrProductSink(
        tmp_path / "components.zarr",
        manifest,
        generation_id="components",
    )

    result = run_component_topology_stage(
        support_source,
        detection_source,
        manifest,
        config=_config(),
        executor=SerialExecutor(),
        sink=sink,
    )

    assert result.parent_count == 0
    assert result.component_count == 0
    assert result.parent_batch_count == 0
    assert result.maximum_parent_read_pixels == 0
    for values in _published(sink).values():
        assert not np.any(values)


def test_component_topology_requires_direct_support_for_every_parent(
    tmp_path: Path,
) -> None:
    """A measurement parent without direct support cannot be deblended."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    signal, direct, measurement, valid = _planes()
    orphaned = measurement.copy()
    orphaned[44:47, 4:7] = int(direct.max()) + 1
    support_source = _publish(
        tmp_path / "support.zarr",
        (
            ("component-labels", direct, "<i4"),
            ("measurement-labels", orphaned, "<i4"),
        ),
        generation_id="support-fixture",
    )
    detection_source = _publish(
        tmp_path / "detection.zarr",
        (("direct-snr", signal, "<f8"), ("valid-pixels", valid, "bool")),
        generation_id="detection-fixture",
    )
    manifest = _manifest(16)

    with pytest.raises(ValueError, match="must own direct support"):
        run_component_topology_stage(
            support_source,
            detection_source,
            manifest,
            config=_config(),
            executor=SerialExecutor(),
            sink=ZarrProductSink(
                tmp_path / "components.zarr",
                manifest,
                generation_id="components",
            ),
        )


def test_component_topology_requires_a_matching_sink_and_generations(
    tmp_path: Path,
) -> None:
    """Identities are checked before any product is initialized."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    support_source, detection_source = _sources(tmp_path)
    manifest = _manifest(16)
    other_shape = plan_image_partitions(
        image_shape_yx=(32, 32),
        tile_core_shape_yx=(16, 16),
        halo_yx=(0, 0),
    )
    incomplete = _publish(
        tmp_path / "incomplete.zarr",
        (("direct-snr", _planes()[0], "<f8"),),
        generation_id="incomplete",
    )

    with pytest.raises(ValueError, match="must use the stage manifest"):
        run_component_topology_stage(
            support_source,
            detection_source,
            manifest,
            config=_config(),
            executor=SerialExecutor(),
            sink=ZarrProductSink(
                tmp_path / "mismatched.zarr",
                _manifest(32),
                generation_id="mismatched",
            ),
        )
    with pytest.raises(ValueError, match="match the component image shape"):
        run_component_topology_stage(
            support_source,
            detection_source,
            other_shape,
            config=_config(),
            executor=SerialExecutor(),
            sink=ZarrProductSink(
                tmp_path / "other.zarr",
                other_shape,
                generation_id="other",
            ),
        )
    with pytest.raises(ValueError, match="every component plane read"):
        run_component_topology_stage(
            support_source,
            incomplete,
            manifest,
            config=_config(),
            executor=SerialExecutor(),
            sink=ZarrProductSink(
                tmp_path / "incomplete-components.zarr",
                manifest,
                generation_id="components",
            ),
        )


def test_parent_extents_merge_in_either_order() -> None:
    """A core that sees only one plane's support still contributes bounds."""
    first = ImageBounds(4, 8, 4, 8)
    second = ImageBounds(6, 12, 2, 5)

    assert _union_bounds(None, first) == first
    assert _union_bounds(first, None) == first
    assert _union_bounds(first, second) == ImageBounds(4, 12, 2, 8)
    assert _union_bounds(second, first) == ImageBounds(4, 12, 2, 8)
    assert _union_bounds(None, None) is None


def _fit_config() -> tuple[CompactMomentConfig, CompactGaussianFitConfig]:
    """Return the reviewed moment and fit policy the public path uses."""
    _, _, moment_config, fit_config, _ = source_finder_configs()
    return moment_config, replace(
        fit_config,
        integrated_flux_bias_correction_sigma=0.0,
    )


def _measurement_header() -> fits.Header:
    """Return one valid one-arcsecond celestial fixture header."""
    header = fits.Header()
    header["NAXIS"] = 2
    header["NAXIS1"] = _SHAPE_YX[1]
    header["NAXIS2"] = _SHAPE_YX[0]
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["CRPIX1"] = (_SHAPE_YX[1] + 1) / 2
    header["CRPIX2"] = (_SHAPE_YX[0] + 1) / 2
    header["CRVAL1"] = 10.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0
    header["BMAJ"] = 4.0 / 3600.0
    header["BMIN"] = 4.0 / 3600.0
    header["BPA"] = 0.0
    return header


def _measurement_inputs() -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.bool_],
    npt.NDArray[np.int32],
    npt.NDArray[np.int32],
]:
    """Return the residual, RMS and component planes the fits measure."""
    signal, _, _, valid = _planes()
    topology = deblend_component_topology(
        np.where(valid, signal, np.nan),
        _planes()[1],
        _planes()[2],
        valid,
        _deblend_config(),
    )
    return (
        signal,
        np.ones(_SHAPE_YX, dtype=np.float64),
        valid,
        np.asarray(topology.direct_component_labels, dtype=np.int32),
        np.asarray(topology.measurement_component_labels, dtype=np.int32),
    )


def _measurement_sources(root: Path) -> tuple[ZarrProductSink, ...]:
    """Publish every generation the fit rounds read."""
    _, rms, valid, direct, measurement = _measurement_inputs()
    return (
        _publish(
            root / "background.zarr",
            (
                ("background", np.zeros(_SHAPE_YX, dtype=np.float64), "<f8"),
                ("rms", rms, "<f8"),
            ),
            generation_id="background-fixture",
        ),
        _publish(
            root / "detection.zarr",
            (("valid-pixels", valid, "bool"),),
            generation_id="detection-fixture",
        ),
        _publish(
            root / "components.zarr",
            (
                ("component-direct-labels", direct, "<i4"),
                ("component-measurement-labels", measurement, "<i4"),
            ),
            generation_id="component-fixture",
        ),
    )


def _run_fits(
    root: Path,
    *,
    core: int = 16,
    executor: object | None = None,
    maximum_batch_read_pixels: int = 8192,
) -> tuple[ComponentFitStageResult, ZarrProductSink, int]:
    """Reconcile the fit parents, then measure them, in isolation."""
    root.mkdir(parents=True, exist_ok=True)
    residual, _, _, _, _ = _measurement_inputs()
    background_source, detection_source, component_source = (
        _measurement_sources(root)
    )
    moment_config, fit_config = _fit_config()
    atrous_plan = build_residual_atrous_plan(
        _MEASUREMENT_BEAM,
        noise_correlation=_MEASUREMENT_BEAM,
    )
    margin = int(fit_config.context_margin_pixels)
    fit_parent_manifest = plan_image_partitions(
        image_shape_yx=_SHAPE_YX,
        tile_core_shape_yx=(
            max(core, 4 * margin + 1),
            max(core, 4 * margin + 1),
        ),
        halo_yx=(margin, margin),
    )
    fit_parent_sink = ZarrProductSink(
        root / "fit-parents.zarr",
        fit_parent_manifest,
        generation_id="fit-parents",
    )
    resolved = SerialExecutor() if executor is None else executor
    fit_parents = run_fit_parent_stage(
        component_source,
        fit_parent_manifest,
        config=FitParentStageConfig(
            context_margin_pixels=margin,
            maximum_tiles_per_batch=2,
        ),
        executor=resolved,  # type: ignore[arg-type]
        sink=fit_parent_sink,
    )
    manifest = _manifest(core)
    sink = ZarrProductSink(
        root / "fits.zarr",
        manifest,
        generation_id="fits",
    )
    result = run_component_fit_stage(
        ArrayImageSource(residual, np.ones(_SHAPE_YX, dtype=np.bool_)),
        background_source,
        detection_source,
        component_source,
        fit_parent_sink,
        manifest,
        config=ComponentFitStageConfig(
            moment=moment_config,
            fit=fit_config,
            atrous_plan=atrous_plan,
            detection_sigma=_DETECTION_SIGMA,
            island_sigma=3.0,
            minimum_pixels=7,
            maximum_bounds_pixels=(
                _deblend_config().maximum_compact_bounds_pixels
            ),
            minimum_support_fraction=0.5,
            maximum_tiles_per_batch=2,
            maximum_batch_read_pixels=maximum_batch_read_pixels,
        ),
        wcs_header_text=_measurement_header().tostring(),
        beam=RestoringBeam(4.0 / 3600.0, 4.0 / 3600.0, 0.0),
        executor=resolved,  # type: ignore[arg-type]
        sink=sink,
    )
    return result, sink, fit_parents.fit_parent_count


def _whole_plane_measurements() -> ComponentMeasurements:
    """Measure every fit parent over complete planes, as the oracle."""
    residual, rms, valid, direct, measurement = _measurement_inputs()
    moment_config, fit_config = _fit_config()
    return measure_component_models(
        residual,
        rms,
        valid,
        direct,
        measurement,
        WCS(_measurement_header(), relax=True).celestial,
        RestoringBeam(4.0 / 3600.0, 4.0 / 3600.0, 0.0),
        moment_config,
        fit_config,
        detection_sigma=_DETECTION_SIGMA,
        island_sigma=3.0,
        minimum_pixels=7,
        maximum_bounds_pixels=(
            _deblend_config().maximum_compact_bounds_pixels
        ),
        atrous_plan=build_residual_atrous_plan(
            _MEASUREMENT_BEAM,
            noise_correlation=_MEASUREMENT_BEAM,
        ),
        minimum_support_fraction=0.5,
    )


def test_published_fits_match_the_whole_plane_measurement(
    tmp_path: Path,
) -> None:
    """One fit parent per task reproduces the whole-plane measurement."""
    result, sink, fit_parent_count = _run_fits(tmp_path / "run")

    expected = _whole_plane_measurements()
    reconciled = reconcile_component_measurements(
        *_measurement_inputs()[:3],
        _measurement_inputs()[4],
        WCS(_measurement_header(), relax=True).celestial,
        RestoringBeam(4.0 / 3600.0, 4.0 / 3600.0, 0.0),
        parents=result.parents,
        measurement_support=np.asarray(
            sink.read_completed_window(
                "measurement-support",
                ImageBounds(0, _SHAPE_YX[0], 0, _SHAPE_YX[1]),
            ),
            dtype=np.bool_,
        ).copy(),
        atrous_plan=build_residual_atrous_plan(
            _MEASUREMENT_BEAM,
            noise_correlation=_MEASUREMENT_BEAM,
        ),
        detection_sigma=_DETECTION_SIGMA,
        island_sigma=3.0,
        minimum_pixels=7,
        maximum_bounds_pixels=(
            _deblend_config().maximum_compact_bounds_pixels
        ),
        minimum_support_fraction=0.5,
    )

    assert fit_parent_count > 1
    assert reconciled.fits == expected.fits
    assert reconciled.compact_groups == expected.compact_groups
    assert reconciled.extended_groups == expected.extended_groups
    assert reconciled.grouping_evidence == expected.grouping_evidence
    assert reconciled.deferred_parent_count == expected.deferred_parent_count
    assert expected.measurement_support is not None
    np.testing.assert_array_equal(
        reconciled.measurement_support,
        expected.measurement_support,
    )


def _assert_parents_equal(
    candidate: tuple[FitParentMeasurement, ...],
    expected: tuple[FitParentMeasurement, ...],
) -> None:
    """Compare every fit parent's records and its bounded support window."""
    assert len(candidate) == len(expected)
    for measured, reference in zip(candidate, expected, strict=True):
        assert measured.fits == reference.fits
        assert measured.compact_groups == reference.compact_groups
        assert measured.extended_groups == reference.extended_groups
        assert measured.evidence == reference.evidence
        assert measured.deferred == reference.deferred
        assert measured.support_bounds == reference.support_bounds
        if reference.support_window is None:
            assert measured.support_window is None
            continue
        assert measured.support_window is not None
        np.testing.assert_array_equal(
            measured.support_window,
            reference.support_window,
        )


def test_component_fits_are_executor_invariant(tmp_path: Path) -> None:
    """Workers fit exactly what one in-process reference fits.

    Every value a task carries must survive the round trip a distributed
    executor puts it through, so the stage sends the caller's header text
    rather than a ``WCS``; Astropy re-serializes a ``WCS`` through a header
    it reformats itself. See
    :func:`~hebog.algorithms.astrometry.celestial_wcs_from_header_text`.
    """
    reference, reference_sink, _ = _run_fits(tmp_path / "reference")

    with Client(
        processes=False,
        n_workers=2,
        threads_per_worker=1,
        dashboard_address=None,
    ) as client:
        result, sink, _ = _run_fits(
            tmp_path / "dask",
            executor=DaskExecutor(client),
        )

    _assert_parents_equal(result.parents, reference.parents)
    bounds = ImageBounds(0, _SHAPE_YX[0], 0, _SHAPE_YX[1])
    np.testing.assert_array_equal(
        np.asarray(sink.read_completed_window("measurement-support", bounds)),
        np.asarray(
            reference_sink.read_completed_window(
                "measurement-support",
                bounds,
            )
        ),
    )


@pytest.mark.parametrize("core", [16, 24, 64])
def test_component_fits_are_partition_and_batch_invariant(
    tmp_path: Path,
    core: int,
) -> None:
    """Tile geometry and batching decide which task runs, not the fits."""
    reference, reference_sink, _ = _run_fits(tmp_path / "reference", core=64)

    result, sink, _ = _run_fits(
        tmp_path / f"core-{core}",
        core=core,
        maximum_batch_read_pixels=1,
    )

    _assert_parents_equal(result.parents, reference.parents)
    bounds = ImageBounds(0, _SHAPE_YX[0], 0, _SHAPE_YX[1])
    np.testing.assert_array_equal(
        np.asarray(sink.read_completed_window("measurement-support", bounds)),
        np.asarray(
            reference_sink.read_completed_window(
                "measurement-support",
                bounds,
            )
        ),
    )


class _ShiftedBoundsSource:
    """An image source that answers with bounds it was not asked for."""

    def __init__(self, source: ArrayImageSource) -> None:
        """Retain the source whose honest answers are then corrupted."""
        self._source = source

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        """Return the asked-for pixels under one narrower bound."""
        window = self._source.read_window(bounds)
        return ImageWindow(
            bounds=ImageBounds(
                bounds.y_start,
                bounds.y_stop,
                bounds.x_start,
                max(bounds.x_start + 1, bounds.x_stop - 1),
            ),
            values=window.values,
            valid_pixels=window.valid_pixels,
        )


def _fit_parent_margin() -> int:
    """Return the fit-context margin the reviewed policy asks for."""
    return int(_fit_config()[1].context_margin_pixels)


def _fit_parent_manifest(margin: int | None = None) -> PartitionManifest:
    """Return the haloed manifest the fit-parent round writes through."""
    resolved = _fit_parent_margin() if margin is None else margin
    side = max(16, 4 * resolved + 1)
    return plan_image_partitions(
        image_shape_yx=_SHAPE_YX,
        tile_core_shape_yx=(side, side),
        halo_yx=(resolved, resolved),
    )


def _fit_parent_config(**overrides: int) -> FitParentStageConfig:
    """Return the fit-parent configuration with one field replaced."""
    return FitParentStageConfig(
        **{
            "context_margin_pixels": _fit_parent_margin(),
            "maximum_tiles_per_batch": 2,
            **overrides,
        }
    )


def test_object_stages_publish_their_canonical_product_sets(
    tmp_path: Path,
) -> None:
    """Both fit rounds name exactly the products their cores write."""
    result, sink, fit_parent_count = _run_fits(tmp_path / "run")

    assert fit_parent_product_names() == ("fit-parent-labels",)
    assert component_fit_product_names() == ("measurement-support",)
    assert set(result.generation.product_names) == set(
        component_fit_product_names()
    )
    assert len(result.generation.chunks) == len(sink.manifest.tiles)
    assert fit_parent_count > 0
    assert result.fit_parent_count == fit_parent_count
    assert result.executor_task_count > 0
    assert result.maximum_graph_width > 0
    assert result.maximum_parent_read_pixels > 0
    assert result.parent_batch_count > 0
    assert result.partition_count == len(sink.manifest.tiles)
    assert result.deferred_parent_count >= 0


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"maximum_tiles_per_batch": 0}, "maximum_tiles_per_batch"),
        ({"context_margin_pixels": -1}, "context margin must be"),
    ],
)
def test_fit_parent_stage_rejects_invalid_configuration(
    overrides: dict[str, int],
    message: str,
) -> None:
    """Configuration is validated before any product is initialized."""
    with pytest.raises(ValueError, match=message):
        _fit_parent_config(**overrides)


@pytest.mark.parametrize(
    "maximum_tiles_per_batch, maximum_batch_read_pixels, message",
    [
        (0, 8192, "maximum_tiles_per_batch"),
        (2, 0, "maximum_batch_read_pixels"),
    ],
)
def test_component_fit_stage_rejects_invalid_configuration(
    maximum_tiles_per_batch: int,
    maximum_batch_read_pixels: int,
    message: str,
) -> None:
    """Configuration is validated before any product is initialized."""
    moment_config, fit_config = _fit_config()
    with pytest.raises(ValueError, match=message):
        ComponentFitStageConfig(
            moment=moment_config,
            fit=fit_config,
            atrous_plan=build_residual_atrous_plan(
                _MEASUREMENT_BEAM,
                noise_correlation=_MEASUREMENT_BEAM,
            ),
            detection_sigma=_DETECTION_SIGMA,
            island_sigma=3.0,
            minimum_pixels=7,
            maximum_bounds_pixels=(
                _deblend_config().maximum_compact_bounds_pixels
            ),
            minimum_support_fraction=0.5,
            maximum_tiles_per_batch=maximum_tiles_per_batch,
            maximum_batch_read_pixels=maximum_batch_read_pixels,
        )


def test_fit_rounds_forbid_empty_executor_work_records() -> None:
    """An empty batch is a scheduling defect, not a task to submit."""
    with pytest.raises(ValueError, match="publication batch must not be"):
        _ContextPublicationBatch(requests=())
    with pytest.raises(ValueError, match="fit batch must not be empty"):
        _FitBatch(parents=(), read_bounds=ImageBounds(0, 1, 0, 1))
    with pytest.raises(ValueError, match="support batch must not be empty"):
        _SupportBatch(requests=())


def test_joined_fit_contexts_take_their_smallest_label() -> None:
    """Union-find keeps the numbering a whole-plane pass would produce."""
    contexts = _DisjointContexts((1, 2, 3))

    contexts.union(2, 3)
    contexts.union(1, 2)

    assert contexts.find(3) == 1
    contexts.union(1, 3)
    assert contexts.fit_parent_numbers() == {1: 1, 2: 1, 3: 1}
    assert _DisjointContexts((4, 7)).fit_parent_numbers() == {4: 1, 7: 2}


def _context_tile(links: tuple[_ContextLink, ...]) -> _ContextTile:
    """Return one core carrying only the links the numbering reads."""
    partition = _fit_parent_manifest().tiles[0]
    empty = np.zeros(0, dtype=np.int32)
    return _ContextTile(
        partition=partition,
        summary=LocalIslandTileSummary(
            partition=partition,
            islands=(),
            boundary_labels=TileBoundaryLabels(empty, empty, empty, empty),
        ),
        links=links,
    )


def _reconciled_contexts(tile_id: str) -> ReconciledIslands:
    """Return two accepted contexts one core labels one and two."""
    return ReconciledIslands(
        islands=tuple(
            DetectedIsland(
                island_id=f"context-{label}",
                global_label=label,
                pixel_count=1,
                bounds=ImageBounds(label, label + 1, label, label + 1),
                peak_signal_to_noise=10.0,
                peak_position_yx=(label, label),
                first_pixel_yx=(label, label),
                touches_image_edge=False,
            )
            for label in (1, 2)
        ),
        tile_mappings=(
            TileLabelMapping(
                tile_id=tile_id,
                local_labels=(1, 2),
                global_labels=(1, 2),
            ),
        ),
        reduction_round_count=1,
    )


def test_one_owner_reaching_two_contexts_makes_one_fit_parent() -> None:
    """Support that lands in two contexts is still fitted jointly."""
    tile = _context_tile(
        (
            _ContextLink(owner_label=1, local_context_label=1),
            _ContextLink(owner_label=1, local_context_label=2),
        )
    )

    numbers = _fit_parent_numbers(
        (tile,), _reconciled_contexts(tile.partition.tile_id)
    )

    assert numbers == {1: 1, 2: 1}


def test_a_context_without_a_global_label_fails_closed() -> None:
    """A mapping that omits a local label is never silently numbered."""
    mapping = TileLabelMapping(
        tile_id="tile", local_labels=(1,), global_labels=(5,)
    )

    assert _global_context(mapping, 1) == 5
    with pytest.raises(ValueError, match="must cover every local label"):
        _global_context(mapping, 2)


@pytest.mark.parametrize(
    "dropped_round, message",
    [
        (1, "no fit-context results"),
        (2, "no fit-parent publication results"),
        (3, "no fit-parent extent results"),
        (4, "no component fit results"),
        (5, "no support publication results"),
    ],
)
def test_every_fit_round_fails_closed_on_a_silent_executor(
    tmp_path: Path,
    dropped_round: int,
    message: str,
) -> None:
    """A dropped result is never published as a complete generation."""
    with pytest.raises(ValueError, match=message):
        _run_fits(
            tmp_path / f"round-{dropped_round}",
            executor=_DropNthMapExecutor(dropped_round),
        )


def test_fit_parent_stage_requires_a_matching_sink_and_generation(
    tmp_path: Path,
) -> None:
    """Identities are checked before any product is initialized."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    _, _, component_source = _measurement_sources(tmp_path)
    manifest = _fit_parent_manifest()
    incomplete = _publish(
        tmp_path / "incomplete.zarr",
        (("component-direct-labels", _measurement_inputs()[3], "<i4"),),
        generation_id="incomplete",
    )
    other_shape = plan_image_partitions(
        image_shape_yx=(32, 32),
        tile_core_shape_yx=manifest.tile_core_shape_yx,
        halo_yx=manifest.halo_yx,
    )

    def run(
        target: PartitionManifest,
        *,
        source: ZarrProductSink = component_source,
        sink_manifest: PartitionManifest | None = None,
        name: str = "fit-parents",
    ) -> None:
        run_fit_parent_stage(
            source,
            target,
            config=_fit_parent_config(),
            executor=SerialExecutor(),
            sink=ZarrProductSink(
                tmp_path / f"{name}.zarr",
                target if sink_manifest is None else sink_manifest,
                generation_id=name,
            ),
        )

    with pytest.raises(ValueError, match="must use the stage manifest"):
        run(manifest, sink_manifest=other_shape, name="mismatched")
    with pytest.raises(ValueError, match="exact context margin"):
        run(_fit_parent_manifest(margin=_fit_parent_margin() + 1))
    with pytest.raises(ValueError, match="match the fit-parent image shape"):
        run(other_shape, name="other")
    with pytest.raises(ValueError, match="measurement component labels"):
        run(manifest, source=incomplete, name="incomplete-parents")


def _fit_stage_config(**overrides: object) -> ComponentFitStageConfig:
    """Return the component-fit configuration with one field replaced."""
    moment_config, fit_config = _fit_config()
    fields: dict[str, object] = {
        "moment": moment_config,
        "fit": fit_config,
        "atrous_plan": build_residual_atrous_plan(
            _MEASUREMENT_BEAM,
            noise_correlation=_MEASUREMENT_BEAM,
        ),
        "detection_sigma": _DETECTION_SIGMA,
        "island_sigma": 3.0,
        "minimum_pixels": 7,
        "maximum_bounds_pixels": (
            _deblend_config().maximum_compact_bounds_pixels
        ),
        "minimum_support_fraction": 0.5,
        "maximum_tiles_per_batch": 2,
        "maximum_batch_read_pixels": 8192,
        **overrides,
    }
    return ComponentFitStageConfig(**fields)  # type: ignore[arg-type]


def _published_fit_parents(root: Path) -> ZarrProductSink:
    """Publish the fit-parent generation the measurement round reads."""
    root.mkdir(parents=True, exist_ok=True)
    manifest = _fit_parent_manifest()
    sink = ZarrProductSink(
        root / "fit-parents.zarr", manifest, generation_id="fit-parents"
    )
    run_fit_parent_stage(
        _measurement_sources(root)[2],
        manifest,
        config=_fit_parent_config(),
        executor=SerialExecutor(),
        sink=sink,
    )
    return sink


def test_component_fit_stage_requires_matching_sinks_and_generations(
    tmp_path: Path,
) -> None:
    """Identities are checked before any product is initialized."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    background, detection, components = _measurement_sources(tmp_path)
    fit_parents = _published_fit_parents(tmp_path / "parents")
    source = ArrayImageSource(
        _measurement_inputs()[0], np.ones(_SHAPE_YX, dtype=np.bool_)
    )
    manifest = _manifest(16)
    other_shape = plan_image_partitions(
        image_shape_yx=(32, 32),
        tile_core_shape_yx=(16, 16),
        halo_yx=(0, 0),
    )
    incomplete = _publish(
        tmp_path / "incomplete.zarr",
        (("background", np.zeros(_SHAPE_YX, dtype=np.float64), "<f8"),),
        generation_id="incomplete",
    )

    def run(
        target: PartitionManifest,
        *,
        image_source: object = source,
        background_source: ZarrProductSink = background,
        sink_manifest: PartitionManifest | None = None,
        name: str = "fits",
    ) -> None:
        run_component_fit_stage(
            image_source,  # type: ignore[arg-type]
            background_source,
            detection,
            components,
            fit_parents,
            target,
            config=_fit_stage_config(),
            wcs_header_text=_measurement_header().tostring(),
            beam=RestoringBeam(4.0 / 3600.0, 4.0 / 3600.0, 0.0),
            executor=SerialExecutor(),
            sink=ZarrProductSink(
                tmp_path / f"{name}.zarr",
                target if sink_manifest is None else sink_manifest,
                generation_id=name,
            ),
        )

    with pytest.raises(ValueError, match="must use the stage manifest"):
        run(manifest, sink_manifest=_manifest(32), name="mismatched")
    with pytest.raises(ValueError, match="cores without a halo"):
        run(_fit_parent_manifest(), name="haloed")
    with pytest.raises(ValueError, match="match the fit image shape"):
        run(other_shape, name="other")
    with pytest.raises(ValueError, match="every fit plane read"):
        run(manifest, background_source=incomplete, name="incomplete-fits")
    with pytest.raises(ValueError, match="different fit-read bounds"):
        run(
            manifest,
            image_source=_ShiftedBoundsSource(source),
            name="shifted",
        )


def test_fit_rounds_publish_an_image_with_no_fit_parent(
    tmp_path: Path,
) -> None:
    """An image with no measurement support still writes every core."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    residual, rms, valid, _, _ = _measurement_inputs()
    empty = np.zeros(_SHAPE_YX, dtype=np.int32)
    background = _publish(
        tmp_path / "background.zarr",
        (
            ("background", np.zeros(_SHAPE_YX, dtype=np.float64), "<f8"),
            ("rms", rms, "<f8"),
        ),
        generation_id="background-fixture",
    )
    detection = _publish(
        tmp_path / "detection.zarr",
        (("valid-pixels", valid, "bool"),),
        generation_id="detection-fixture",
    )
    components = _publish(
        tmp_path / "components.zarr",
        (
            ("component-direct-labels", empty, "<i4"),
            ("component-measurement-labels", empty, "<i4"),
        ),
        generation_id="component-fixture",
    )
    parent_manifest = _fit_parent_manifest()
    parent_sink = ZarrProductSink(
        tmp_path / "fit-parents.zarr",
        parent_manifest,
        generation_id="fit-parents",
    )
    manifest = _manifest(16)
    sink = ZarrProductSink(
        tmp_path / "fits.zarr", manifest, generation_id="fits"
    )

    parents = run_fit_parent_stage(
        components,
        parent_manifest,
        config=_fit_parent_config(),
        executor=SerialExecutor(),
        sink=parent_sink,
    )
    result = run_component_fit_stage(
        ArrayImageSource(residual, np.ones(_SHAPE_YX, dtype=np.bool_)),
        background,
        detection,
        components,
        parent_sink,
        manifest,
        config=_fit_stage_config(),
        wcs_header_text=_measurement_header().tostring(),
        beam=RestoringBeam(4.0 / 3600.0, 4.0 / 3600.0, 0.0),
        executor=SerialExecutor(),
        sink=sink,
    )

    assert parents.fit_parent_count == 0
    assert result.fit_parent_count == 0
    assert result.parent_batch_count == 0
    assert result.parents == ()
    assert len(result.generation.chunks) == len(manifest.tiles)
    assert not np.asarray(
        sink.read_completed_window(
            "measurement-support",
            ImageBounds(0, _SHAPE_YX[0], 0, _SHAPE_YX[1]),
        )
    ).any()
