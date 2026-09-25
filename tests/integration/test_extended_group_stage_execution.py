# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Per-feature cross-parent grouping, against the whole-plane oracle."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
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
    measure_component_models,
    reconcile_component_measurements,
)
from hebog.algorithms.component_topology import deblend_component_topology
from hebog.algorithms.multiscale import (
    BeamShapePixels,
    build_residual_atrous_plan,
)
from hebog.algorithms.partitioning import plan_image_partitions
from hebog.config import CompactDeblendConfig
from hebog.data_models.images import RestoringBeam
from hebog.data_models.partitioning import ImageBounds, PartitionManifest
from hebog.executors import DaskExecutor, SerialExecutor, TaskRequirement
from hebog.io.base import ImageWindow
from hebog.io.zarr import ZarrProductSink
from hebog.science.configuration import source_finder_configs
from hebog.stages.objects import (
    ComponentFitStageConfig,
    ExtendedGroupStageConfig,
    ExtendedGroupStageResult,
    FitParentStageConfig,
    SupportFeature,
    _feature_mask,
    _FeatureScanBatch,
    _GroupBatch,
    run_component_fit_stage,
    run_extended_group_stage,
    run_fit_parent_stage,
)
from hebog.validation.tiled_detection import ArrayImageSource

pytestmark = pytest.mark.integration

_Input = TypeVar("_Input")
_Output = TypeVar("_Output")
_SHAPE_YX = (97, 145)
_DETECTION_SIGMA = 5.0
_BEAM = BeamShapePixels(4.0, 4.0, 0.0)
_RESTORING_BEAM = RestoringBeam(4.0 / 3600.0, 4.0 / 3600.0, 0.0)


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


def _labelled(mask: npt.NDArray[np.bool_]) -> npt.NDArray[np.int32]:
    """Return eight-connected labels of one analytic mask."""
    labels, _ = cast(
        "tuple[npt.NDArray[np.int32], int]",
        ndimage_label(mask, structure=np.ones((3, 3), dtype=np.int8)),
    )
    return labels


def _signal() -> npt.NDArray[np.float64]:
    """Return two compact peaks on a broad halo, plus an isolated peak.

    The halo carries most of the flux, so the admitted compact models do not
    explain it and the emission that remains after subtracting them persists
    across adjacent scales. That is what makes the two peaks one extended
    group, and the halo spans many tile cores, which is what makes the
    per-feature round necessary.
    """
    yy, xx = np.mgrid[: _SHAPE_YX[0], : _SHAPE_YX[1]]
    return (
        12.0 * np.exp(-0.5 * (((xx - 42) / 2.0) ** 2 + ((yy - 48) / 2.0) ** 2))
        + 12.0
        * np.exp(-0.5 * (((xx - 58) / 2.0) ** 2 + ((yy - 48) / 2.0) ** 2))
        + 6.0
        * np.exp(-0.5 * (((xx - 50) / 14.0) ** 2 + ((yy - 48) / 7.0) ** 2))
        + 9.0 * np.exp(-((yy - 16) ** 2 + (xx - 126) ** 2) / 8.0)
    )


def _planes() -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.bool_],
    npt.NDArray[np.int32],
    npt.NDArray[np.int32],
]:
    """Return the residual, RMS and deblended component planes."""
    signal = _signal()
    valid = np.ones(_SHAPE_YX, dtype=np.bool_)
    direct = np.zeros(_SHAPE_YX, dtype=np.int32)
    measurement = np.zeros(_SHAPE_YX, dtype=np.int32)
    labelled = _labelled(signal >= 3.0)
    for index, value in enumerate(
        sorted({int(item) for item in np.unique(labelled) if item}), start=1
    ):
        direct[labelled == value] = index
    support = _labelled(signal >= 2.0)
    for value in np.unique(support):
        if value <= 0:
            continue
        region = support == value
        owners = {int(item) for item in np.unique(direct[region]) if item}
        if len(owners) == 1:
            measurement[region] = owners.pop()
    measurement[direct > 0] = direct[direct > 0]
    topology = deblend_component_topology(
        np.where(valid, signal, np.nan),
        direct,
        measurement,
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


def _deblend_config() -> CompactDeblendConfig:
    """Return the reviewed compact deblending policy the public path uses."""
    return replace(
        source_finder_configs()[1],
        minimum_peak_signal_to_noise=float(
            np.nextafter(_DETECTION_SIGMA, -np.inf)
        ),
    )


def _fit_config() -> tuple[object, object]:
    """Return the reviewed moment and fit policy the public path uses."""
    _, _, moment_config, fit_config, _ = source_finder_configs()
    return moment_config, replace(
        fit_config, integrated_flux_bias_correction_sigma=0.0
    )


def _header() -> fits.Header:
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


def _atrous_plan() -> object:
    """Return the reviewed residual à trous plan for the fixture beam."""
    return build_residual_atrous_plan(_BEAM, noise_correlation=_BEAM)


def _manifest(core: int) -> PartitionManifest:
    """Plan one core-only partition of the fixture image."""
    return plan_image_partitions(
        image_shape_yx=_SHAPE_YX,
        tile_core_shape_yx=(core, core),
        halo_yx=(0, 0),
    )


def _publish(
    root: Path,
    products: tuple[tuple[str, npt.NDArray[np.generic], str], ...],
    *,
    generation_id: str,
) -> ZarrProductSink:
    """Publish one generation of analytic planes over 16-pixel cores."""
    manifest = _manifest(16)
    sink = ZarrProductSink(root, manifest, generation_id=generation_id)
    for product_name, _, dtype in products:
        sink.initialize_product(
            product_name=product_name, dtype=np.dtype(dtype)
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


@dataclass(frozen=True, slots=True)
class _Published:
    """Everything the fit rounds published, for the grouping round."""

    parents: tuple[object, ...]
    support_sink: ZarrProductSink
    background_source: ZarrProductSink
    detection_source: ZarrProductSink
    component_source: ZarrProductSink


def _run_fits(root: Path) -> _Published:
    """Publish the measurement support the grouping round reads."""
    root.mkdir(parents=True, exist_ok=True)
    residual, rms, valid, direct, measurement = _planes()
    background_source = _publish(
        root / "background.zarr",
        (
            ("background", np.zeros(_SHAPE_YX, dtype=np.float64), "<f8"),
            ("rms", rms, "<f8"),
        ),
        generation_id="background-fixture",
    )
    detection_source = _publish(
        root / "detection.zarr",
        (("valid-pixels", valid, "bool"),),
        generation_id="detection-fixture",
    )
    component_source = _publish(
        root / "components.zarr",
        (
            ("component-direct-labels", direct, "<i4"),
            ("component-measurement-labels", measurement, "<i4"),
        ),
        generation_id="component-fixture",
    )
    moment_config, fit_config = _fit_config()
    margin = int(fit_config.context_margin_pixels)  # type: ignore[attr-defined]
    side = max(32, 4 * margin + 1)
    parent_manifest = plan_image_partitions(
        image_shape_yx=_SHAPE_YX,
        tile_core_shape_yx=(side, side),
        halo_yx=(margin, margin),
    )
    parent_sink = ZarrProductSink(
        root / "fit-parents.zarr", parent_manifest, generation_id="parents"
    )
    run_fit_parent_stage(
        component_source,
        parent_manifest,
        config=FitParentStageConfig(
            context_margin_pixels=margin, maximum_tiles_per_batch=2
        ),
        executor=SerialExecutor(),
        sink=parent_sink,
    )
    manifest = _manifest(32)
    support_sink = ZarrProductSink(
        root / "fits.zarr", manifest, generation_id="fits"
    )
    result = run_component_fit_stage(
        ArrayImageSource(residual, valid),
        background_source,
        detection_source,
        component_source,
        parent_sink,
        manifest,
        config=ComponentFitStageConfig(
            moment=moment_config,  # type: ignore[arg-type]
            fit=fit_config,  # type: ignore[arg-type]
            atrous_plan=_atrous_plan(),  # type: ignore[arg-type]
            detection_sigma=_DETECTION_SIGMA,
            island_sigma=3.0,
            minimum_pixels=7,
            maximum_bounds_pixels=(
                _deblend_config().maximum_compact_bounds_pixels
            ),
            minimum_support_fraction=0.5,
            maximum_tiles_per_batch=2,
            maximum_batch_read_pixels=65536,
        ),
        wcs_header_text=_header().tostring(),
        beam=_RESTORING_BEAM,
        executor=SerialExecutor(),
        sink=support_sink,
    )
    return _Published(
        parents=result.parents,
        support_sink=support_sink,
        background_source=background_source,
        detection_source=detection_source,
        component_source=component_source,
    )


def _group_config(**overrides: object) -> ExtendedGroupStageConfig:
    """Return the grouping configuration with one field replaced."""
    fields: dict[str, object] = {
        "atrous_plan": _atrous_plan(),
        "detection_sigma": _DETECTION_SIGMA,
        "island_sigma": 3.0,
        "minimum_pixels": 7,
        "maximum_bounds_pixels": (
            _deblend_config().maximum_compact_bounds_pixels
        ),
        "minimum_support_fraction": 0.5,
        "maximum_tiles_per_batch": 2,
        "maximum_batch_read_pixels": 65536,
        **overrides,
    }
    return ExtendedGroupStageConfig(**fields)  # type: ignore[arg-type]


def _run_groups(
    published: _Published,
    *,
    core: int = 16,
    executor: object | None = None,
    image_source: object | None = None,
    **overrides: object,
) -> ExtendedGroupStageResult:
    """Group every reconciled support feature, in isolation."""
    residual, _, valid, _, _ = _planes()
    return run_extended_group_stage(
        ArrayImageSource(residual, valid)
        if image_source is None
        else image_source,  # type: ignore[arg-type]
        published.background_source,
        published.detection_source,
        published.component_source,
        published.support_sink,
        _manifest(core),
        config=_group_config(**overrides),
        parents=published.parents,  # type: ignore[arg-type]
        wcs_header_text=_header().tostring(),
        beam=_RESTORING_BEAM,
        executor=SerialExecutor() if executor is None else executor,  # type: ignore[arg-type]
    )


def _reconciled(
    published: _Published, groups: ExtendedGroupStageResult
) -> ComponentMeasurements:
    """Reduce the published parent and feature records, as the public path."""
    return reconcile_component_measurements(
        parents=published.parents,  # type: ignore[arg-type]
        features=groups.features,
    )


def _whole_plane() -> ComponentMeasurements:
    """Measure and group over complete planes, as the serial oracle."""
    residual, rms, valid, direct, measurement = _planes()
    moment_config, fit_config = _fit_config()
    return measure_component_models(
        residual,
        rms,
        valid,
        direct,
        measurement,
        WCS(_header(), relax=True).celestial,
        _RESTORING_BEAM,
        moment_config,  # type: ignore[arg-type]
        fit_config,  # type: ignore[arg-type]
        detection_sigma=_DETECTION_SIGMA,
        island_sigma=3.0,
        minimum_pixels=7,
        maximum_bounds_pixels=(
            _deblend_config().maximum_compact_bounds_pixels
        ),
        atrous_plan=_atrous_plan(),  # type: ignore[arg-type]
        minimum_support_fraction=0.5,
    )


def test_published_groups_match_the_whole_plane_reconciliation(
    tmp_path: Path,
) -> None:
    """One feature per task reproduces the whole-plane grouping exactly."""
    published = _run_fits(tmp_path / "run")

    groups = _run_groups(published)
    reconciled = _reconciled(published, groups)

    expected = _whole_plane()
    assert expected.extended_groups, "the fixture must group its components"
    assert expected.grouping_evidence, "the fixture must record its evidence"
    assert groups.feature_count > 1
    assert reconciled.extended_groups == expected.extended_groups
    assert reconciled.compact_groups == expected.compact_groups
    assert reconciled.grouping_evidence == expected.grouping_evidence
    assert reconciled.proposed_compact_groups == (
        expected.proposed_compact_groups
    )
    assert reconciled.fits == expected.fits


def _assert_groups_equal(
    candidate: ExtendedGroupStageResult,
    expected: ExtendedGroupStageResult,
) -> None:
    """Compare every feature's groups and evidence, in canonical order."""
    assert candidate.grouped_feature_count == expected.grouped_feature_count
    assert candidate.features == expected.features


@pytest.mark.parametrize("core", [16, 32, 97])
def test_extended_groups_are_partition_and_batch_invariant(
    tmp_path: Path, core: int
) -> None:
    """Tile geometry and batching decide which task runs, not the groups."""
    published = _run_fits(tmp_path / "run")
    reference = _run_groups(published, core=97)

    result = _run_groups(
        published,
        core=core,
        maximum_batch_read_pixels=1,
        maximum_tiles_per_batch=1,
    )

    _assert_groups_equal(result, reference)


def test_extended_groups_are_executor_invariant(tmp_path: Path) -> None:
    """Workers group exactly what one in-process reference groups."""
    published = _run_fits(tmp_path / "run")
    reference = _run_groups(published)

    with Client(
        processes=False,
        n_workers=2,
        threads_per_worker=1,
        dashboard_address=None,
    ) as client:
        result = _run_groups(published, executor=DaskExecutor(client))

    _assert_groups_equal(result, reference)


def test_grouping_publishes_scalar_execution_evidence(
    tmp_path: Path,
) -> None:
    """The stage reports the work it did without publishing a plane."""
    published = _run_fits(tmp_path / "run")

    result = _run_groups(published)

    assert result.partition_count == len(_manifest(16).tiles)
    assert result.executor_task_count > result.feature_batch_count
    assert result.maximum_graph_width > 0
    assert result.maximum_feature_read_pixels > 0
    assert result.feature_batch_count > 0
    assert result.reconciliation_round_count >= 1
    assert result.grouped_feature_count <= result.feature_count


@pytest.mark.parametrize(
    "maximum_tiles_per_batch, maximum_batch_read_pixels, message",
    [
        (0, 8192, "maximum_tiles_per_batch"),
        (2, 0, "maximum_batch_read_pixels"),
    ],
)
def test_grouping_rejects_invalid_configuration(
    maximum_tiles_per_batch: int,
    maximum_batch_read_pixels: int,
    message: str,
) -> None:
    """Configuration is validated before any round is submitted."""
    with pytest.raises(ValueError, match=message):
        _group_config(
            maximum_tiles_per_batch=maximum_tiles_per_batch,
            maximum_batch_read_pixels=maximum_batch_read_pixels,
        )


def test_grouping_rounds_forbid_empty_executor_work_records() -> None:
    """An empty batch is a scheduling defect, not a task to submit."""
    with pytest.raises(ValueError, match="feature scan batch must not be"):
        _FeatureScanBatch(partitions=())
    with pytest.raises(ValueError, match="group batch must not be empty"):
        _GroupBatch(
            features=(),
            read_bounds=ImageBounds(0, 1, 0, 1),
            fits=(),
            protected_labels=frozenset(),
        )


@pytest.mark.parametrize(
    "dropped_round, message",
    [
        (1, "no support-feature results"),
        (2, "no extended group results"),
    ],
)
def test_every_grouping_round_fails_closed_on_a_silent_executor(
    tmp_path: Path, dropped_round: int, message: str
) -> None:
    """A dropped result is never reduced as a complete grouping."""
    published = _run_fits(tmp_path / "run")

    with pytest.raises(ValueError, match=message):
        _run_groups(published, executor=_DropNthMapExecutor(dropped_round))


def test_grouping_requires_matching_generations_and_a_core_manifest(
    tmp_path: Path,
) -> None:
    """Identities are checked before any round is submitted."""
    published = _run_fits(tmp_path / "run")
    incomplete = _publish(
        tmp_path / "incomplete.zarr",
        (("rms", _planes()[1], "<f8"),),
        generation_id="incomplete",
    )
    other_shape = plan_image_partitions(
        image_shape_yx=(32, 32),
        tile_core_shape_yx=(16, 16),
        halo_yx=(0, 0),
    )
    haloed = plan_image_partitions(
        image_shape_yx=_SHAPE_YX,
        tile_core_shape_yx=(32, 32),
        halo_yx=(2, 2),
    )

    def run(
        manifest: PartitionManifest,
        *,
        background_source: ZarrProductSink | None = None,
    ) -> None:
        run_extended_group_stage(
            ArrayImageSource(_planes()[0], _planes()[2]),
            published.background_source
            if background_source is None
            else background_source,
            published.detection_source,
            published.component_source,
            published.support_sink,
            manifest,
            config=_group_config(),
            parents=published.parents,  # type: ignore[arg-type]
            wcs_header_text=_header().tostring(),
            beam=_RESTORING_BEAM,
            executor=SerialExecutor(),
        )

    with pytest.raises(ValueError, match="cores without a halo"):
        run(haloed)
    with pytest.raises(ValueError, match="match the grouping image shape"):
        run(other_shape)
    with pytest.raises(ValueError, match="every grouping plane read"):
        run(_manifest(16), background_source=incomplete)
    with pytest.raises(ValueError, match="different group-read bounds"):
        _run_groups(
            published,
            image_source=_ShiftedBoundsSource(
                ArrayImageSource(_planes()[0], _planes()[2])
            ),
        )


def test_a_feature_without_its_canonical_pixel_fails_closed() -> None:
    """A window that does not hold the feature is never silently grouped."""
    support = np.zeros((8, 8), dtype=np.bool_)
    support[2:5, 2:5] = True
    window = ImageBounds(0, 8, 0, 8)

    found = _feature_mask(
        support,
        SupportFeature(feature_label=1, first_pixel_yx=(2, 2), window=window),
    )

    np.testing.assert_array_equal(found, support)
    with pytest.raises(ValueError, match="canonical first pixel"):
        _feature_mask(
            support,
            SupportFeature(
                feature_label=1, first_pixel_yx=(0, 0), window=window
            ),
        )


def test_grouping_publishes_an_image_with_no_support_feature(
    tmp_path: Path,
) -> None:
    """An image whose support is empty reduces to no feature records."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    published = _run_fits(tmp_path / "run")
    empty = _publish(
        tmp_path / "empty.zarr",
        (
            (
                "measurement-support",
                np.zeros(_SHAPE_YX, dtype=np.bool_),
                "bool",
            ),
        ),
        generation_id="empty-support",
    )

    result = run_extended_group_stage(
        ArrayImageSource(_planes()[0], _planes()[2]),
        published.background_source,
        published.detection_source,
        published.component_source,
        empty,
        _manifest(16),
        config=_group_config(),
        parents=published.parents,  # type: ignore[arg-type]
        wcs_header_text=_header().tostring(),
        beam=_RESTORING_BEAM,
        executor=SerialExecutor(),
    )

    assert result.feature_count == 0
    assert result.grouped_feature_count == 0
    assert result.features == ()
    assert result.feature_batch_count == 0
    assert result.maximum_feature_read_pixels == 0


def test_a_feature_beyond_the_work_bound_contributes_no_grouping(
    tmp_path: Path,
) -> None:
    """A support feature wider than the reviewed bound is left ungrouped.

    The whole-plane pass skips the same feature, so the tiled rounds must
    not group what the reviewed compact work limit refuses to open.
    """
    published = _run_fits(tmp_path / "run")

    result = _run_groups(published, maximum_bounds_pixels=1)

    assert result.feature_count > 0
    assert result.grouped_feature_count == 0
    assert result.features == ()
    assert result.feature_batch_count == 0
