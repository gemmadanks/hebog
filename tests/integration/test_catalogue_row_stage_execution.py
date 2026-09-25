# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Per-segment catalogue rows, against the whole-plane builder."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
from math import ceil, log, pi
from pathlib import Path
from typing import TypeVar, cast

import numpy as np
import numpy.typing as npt
import pytest
from astropy.io import fits
from distributed import Client
from scipy.ndimage import label as ndimage_label

from hebog.algorithms.partitioning import plan_image_partitions
from hebog.data_models.images import RestoringBeam
from hebog.data_models.partitioning import ImageBounds, PartitionManifest
from hebog.executors import DaskExecutor, SerialExecutor, TaskRequirement
from hebog.io.zarr import ZarrProductSink
from hebog.science.catalogues import (
    build_hebog_segment_moment_catalogue,
    segment_local_rms,
)
from hebog.stages.catalogue_rows import (
    SegmentRowStageConfig,
    SegmentRowStageResult,
    _CoreBatch,
    _RowBatch,
    _shaped_rows,
    run_segment_row_stage,
    segment_row_product_names,
)
from hebog.validation.tiled_detection import ArrayImageSource

pytestmark = pytest.mark.integration

_Input = TypeVar("_Input")
_Output = TypeVar("_Output")
_SHAPE_YX = (72, 104)
_BEAM_MAJOR = 4.0
_BEAM_MINOR = 3.0
_APERTURE_BEAMS = 1.5


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
        "tuple[npt.NDArray[np.int32], int]",
        ndimage_label(mask, structure=np.ones((3, 3), dtype=np.int8)),
    )
    return labels


def _planes() -> tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.bool_],
    npt.NDArray[np.int32],
]:
    """Return the image, background, validity and segment labels.

    Four segments, two of them close enough that their reviewed apertures
    compete for the pixels between them, and every one large enough to span
    more than one core.
    """
    yy, xx = np.mgrid[: _SHAPE_YX[0], : _SHAPE_YX[1]]
    image = (
        14.0 * np.exp(-0.5 * (((xx - 30) / 3.0) ** 2 + ((yy - 34) / 3.0) ** 2))
        + 13.0
        * np.exp(-0.5 * (((xx - 44) / 3.0) ** 2 + ((yy - 34) / 3.0) ** 2))
        + 11.0
        * np.exp(-0.5 * (((xx - 86) / 3.0) ** 2 + ((yy - 16) / 3.0) ** 2))
        + 9.0
        * np.exp(-0.5 * (((xx - 20) / 3.0) ** 2 + ((yy - 60) / 3.0) ** 2))
    )
    background = np.zeros(_SHAPE_YX, dtype=np.float64)
    valid = np.ones(_SHAPE_YX, dtype=np.bool_)
    return image, background, valid, _labelled(image >= 5.0)


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
    header["BMAJ"] = _BEAM_MAJOR / 3600.0
    header["BMIN"] = _BEAM_MINOR / 3600.0
    header["BPA"] = 0.0
    return header


def _beam() -> RestoringBeam:
    """Return the restoring beam the fixture header declares."""
    return RestoringBeam(
        major_fwhm_degrees=_BEAM_MAJOR / 3600.0,
        minor_fwhm_degrees=_BEAM_MINOR / 3600.0,
        position_angle_degrees=0.0,
    )


def _beam_area_pixels() -> float:
    """Return the beam area the whole-plane builder divides flux by."""
    return 2.0 * pi / (8.0 * log(2.0)) * _BEAM_MAJOR * _BEAM_MINOR


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


def _rms() -> npt.NDArray[np.float64]:
    """Return one local-noise plane that varies across the image.

    A constant plane would make every segment quote the same noise, so the
    estimate rises with x and one blanked column carries none at all.
    """
    _, xx = np.mgrid[: _SHAPE_YX[0], : _SHAPE_YX[1]]
    rms = 1.0 + 0.01 * np.asarray(xx, dtype=np.float64)
    rms[:, 30] = np.nan
    rms[:, 44] = -1.0
    return rms


def _sources(
    root: Path,
    rms: npt.NDArray[np.float64] | None = None,
) -> tuple[ZarrProductSink, ...]:
    """Publish every generation the row rounds read."""
    root.mkdir(parents=True, exist_ok=True)
    image, background, valid, labels = _planes()
    return (
        _publish(
            root / "background.zarr",
            (
                ("background", background, "<f8"),
                ("rms", _rms() if rms is None else rms, "<f8"),
            ),
            generation_id="background-fixture",
        ),
        _publish(
            root / "detection.zarr",
            (
                ("valid-pixels", valid, "bool"),
                ("position-signal", image, "<f8"),
            ),
            generation_id="detection-fixture",
        ),
        _publish(
            root / "labels.zarr",
            (("segment-labels", labels, "<i4"),),
            generation_id="label-fixture",
        ),
    )


def _config(**overrides: object) -> SegmentRowStageConfig:
    """Return the row configuration with one field replaced."""
    fields: dict[str, object] = {
        "label_product_name": "segment-labels",
        "centroid_product_name": "segment-labels",
        "aperture_radius_pixels": ceil(_APERTURE_BEAMS * _BEAM_MAJOR),
        "aperture_tie_policy": "nearest-support",
        "beam_area_pixels": _beam_area_pixels(),
        "denoised_position_maximum_peak_to_mean_ratio": 3.0,
        "with_position_diagnostics": False,
        "maximum_tiles_per_batch": 2,
        "maximum_objects_per_batch": 2,
        "maximum_batch_read_pixels": 65536,
        **overrides,
    }
    return SegmentRowStageConfig(**fields)  # type: ignore[arg-type]


def _run(
    root: Path,
    *,
    core: int = 16,
    executor: object | None = None,
    header: fits.Header | None = None,
    rms: npt.NDArray[np.float64] | None = None,
    **overrides: object,
) -> SegmentRowStageResult:
    """Measure every segment's row, in isolation."""
    background, detection, labels = _sources(root, rms)
    image, _, valid, _ = _planes()
    manifest = _manifest(core)
    return run_segment_row_stage(
        ArrayImageSource(image, valid),
        background,
        detection,
        labels,
        labels,
        detection,
        manifest,
        config=_config(**overrides),
        wcs_header_text=(_header() if header is None else header).tostring(),
        beam=_beam(),
        executor=SerialExecutor() if executor is None else executor,  # type: ignore[arg-type]
        sink=ZarrProductSink(
            root / f"rows-{core}.zarr", manifest, generation_id="rows"
        ),
    )


def _whole_plane(**overrides: object):
    """Measure every segment over complete planes, as the serial oracle."""
    image, background, valid, labels = _planes()
    return build_hebog_segment_moment_catalogue(
        image,
        background,
        valid,
        labels,
        _header(),
        beam_major_fwhm_pixels=_BEAM_MAJOR,
        beam_minor_fwhm_pixels=_BEAM_MINOR,
        measurement_aperture_radius_beams=_APERTURE_BEAMS,
        position_signal_jy_per_beam=image,
        **overrides,  # type: ignore[arg-type]
    )


def test_published_rows_match_the_whole_plane_catalogue(
    tmp_path: Path,
) -> None:
    """One segment per task reproduces the whole-plane catalogue exactly."""
    expected = _whole_plane()

    result = _run(tmp_path / "run")

    assert len(expected) > 1, "the fixture must measure several segments"
    assert result.segment_count >= len(expected)
    assert result.rows == expected


def test_the_canonical_source_policy_and_diagnostics_also_match(
    tmp_path: Path,
) -> None:
    """The source-row variant reproduces its whole-plane builder too."""
    diagnostics: dict[int, object] = {}
    expected = _whole_plane(
        aperture_tie_policy="canonical-source",
        position_diagnostics=diagnostics,
    )

    result = _run(
        tmp_path / "run",
        aperture_tie_policy="canonical-source",
        with_position_diagnostics=True,
    )

    assert diagnostics, "the fixture must record position diagnostics"
    assert result.rows == expected
    assert dict(result.position_diagnostics) == diagnostics


def test_published_local_rms_matches_the_whole_plane_estimate(
    tmp_path: Path,
) -> None:
    """Each segment's noise comes from the pixels it owns, not its aperture.

    The row round reads the estimate with the window it already measures in,
    so the noise a catalogue row quotes is the median over that segment's own
    support, ignoring pixels with no finite positive estimate.
    """
    _, _, _, labels = _planes()
    expected = {
        label_value: segment_local_rms(_rms(), labels, label_value=label_value)
        for label_value in sorted(
            int(value) for value in np.unique(labels) if value > 0
        )
    }

    result = _run(tmp_path / "run")

    assert len(expected) > 1, "the fixture must measure several segments"
    assert all(value is not None for value in expected.values())
    assert dict(result.local_rms_by_label) == expected
    assert len({*expected.values()}) == len(expected), (
        "the fixture's segments must not share one noise estimate"
    )


def test_a_segment_owning_no_usable_estimate_quotes_no_noise(
    tmp_path: Path,
) -> None:
    """An unusable estimate over a segment's whole support reports nothing."""
    result = _run(tmp_path / "run", rms=np.zeros(_SHAPE_YX, dtype=np.float64))

    assert result.rows, "the fixture must still measure its rows"
    assert dict(result.local_rms_by_label) == {}


@pytest.mark.parametrize("core", [16, 24, 72])
def test_rows_are_partition_and_batch_invariant(
    tmp_path: Path, core: int
) -> None:
    """Tile geometry and batching decide which task runs, not the rows."""
    reference = _run(tmp_path / "reference", core=72)

    result = _run(
        tmp_path / f"core-{core}",
        core=core,
        maximum_tiles_per_batch=1,
        maximum_objects_per_batch=1,
        maximum_batch_read_pixels=1,
    )

    assert result.rows == reference.rows
    assert result.local_rms_by_label == reference.local_rms_by_label


def test_rows_are_executor_invariant(tmp_path: Path) -> None:
    """Workers measure exactly what one in-process reference measures."""
    reference = _run(tmp_path / "reference")

    with Client(
        processes=False,
        n_workers=2,
        threads_per_worker=1,
        dashboard_address=None,
    ) as client:
        result = _run(tmp_path / "dask", executor=DaskExecutor(client))

    assert result.rows == reference.rows
    assert result.local_rms_by_label == reference.local_rms_by_label


def test_the_row_stage_publishes_canonical_products(tmp_path: Path) -> None:
    """The generation carries exactly one aperture chunk per core."""
    result = _run(tmp_path / "run")

    assert segment_row_product_names() == ("aperture-labels",)
    assert set(result.generation.product_names) == {"aperture-labels"}
    assert len(result.generation.chunks) == len(_manifest(16).tiles)
    assert result.partition_count == len(_manifest(16).tiles)
    assert result.measured_segment_count == len(result.rows)
    # Two core rounds at two tiles a batch, plus the row round.
    core_batches = ceil(result.partition_count / 2)
    assert result.executor_task_count > 2 * core_batches
    assert result.maximum_graph_width > 0
    assert result.maximum_segment_read_pixels > 0


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"maximum_tiles_per_batch": 0}, "maximum_tiles_per_batch"),
        ({"maximum_objects_per_batch": 0}, "maximum_objects_per_batch"),
        ({"maximum_batch_read_pixels": True}, "maximum_batch_read_pixels"),
        ({"aperture_radius_pixels": -1}, "aperture_radius_pixels"),
        ({"aperture_tie_policy": "nearest"}, "tie policy is unsupported"),
    ],
)
def test_the_row_stage_rejects_invalid_configuration(
    overrides: dict[str, object], message: str
) -> None:
    """Configuration is validated before any product is initialized."""
    with pytest.raises(ValueError, match=message):
        _config(**overrides)


def test_the_row_rounds_forbid_empty_executor_work_records() -> None:
    """An empty batch is a scheduling defect, not a task to submit."""
    with pytest.raises(ValueError, match="segment core batch must not be"):
        _CoreBatch(partitions=())
    with pytest.raises(ValueError, match="segment row batch must not be"):
        _RowBatch(segments=(), read_bounds=ImageBounds(0, 1, 0, 1))


@pytest.mark.parametrize(
    "dropped_round, message",
    [
        (1, "no segment aperture results"),
        (2, "no segment window results"),
        (3, "no segment row results"),
    ],
)
def test_every_row_round_fails_closed_on_a_silent_executor(
    tmp_path: Path, dropped_round: int, message: str
) -> None:
    """A dropped result is never published as a complete catalogue."""
    with pytest.raises(ValueError, match=message):
        _run(
            tmp_path / f"round-{dropped_round}",
            executor=_DropNthMapExecutor(dropped_round),
        )


def test_the_row_stage_requires_matching_sinks_and_generations(
    tmp_path: Path,
) -> None:
    """Identities are checked before any product is initialized."""
    background, detection, labels = _sources(tmp_path / "run")
    image, _, valid, _ = _planes()
    manifest = _manifest(16)
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
        target: PartitionManifest,
        *,
        label_source: ZarrProductSink = labels,
        sink_manifest: PartitionManifest | None = None,
        name: str = "rows",
    ) -> None:
        run_segment_row_stage(
            ArrayImageSource(image, valid),
            background,
            detection,
            label_source,
            label_source,
            detection,
            target,
            config=_config(),
            wcs_header_text=_header().tostring(),
            beam=_beam(),
            executor=SerialExecutor(),
            sink=ZarrProductSink(
                tmp_path / f"{name}.zarr",
                target if sink_manifest is None else sink_manifest,
                generation_id=name,
            ),
        )

    with pytest.raises(ValueError, match="must use the stage manifest"):
        run(manifest, sink_manifest=other_shape, name="mismatched")
    with pytest.raises(ValueError, match="cores without a halo"):
        run(haloed, name="haloed")
    with pytest.raises(ValueError, match="match the segment image shape"):
        run(other_shape, name="other")
    with pytest.raises(ValueError, match="every segment plane read"):
        run(manifest, label_source=background, name="incomplete")


def test_an_image_with_no_segment_publishes_an_empty_catalogue(
    tmp_path: Path,
) -> None:
    """An image whose labels are empty measures no row and writes cores."""
    root = tmp_path / "run"
    root.mkdir(parents=True, exist_ok=True)
    image, background_plane, valid, _ = _planes()
    background = _publish(
        root / "background.zarr",
        (
            ("background", background_plane, "<f8"),
            ("rms", _rms(), "<f8"),
        ),
        generation_id="background-fixture",
    )
    detection = _publish(
        root / "detection.zarr",
        (
            ("valid-pixels", valid, "bool"),
            ("position-signal", image, "<f8"),
        ),
        generation_id="detection-fixture",
    )
    labels = _publish(
        root / "labels.zarr",
        (("segment-labels", np.zeros(_SHAPE_YX, dtype=np.int32), "<i4"),),
        generation_id="label-fixture",
    )
    manifest = _manifest(16)

    result = run_segment_row_stage(
        ArrayImageSource(image, valid),
        background,
        detection,
        labels,
        labels,
        detection,
        manifest,
        config=_config(),
        wcs_header_text=_header().tostring(),
        beam=_beam(),
        executor=SerialExecutor(),
        sink=ZarrProductSink(
            root / "rows.zarr", manifest, generation_id="rows"
        ),
    )

    assert result.segment_count == 0
    assert result.rows == ()
    assert dict(result.local_rms_by_label) == {}
    assert result.maximum_segment_read_pixels == 0
    assert len(result.generation.chunks) == len(manifest.tiles)


class _ShiftedBoundsSource:
    """An image source that answers with bounds it was not asked for."""

    def __init__(self, source: ArrayImageSource) -> None:
        """Retain the source whose honest answers are then corrupted."""
        self._source = source

    def read_window(self, bounds: ImageBounds):
        """Return the asked-for pixels under one narrower bound."""
        window = self._source.read_window(bounds)
        return replace(
            window,
            bounds=ImageBounds(
                bounds.y_start,
                bounds.y_stop,
                bounds.x_start,
                max(bounds.x_start + 1, bounds.x_stop - 1),
            ),
        )


def test_a_read_that_answers_different_bounds_fails_closed(
    tmp_path: Path,
) -> None:
    """A segment is never measured from pixels it did not ask for."""
    background, detection, labels = _sources(tmp_path / "run")
    image, _, valid, _ = _planes()
    manifest = _manifest(16)

    with pytest.raises(ValueError, match="different segment bounds"):
        run_segment_row_stage(
            _ShiftedBoundsSource(ArrayImageSource(image, valid)),
            background,
            detection,
            labels,
            labels,
            detection,
            manifest,
            config=_config(),
            wcs_header_text=_header().tostring(),
            beam=_beam(),
            executor=SerialExecutor(),
            sink=ZarrProductSink(
                tmp_path / "shifted.zarr", manifest, generation_id="shifted"
            ),
        )


def test_an_unmeasurable_segment_publishes_no_row(tmp_path: Path) -> None:
    """A segment whose pixels are all invalid keeps its label and no row.

    The whole-plane builder skips it for the same reason, so the two agree
    on a catalogue shorter than the label set.
    """
    root = tmp_path / "run"
    root.mkdir(parents=True, exist_ok=True)
    image, background_plane, valid, labels_plane = _planes()
    hidden = int(labels_plane[60, 20])
    assert hidden > 0
    masked = valid & (labels_plane != hidden)
    background = _publish(
        root / "background.zarr",
        (
            ("background", background_plane, "<f8"),
            ("rms", _rms(), "<f8"),
        ),
        generation_id="background-fixture",
    )
    detection = _publish(
        root / "detection.zarr",
        (
            ("valid-pixels", masked, "bool"),
            ("position-signal", image, "<f8"),
        ),
        generation_id="detection-fixture",
    )
    labels = _publish(
        root / "labels.zarr",
        (("segment-labels", labels_plane, "<i4"),),
        generation_id="label-fixture",
    )
    manifest = _manifest(16)

    result = run_segment_row_stage(
        ArrayImageSource(image, masked),
        background,
        detection,
        labels,
        labels,
        detection,
        manifest,
        config=_config(),
        wcs_header_text=_header().tostring(),
        beam=_beam(),
        executor=SerialExecutor(),
        sink=ZarrProductSink(
            root / "rows.zarr", manifest, generation_id="rows"
        ),
    )

    expected = build_hebog_segment_moment_catalogue(
        image,
        background_plane,
        masked,
        labels_plane,
        _header(),
        beam_major_fwhm_pixels=_BEAM_MAJOR,
        beam_minor_fwhm_pixels=_BEAM_MINOR,
        measurement_aperture_radius_beams=_APERTURE_BEAMS,
        position_signal_jy_per_beam=image,
    )
    assert len(expected) < int(labels_plane.max())
    assert result.measured_segment_count < result.segment_count
    assert result.rows == expected


def test_a_batch_reports_the_rows_one_segment_at_a_time_would(
    tmp_path: Path,
) -> None:
    """Converting a batch together must not change what it reports.

    A row's coordinate belongs at its own position estimate and its shape's
    geometry at its own moment centroid, and a batch converts every one of
    both in one call. That is only sound while each segment still receives
    what its own centroids earn, whatever else is in the batch with it.
    """
    reference = _run(tmp_path / "one-at-a-time", maximum_objects_per_batch=1)

    batched = _run(tmp_path / "together", maximum_objects_per_batch=64)

    assert len(reference.rows) > 1, "the fixture must hold several segments"
    assert batched.rows == reference.rows


def test_a_geometry_the_wcs_cannot_give_leaves_every_shape_unavailable(
    tmp_path: Path,
) -> None:
    """An unusable frame belongs to the WCS, not to one segment.

    The per-segment path reports such a segment as shape-unavailable rather
    than failing, so a batch must report every one of its segments that way
    rather than failing the task.
    """
    galactic = _header()
    galactic["CTYPE1"] = "GLON-TAN"
    galactic["CTYPE2"] = "GLAT-TAN"

    result = _run(tmp_path / "galactic", header=galactic)

    assert result.rows, "the fixture must still measure rows"
    for row in result.rows:
        assert row.fitted_shape is None
        assert row.deconvolution_status == "unavailable"
        assert "shape-unavailable" in row.quality_flags


def test_a_batch_with_no_measurable_segment_converts_nothing() -> None:
    """A batch whose segments all fail to measure must reach no conversion.

    Every segment of a batch can be unmeasurable, and an empty batch has no
    position to convert. Asking Astropy to transform nothing is not an error
    worth risking, so the batch returns before it reaches the WCS.
    """
    assert _shaped_rows((), celestial_wcs=None, beam=_beam()) == (), (
        "an empty batch must not touch the WCS"
    )
