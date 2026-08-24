# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Executor, batching, retry, and product contracts for Phase 5 science."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from typing import TypeVar

import numpy as np
import numpy.typing as npt
import pytest
from distributed import Client

from hebog.algorithms.multiscale import (
    BeamShapePixels,
    detect_residual_multiscale_islands,
    prepare_scale_filter_inputs,
)
from hebog.algorithms.partitioning import plan_image_partitions
from hebog.algorithms.phase_five_execution import (
    evaluate_phase_five_filter_tile,
    scale_filter_halo_pixels,
)
from hebog.config import ResidualMultiscaleDetectionConfig
from hebog.data_models.partitioning import ImageBounds, PartitionManifest
from hebog.data_models.products import ProductChunk
from hebog.executors import DaskExecutor, SerialExecutor
from hebog.io.base import ImageWindow
from hebog.io.zarr import ZarrProductSink
from hebog.stages.multiscale import (
    PhaseFiveMultiscaleStageConfig,
    PhaseFiveMultiscaleStageResult,
    phase_five_multiscale_product_names,
    run_phase_five_multiscale_stage,
)

pytestmark = pytest.mark.integration

_Input = TypeVar("_Input")
_Output = TypeVar("_Output")
_SUPPORT_FRACTION = 0.5


class _ArrayImageSource:
    """Pickleable bounded image source for executor tests."""

    def __init__(
        self,
        values: npt.NDArray[np.float64],
        valid: npt.NDArray[np.bool_],
    ) -> None:
        self._values = values
        self._valid = valid

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        """Return one owned aligned window."""
        selection = _selection(bounds)
        return ImageWindow(
            bounds=bounds,
            values=np.array(self._values[selection], copy=True),
            valid_pixels=np.array(self._valid[selection], copy=True),
        )


class _InvalidImageSource(_ArrayImageSource):
    """Inject one deterministic image-window boundary failure."""

    def __init__(
        self,
        values: npt.NDArray[np.float64],
        valid: npt.NDArray[np.bool_],
        *,
        failure: str,
    ) -> None:
        super().__init__(values, valid)
        self._failure = failure

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        """Return either different bounds or misaligned arrays."""
        window = super().read_window(bounds)
        if self._failure == "bounds":
            return ImageWindow(
                bounds=ImageBounds(
                    bounds.y_start + 1,
                    bounds.y_stop + 1,
                    bounds.x_start,
                    bounds.x_stop,
                ),
                values=window.values,
                valid_pixels=window.valid_pixels,
            )
        return ImageWindow(
            bounds=bounds,
            values=window.values[:-1],
            valid_pixels=window.valid_pixels[:-1],
        )


class _ReverseCompletionExecutor:
    """Return completed task records in reverse order."""

    def map_batches(
        self,
        function: Callable[[_Input], _Output],
        batches: Iterable[_Input],
    ) -> list[_Output]:
        """Evaluate canonically but expose reverse completion order."""
        return list(reversed([function(batch) for batch in batches]))


class _RetryExecutor:
    """Retry every batch identically before returning one result."""

    def map_batches(
        self,
        function: Callable[[_Input], _Output],
        batches: Iterable[_Input],
    ) -> list[_Output]:
        """Prove completed chunks accept identical task retry."""
        results: list[_Output] = []
        for batch in batches:
            function(batch)
            second = function(batch)
            results.append(second)
        return results


class _EmptyExecutor:
    """Drop every submitted result for fail-closed executor testing."""

    def map_batches(
        self,
        _function: Callable[[_Input], _Output],
        _batches: Iterable[_Input],
    ) -> list[_Output]:
        """Return no result without evaluating work."""
        return []


class _EmptySecondPassExecutor:
    """Complete topology but drop every publication result."""

    def __init__(self) -> None:
        self._call_count = 0

    def map_batches(
        self,
        function: Callable[[_Input], _Output],
        batches: Iterable[_Input],
    ) -> list[_Output]:
        """Run the first map and return nothing from the second."""
        self._call_count += 1
        if self._call_count == 1:
            return [function(batch) for batch in batches]
        return []


@dataclass(frozen=True, slots=True)
class _ScienceIdentity:
    """Small-image oracle for promoted masks and stable topology IDs."""

    retained_mask: npt.NDArray[np.bool_]
    reconstruction_mask: npt.NDArray[np.bool_]
    scale_masks: tuple[npt.NDArray[np.bool_], ...]
    detection_island_ids: tuple[str, ...]
    reconstruction_island_ids: tuple[str, ...]
    scale_island_ids: tuple[tuple[str, ...], ...]


def _selection(bounds: ImageBounds) -> tuple[slice, slice]:
    """Return global slices for one half-open bound."""
    return (
        slice(bounds.y_start, bounds.y_stop),
        slice(bounds.x_start, bounds.x_stop),
    )


def _beam() -> BeamShapePixels:
    """Return a small beam with the frozen 14-pixel B3 halo."""
    return BeamShapePixels(1.0, 0.8, 13.0)


def _detection_config() -> ResidualMultiscaleDetectionConfig:
    """Return the frozen residual-B3 detection policy."""
    return ResidualMultiscaleDetectionConfig(
        detection_threshold_sigma=5.0,
        island_threshold_sigma=3.0,
        minimum_scale_support_fraction=_SUPPORT_FRACTION,
        minimum_island_area_beams=1.0,
    )


def _planes() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Create partition-edge, image-edge, and invalid-pixel evidence."""
    shape = (129, 137)
    y_grid, x_grid = np.indices(shape, dtype=np.float64)
    image = np.zeros(shape, dtype=np.float64)
    for centre_yx, sigma, amplitude in (
        ((61.0, 67.0), 4.0, 24.0),
        ((4.0, 115.0), 3.0, 19.0),
        ((125.0, 3.0), 5.0, 22.0),
        ((90.0, 95.0), 7.0, 17.0),
    ):
        image += amplitude * np.exp(
            -0.5
            * (
                np.square((y_grid - centre_yx[0]) / sigma)
                + np.square((x_grid - centre_yx[1]) / sigma)
            )
        )
    background = 0.03 * np.sin(x_grid / 17.0)
    rms = 1.0 + 0.05 * (y_grid / shape[0])
    valid = np.ones(shape, dtype=np.bool_)
    valid[57:65, 69:73] = False
    image[~valid] = np.nan
    return image, valid, background, rms


def _manifest(core_yx: tuple[int, int]) -> PartitionManifest:
    """Return one exact-halo zero-origin multiscale manifest."""
    halo = scale_filter_halo_pixels(_beam())
    return plan_image_partitions(
        image_shape_yx=_planes()[0].shape,
        tile_core_shape_yx=core_yx,
        halo_yx=(halo, halo),
    )


def _background_source(
    root: Path,
    *,
    image_shape_yx: tuple[int, int] = (129, 137),
    product_names: tuple[str, ...] = ("background", "rms"),
) -> ZarrProductSink:
    """Publish one reusable completed Phase 2 background/RMS generation."""
    _, _, background, rms = _planes()
    if image_shape_yx != background.shape:
        background = np.zeros(image_shape_yx, dtype=np.float64)
        rms = np.ones(image_shape_yx, dtype=np.float64)
    manifest = plan_image_partitions(
        image_shape_yx=image_shape_yx,
        tile_core_shape_yx=(64, 64),
        halo_yx=(0, 0),
    )
    sink = ZarrProductSink(
        root,
        manifest,
        generation_id="phase-two-fixture",
    )
    for name in product_names:
        sink.initialize_product(product_name=name, dtype=np.dtype("<f8"))
    chunks: list[ProductChunk] = []
    for tile in manifest.tiles:
        selection = _selection(tile.core_bounds)
        for product_name, values in (
            ("background", background),
            ("rms", rms),
        ):
            if product_name in product_names:
                chunks.append(
                    sink.write_chunk(
                        product_name=product_name,
                        tile=tile,
                        values=np.asarray(values[selection]),
                    )
                )
    sink.publish_generation(
        product_names=product_names,
        chunks=chunks,
    )
    return sink


def _run(
    root: Path,
    *,
    manifest: PartitionManifest,
    background_source: ZarrProductSink,
    executor: object,
    tiles_per_batch: int,
) -> tuple[PhaseFiveMultiscaleStageResult, ZarrProductSink]:
    """Execute one isolated stage variant with a common generation ID."""
    image, valid, _, _ = _planes()
    sink = ZarrProductSink(
        root,
        manifest,
        generation_id="phase-five-invariance",
    )
    result = run_phase_five_multiscale_stage(
        _ArrayImageSource(image, valid),
        background_source,
        manifest,
        config=PhaseFiveMultiscaleStageConfig(
            beam=_beam(),
            detection=_detection_config(),
            maximum_tiles_per_batch=tiles_per_batch,
        ),
        executor=executor,  # type: ignore[arg-type]
        sink=sink,
    )
    return result, sink


def _bool_window(
    source: ZarrProductSink,
    product_name: str,
    bounds: ImageBounds,
) -> npt.NDArray[np.bool_]:
    """Read one boolean test product with its reviewed storage dtype."""
    return np.asarray(
        source.read_completed_window(product_name, bounds),
        dtype=np.bool_,
    )


def _float_window(
    source: ZarrProductSink,
    product_name: str,
    bounds: ImageBounds,
) -> npt.NDArray[np.float64]:
    """Read one float test product with its reviewed storage dtype."""
    return np.asarray(
        source.read_completed_window(product_name, bounds),
        dtype=np.float64,
    )


def _science_identity(
    result: PhaseFiveMultiscaleStageResult,
    source: ZarrProductSink,
) -> _ScienceIdentity:
    """Read only the small test products and reconciled identities."""
    bounds = ImageBounds(0, 129, 0, 137)
    return _ScienceIdentity(
        retained_mask=_bool_window(source, "retained-mask", bounds),
        reconstruction_mask=_bool_window(
            source,
            "reconstruction-mask",
            bounds,
        ),
        scale_masks=tuple(
            _bool_window(source, f"scale-{order}-significant", bounds)
            for order in (1, 2, 3)
        ),
        detection_island_ids=tuple(
            island.island_id for island in result.detection_islands
        ),
        reconstruction_island_ids=tuple(
            island.island_id for island in result.reconstruction_islands
        ),
        scale_island_ids=tuple(
            tuple(island.island_id for island in islands)
            for islands in result.scale_islands_by_order
        ),
    )


def _assert_science_identity_equal(
    candidate: _ScienceIdentity,
    expected: _ScienceIdentity,
) -> None:
    """Compare exact accepted masks and stable reconciled identities."""
    np.testing.assert_array_equal(
        candidate.retained_mask, expected.retained_mask
    )
    np.testing.assert_array_equal(
        candidate.reconstruction_mask,
        expected.reconstruction_mask,
    )
    for candidate_mask, expected_mask in zip(
        candidate.scale_masks,
        expected.scale_masks,
        strict=True,
    ):
        np.testing.assert_array_equal(candidate_mask, expected_mask)
    assert candidate.detection_island_ids == expected.detection_island_ids
    assert (
        candidate.reconstruction_island_ids
        == expected.reconstruction_island_ids
    )
    assert candidate.scale_island_ids == expected.scale_island_ids


def test_multiscale_stage_is_batch_order_retry_and_executor_invariant(
    tmp_path: Path,
) -> None:
    """The same partition publishes one exact science generation."""
    background = _background_source(tmp_path / "background")
    manifest = _manifest((61, 67))
    variants: list[tuple[str, object, int]] = [
        ("serial-one", SerialExecutor(), 1),
        ("serial-all", SerialExecutor(), len(manifest.tiles)),
        ("reverse", _ReverseCompletionExecutor(), 2),
        ("retry", _RetryExecutor(), 2),
    ]
    outputs = [
        _run(
            tmp_path / name,
            manifest=manifest,
            background_source=background,
            executor=executor,
            tiles_per_batch=batch_size,
        )
        for name, executor, batch_size in variants
    ]
    for worker_count in (1, 2):
        with Client(
            processes=False,
            n_workers=worker_count,
            threads_per_worker=1,
            dashboard_address=None,
        ) as client:
            outputs.append(
                _run(
                    tmp_path / f"dask-{worker_count}",
                    manifest=manifest,
                    background_source=background,
                    executor=DaskExecutor(client),
                    tiles_per_batch=2,
                )
            )

    reference_result, reference_source = outputs[0]
    expected_manifest = reference_result.generation.canonical_json_bytes()
    expected_identity = _science_identity(
        reference_result,
        reference_source,
    )
    for result, source in outputs[1:]:
        assert result.generation.canonical_json_bytes() == expected_manifest
        assert result.partition_count == len(manifest.tiles)
        assert result.executor_task_count > 0
        assert result.maximum_read_pixel_count > 0
        assert result.maximum_workspace_bytes > 0
        assert result.maximum_retained_array_bytes > 0
        assert result.maximum_worker_bytes >= (
            result.maximum_retained_array_bytes
        )
        assert result.maximum_worker_bytes >= result.maximum_workspace_bytes
        assert result.topology_summary_count == 2 * len(manifest.tiles)
        assert result.scale_summary_count == 3 * len(manifest.tiles)
        assert result.boundary_summary_array_bytes > 0
        assert result.maximum_task_summary_array_bytes > 0
        assert result.published_product_shard_count == (
            len(phase_five_multiscale_product_names()) * len(manifest.tiles)
        )
        assert result.maximum_task_product_shard_count > 0
        _assert_science_identity_equal(
            _science_identity(result, source),
            expected_identity,
        )

    for (name, _, batch_size), (result, _) in zip(
        variants,
        outputs[: len(variants)],
        strict=True,
    ):
        batch_count = ceil(len(manifest.tiles) / batch_size)
        assert result.executor_task_count == 2 * batch_count, name
        assert result.maximum_graph_width == batch_count, name
        assert result.maximum_batch_partition_count == min(
            batch_size,
            len(manifest.tiles),
        )
        assert result.maximum_task_product_shard_count <= (
            len(phase_five_multiscale_product_names()) * batch_size
        )

    batch_two_reference = outputs[2][0]
    for result, _ in outputs[3:]:
        assert result.maximum_graph_width == (
            batch_two_reference.maximum_graph_width
        )
        assert result.maximum_retained_array_bytes == (
            batch_two_reference.maximum_retained_array_bytes
        )
        assert result.maximum_worker_bytes == (
            batch_two_reference.maximum_worker_bytes
        )
        assert result.boundary_summary_array_bytes == (
            batch_two_reference.boundary_summary_array_bytes
        )
        assert result.maximum_task_summary_array_bytes == (
            batch_two_reference.maximum_task_summary_array_bytes
        )
        assert result.published_product_shard_count == (
            batch_two_reference.published_product_shard_count
        )


def test_multiscale_science_and_topology_ids_are_partition_invariant(
    tmp_path: Path,
) -> None:
    """Different tile layouts retain science and global topology identity."""
    background = _background_source(tmp_path / "background")
    one_manifest = _manifest((129, 137))
    many_manifest = _manifest((61, 67))
    one_result, one_source = _run(
        tmp_path / "one",
        manifest=one_manifest,
        background_source=background,
        executor=SerialExecutor(),
        tiles_per_batch=1,
    )
    many_result, many_source = _run(
        tmp_path / "many",
        manifest=many_manifest,
        background_source=background,
        executor=SerialExecutor(),
        tiles_per_batch=2,
    )

    assert one_result.generation.partition_manifest != (
        many_result.generation.partition_manifest
    )
    bounds = ImageBounds(0, 129, 0, 137)
    for product_name in phase_five_multiscale_product_names():
        one = one_source.read_completed_window(product_name, bounds)
        many = many_source.read_completed_window(product_name, bounds)
        if one.dtype == np.dtype(np.bool_):
            np.testing.assert_array_equal(many, one)
        else:
            np.testing.assert_allclose(
                np.asarray(many, dtype=np.float64),
                np.asarray(one, dtype=np.float64),
                rtol=2e-13,
                atol=2e-13,
                equal_nan=True,
            )
    _assert_science_identity_equal(
        _science_identity(many_result, many_source),
        _science_identity(one_result, one_source),
    )


def test_multiscale_stage_matches_promoted_one_tile_science(
    tmp_path: Path,
) -> None:
    """Reconciled products reproduce the frozen serial scientific oracle."""
    image, valid, background, rms = _planes()
    manifest = _manifest((129, 137))
    result, source = _run(
        tmp_path / "stage",
        manifest=manifest,
        background_source=_background_source(tmp_path / "background"),
        executor=SerialExecutor(),
        tiles_per_batch=1,
    )
    tile = manifest.tiles[0]
    filtered = evaluate_phase_five_filter_tile(
        prepare_scale_filter_inputs(image, valid, background, rms),
        partition=tile,
        image_shape_yx=manifest.image_shape_yx,
        beam=_beam(),
        minimum_support_fraction=_SUPPORT_FRACTION,
    )
    oracle = detect_residual_multiscale_islands(
        filtered.prepared_inputs,
        filtered.matched_filter,
        filtered.atrous_result,
        _beam(),
        _detection_config(),
    )
    bounds = tile.core_bounds

    np.testing.assert_array_equal(
        _bool_window(source, "retained-mask", bounds),
        oracle.retained_mask,
    )
    np.testing.assert_array_equal(
        _bool_window(source, "reconstruction-mask", bounds),
        oracle.reconstruction.support_mask,
    )
    np.testing.assert_allclose(
        _float_window(source, "combined-snr", bounds),
        oracle.combined_snr,
        rtol=2e-13,
        atol=2e-13,
    )
    np.testing.assert_allclose(
        _float_window(source, "reconstructed-signal", bounds),
        oracle.reconstruction.signal_jy_per_beam,
        rtol=2e-13,
        atol=2e-13,
    )
    np.testing.assert_allclose(
        _float_window(source, "position-signal", bounds),
        filtered.prepared_inputs.residual_jy_per_beam
        + oracle.reconstruction.signal_jy_per_beam,
        rtol=2e-13,
        atol=2e-13,
    )
    for order, significant in enumerate(
        oracle.reconstruction.significant_scale_masks,
        start=1,
    ):
        np.testing.assert_array_equal(
            _bool_window(source, f"scale-{order}-significant", bounds),
            significant & oracle.reconstruction.support_mask,
        )
    assert result.detection_islands
    assert result.reconstruction_islands


@pytest.mark.parametrize("maximum_tiles_per_batch", [0, True])
def test_multiscale_stage_rejects_invalid_batch_size_before_writes(
    maximum_tiles_per_batch: int,
) -> None:
    """Batching must have one explicit positive bounded task size."""
    with pytest.raises(ValueError, match="maximum_tiles_per_batch"):
        PhaseFiveMultiscaleStageConfig(
            beam=_beam(),
            detection=_detection_config(),
            maximum_tiles_per_batch=maximum_tiles_per_batch,
        )


def test_multiscale_stage_requires_exact_filter_halo(tmp_path: Path) -> None:
    """A stage cannot dispatch a manifest with incomplete filter reads."""
    image, valid, _, _ = _planes()
    manifest = plan_image_partitions(
        image_shape_yx=image.shape,
        tile_core_shape_yx=(61, 67),
        halo_yx=(13, 13),
    )
    sink = ZarrProductSink(
        tmp_path / "output",
        manifest,
        generation_id="invalid-halo",
    )

    with pytest.raises(ValueError, match="exact widest filter halo"):
        run_phase_five_multiscale_stage(
            _ArrayImageSource(image, valid),
            _background_source(tmp_path / "background"),
            manifest,
            config=PhaseFiveMultiscaleStageConfig(
                beam=_beam(),
                detection=_detection_config(),
                maximum_tiles_per_batch=1,
            ),
            executor=SerialExecutor(),
            sink=sink,
        )
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize(
    ("failure", "message"),
    (("bounds", "different filter-read bounds"), ("shape", "misaligned")),
)
def test_multiscale_stage_rejects_invalid_image_windows(
    tmp_path: Path,
    failure: str,
    message: str,
) -> None:
    """Worker reads fail before malformed science can be published."""
    image, valid, _, _ = _planes()
    manifest = _manifest((129, 137))
    sink = ZarrProductSink(
        tmp_path / "output",
        manifest,
        generation_id="invalid-window",
    )

    with pytest.raises(ValueError, match=message):
        run_phase_five_multiscale_stage(
            _InvalidImageSource(image, valid, failure=failure),
            _background_source(tmp_path / "background"),
            manifest,
            config=PhaseFiveMultiscaleStageConfig(
                beam=_beam(),
                detection=_detection_config(),
                maximum_tiles_per_batch=1,
            ),
            executor=SerialExecutor(),
            sink=sink,
        )


def test_multiscale_stage_rejects_noncomposable_generations(
    tmp_path: Path,
) -> None:
    """Output, image-shape, and Phase 2 product identities fail closed."""
    image, valid, _, _ = _planes()
    manifest = _manifest((61, 67))
    config = PhaseFiveMultiscaleStageConfig(
        beam=_beam(),
        detection=_detection_config(),
        maximum_tiles_per_batch=1,
    )
    wrong_sink = ZarrProductSink(
        tmp_path / "wrong-sink",
        _manifest((129, 137)),
        generation_id="wrong-sink",
    )
    with pytest.raises(ValueError, match="sink must use"):
        run_phase_five_multiscale_stage(
            _ArrayImageSource(image, valid),
            _background_source(tmp_path / "background-a"),
            manifest,
            config=config,
            executor=SerialExecutor(),
            sink=wrong_sink,
        )

    for name, background, message in (
        (
            "wrong-shape",
            _background_source(
                tmp_path / "background-b",
                image_shape_yx=(128, 137),
            ),
            "match the filter image shape",
        ),
        (
            "missing-rms",
            _background_source(
                tmp_path / "background-c",
                product_names=("background",),
            ),
            "publish background and rms",
        ),
    ):
        sink = ZarrProductSink(
            tmp_path / name,
            manifest,
            generation_id=name,
        )
        with pytest.raises(ValueError, match=message):
            run_phase_five_multiscale_stage(
                _ArrayImageSource(image, valid),
                background,
                manifest,
                config=config,
                executor=SerialExecutor(),
                sink=sink,
            )


@pytest.mark.parametrize(
    ("executor", "message"),
    (
        (_EmptyExecutor(), "no Phase 5 topology results"),
        (_EmptySecondPassExecutor(), "no Phase 5 publication results"),
    ),
)
def test_multiscale_stage_rejects_missing_executor_results(
    tmp_path: Path,
    executor: object,
    message: str,
) -> None:
    """A dropped first- or second-pass result cannot publish a generation."""
    image, valid, _, _ = _planes()
    manifest = _manifest((129, 137))
    sink = ZarrProductSink(
        tmp_path / "output",
        manifest,
        generation_id="missing-executor-result",
    )

    with pytest.raises(ValueError, match=message):
        run_phase_five_multiscale_stage(
            _ArrayImageSource(image, valid),
            _background_source(tmp_path / "background"),
            manifest,
            config=PhaseFiveMultiscaleStageConfig(
                beam=_beam(),
                detection=_detection_config(),
                maximum_tiles_per_batch=1,
            ),
            executor=executor,  # type: ignore[arg-type]
            sink=sink,
        )
