"""Fixture-only executor contracts for public-finder seed ownership."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, TypeAlias

import numpy as np
import numpy.typing as npt
import pytest
from distributed import Client, LocalCluster

from hebog.algorithms.extended_measurement import (
    assign_seeded_multiscale_support,
)
from hebog.algorithms.multiscale_association import ScaleDetectionPlane
from hebog.algorithms.source_association import (
    associate_components_by_multiscale_hierarchy,
    associate_detection_components,
    build_detection_component_records,
    reduce_source_associations,
)
from hebog.data_models.multiscale import ScaleDetection
from hebog.data_models.source_association import (
    DetectionComponentRecord,
    SourceAssociationResult,
)
from hebog.executors import DaskExecutor, SerialExecutor

OwnershipBatch: TypeAlias = tuple[
    npt.NDArray[np.int32],
    npt.NDArray[np.bool_],
    npt.NDArray[np.bool_],
    float,
    dict[int, tuple[int, int]],
]
AssociationBatch: TypeAlias = tuple[
    npt.NDArray[np.int32],
    tuple[DetectionComponentRecord, ...],
    tuple[int, int],
]
HierarchyBatch: TypeAlias = tuple[
    npt.NDArray[np.int32],
    tuple[DetectionComponentRecord, ...],
    tuple[ScaleDetectionPlane, ...],
    npt.NDArray[np.bool_],
]


def _own_support(batch: OwnershipBatch) -> npt.NDArray[np.int32]:
    """Apply the pure ownership kernel in a worker-safe function."""
    labels, support, valid, beam_major_fwhm_pixels, references = batch
    return assign_seeded_multiscale_support(
        labels,
        support,
        valid,
        beam_major_fwhm_pixels=beam_major_fwhm_pixels,
        canonical_seed_references_yx=references,
    )


def _fixture() -> OwnershipBatch:
    """Return two seeds joined by multiscale support and finite wings."""
    labels = np.zeros((9, 11), dtype=np.int32)
    labels[4, 1] = 9
    labels[4, 9] = 2
    support = np.zeros(labels.shape, dtype=np.bool_)
    support[4, 1:10] = True
    support[3:6, 2] = True
    support[3:6, 8] = True
    return (
        labels,
        support,
        np.ones(labels.shape, dtype=np.bool_),
        8.0,
        {9: (4, 1), 2: (4, 9)},
    )


def _partition(batch: OwnershipBatch) -> tuple[OwnershipBatch, ...]:
    """Split x cores with the exact half-beam ownership halo."""
    labels, support, valid, beam, references = batch
    return (
        (labels[:, :10], support[:, :10], valid[:, :10], beam, references),
        (labels[:, 2:], support[:, 2:], valid[:, 2:], beam, references),
    )


def _stitch(parts: list[npt.NDArray[np.int32]]) -> npt.NDArray[np.int32]:
    """Extract non-overlapping cores from the two halo-bearing results."""
    return np.concatenate((parts[0][:, :6], parts[1][:, 4:]), axis=1)


@pytest.mark.integration
def test_seed_ownership_is_serial_dask_and_partition_invariant() -> None:
    """Bridge ownership is invariant to executor and exact-halo tiling."""
    batch = _fixture()
    serial = SerialExecutor()
    expected = serial.map_batches(_own_support, (batch,))[0]
    serial_partitioned = _stitch(
        serial.map_batches(_own_support, _partition(batch))
    )
    np.testing.assert_array_equal(serial_partitioned, expected)

    cluster = LocalCluster(
        n_workers=2,
        threads_per_worker=1,
        processes=False,
        dashboard_address="",
    )
    with cluster, Client(cluster) as client:
        executor = DaskExecutor(client)
        dask_full = executor.map_batches(_own_support, (batch,))[0]
        dask_partitioned = _stitch(
            executor.map_batches(_own_support, _partition(batch))
        )

    np.testing.assert_array_equal(dask_full, expected)
    np.testing.assert_array_equal(dask_partitioned, expected)


def _associate_fixture(
    labels: npt.NDArray[np.int32],
) -> SourceAssociationResult:
    """Associate one worker-safe analytic component fixture."""
    signal = np.where(labels > 0, 1.0, 0.0)
    records = tuple(
        replace(
            item,
            covariance_pixels_squared=((1.0, 0.0), (0.0, 16.0)),
        )
        for item in build_detection_component_records(
            labels,
            signal,
            np.ones(labels.shape, dtype=np.bool_),
        )
    )
    return associate_detection_components(
        records,
        labels,
        np.ones(labels.shape, dtype=np.bool_),
        np.full(labels.shape, 4.0),
        np.ones(labels.shape, dtype=np.bool_),
        island_threshold_sigma=3.0,
    )


def _identity_view(result: SourceAssociationResult) -> tuple[Any, ...]:
    """Discard task-local integer labels from stable graph comparison."""
    return (
        tuple(
            (
                item.component_id,
                item.canonical_pixel_yx,
                item.centroid_yx,
                item.covariance_pixels_squared,
            )
            for item in result.components
        ),
        result.edges,
        result.memberships,
        result.hierarchy_diagnostics,
    )


def _associate_partition(batch: AssociationBatch) -> SourceAssociationResult:
    """Build graph evidence on one global-coordinate halo window."""
    labels, records, origin_yx = batch
    return associate_detection_components(
        records,
        labels,
        np.ones(labels.shape, dtype=np.bool_),
        np.full(labels.shape, 4.0),
        np.ones(labels.shape, dtype=np.bool_),
        island_threshold_sigma=3.0,
        origin_yx=origin_yx,
    )


@pytest.mark.integration
def test_source_association_is_serial_dask_and_label_invariant() -> None:
    """Stable records and complete-link reduction ignore scheduler labels."""
    labels = np.zeros((9, 17), dtype=np.int32)
    labels[3:6, 3:6] = 9
    labels[3:6, 11:14] = 2
    permuted = np.where(labels == 9, 31, np.where(labels == 2, 7, 0)).astype(
        np.int32
    )
    serial = SerialExecutor()
    expected, serial_permuted = serial.map_batches(
        _associate_fixture,
        (labels, permuted),
    )
    assert _identity_view(serial_permuted) == _identity_view(expected)

    cluster = LocalCluster(
        n_workers=2,
        threads_per_worker=1,
        processes=False,
        dashboard_address="",
    )
    with cluster, Client(cluster) as client:
        actual = DaskExecutor(client).map_batches(
            _associate_fixture,
            (permuted, labels),
        )

    assert [_identity_view(item) for item in actual] == [
        _identity_view(expected),
        _identity_view(expected),
    ]


@pytest.mark.integration
def test_source_association_partition_order_and_retry_invariance() -> None:
    """Overlapping association halos reduce to the one-tile graph."""
    labels = np.zeros((9, 17), dtype=np.int32)
    labels[3:6, 3:6] = 9
    labels[3:6, 11:14] = 2
    expected = _associate_fixture(labels)
    records = expected.components
    partitions: tuple[AssociationBatch, ...] = (
        (labels[:, :15], records, (0, 0)),
        (labels[:, 2:], records, (0, 2)),
    )

    serial_results = SerialExecutor().map_batches(
        _associate_partition,
        partitions,
    )
    serial = reduce_source_associations(
        records,
        tuple(edge for result in serial_results for edge in result.edges),
    )

    cluster = LocalCluster(
        n_workers=2,
        threads_per_worker=1,
        processes=False,
        dashboard_address="",
    )
    with cluster, Client(cluster) as client:
        dask_results = DaskExecutor(client).map_batches(
            _associate_partition,
            (*tuple(reversed(partitions)), partitions[0]),
        )
    dask = reduce_source_associations(
        records,
        tuple(edge for result in dask_results for edge in result.edges),
    )

    assert _identity_view(serial) == _identity_view(expected)
    assert _identity_view(dask) == _identity_view(expected)


def _hierarchy_cycle_plane(
    shape: tuple[int, int],
    pixels: tuple[tuple[int, int], ...],
    *,
    scale_order: int,
) -> ScaleDetectionPlane:
    """Build separated features whose B3 envelopes form one cycle."""
    support_labels = np.zeros(shape, dtype=np.int32)
    detections: list[ScaleDetection] = []
    for label_value, pixel in enumerate(pixels, start=1):
        support_labels[pixel] = label_value
        detections.append(
            ScaleDetection(
                detection_id=(
                    f"scale-hierarchy-{scale_order}-{pixel[0]}-{pixel[1]}"
                ),
                parent_island_id=None,
                scale_order=scale_order,
                nominal_scale_beam_fwhm=float(2 ** (scale_order - 1)),
                support_pixel_count=1,
                valid_support_fraction=1.0,
                bounds_yx=(pixel[0], pixel[0] + 1, pixel[1], pixel[1] + 1),
                canonical_pixel_yx=pixel,
                peak_response_jy_per_beam=1.0,
                peak_signal_to_noise=5.0,
                touches_image_edge=False,
            )
        )
    return ScaleDetectionPlane(
        scale_order=scale_order,
        component_labels=support_labels,
        detections=tuple(detections),
    )


def _reconstruct_hierarchy(batch: HierarchyBatch) -> SourceAssociationResult:
    """Apply common-parent reconstruction through a worker-safe boundary."""
    labels, records, planes, significant = batch
    return associate_components_by_multiscale_hierarchy(
        records,
        labels,
        planes,
        np.ones(labels.shape, dtype=np.bool_),
        significant_multiscale_support=significant,
    )


@pytest.mark.integration
def test_source_hierarchy_is_serial_dask_order_and_retry_invariant() -> None:
    """Scale-aware parent membership ignores labels, tasks, and order."""
    pixels = ((10, 20), (20, 10), (20, 30), (30, 20))
    labels = np.zeros((41, 41), dtype=np.int32)
    for label_value, pixel in zip((9, 2, 17, 4), pixels, strict=True):
        labels[pixel] = label_value
    permuted = np.zeros_like(labels)
    for label_value, pixel in zip((31, 7, 22, 13), pixels, strict=True):
        permuted[pixel] = label_value
    middle = _hierarchy_cycle_plane(
        labels.shape,
        pixels,
        scale_order=2,
    )
    coarse = _hierarchy_cycle_plane(
        labels.shape,
        tuple(reversed(pixels)),
        scale_order=3,
    )
    records = build_detection_component_records(
        labels,
        np.asarray(labels > 0, dtype=np.float64),
        np.ones(labels.shape, dtype=np.bool_),
    )
    permuted_records = build_detection_component_records(
        permuted,
        np.asarray(permuted > 0, dtype=np.float64),
        np.ones(labels.shape, dtype=np.bool_),
    )
    batches: tuple[HierarchyBatch, ...] = (
        (
            labels,
            records,
            (middle, coarse),
            np.zeros(labels.shape, dtype=np.bool_),
        ),
        (
            permuted,
            tuple(reversed(permuted_records)),
            (coarse, middle),
            np.zeros(labels.shape, dtype=np.bool_),
        ),
    )
    expected = SerialExecutor().map_batches(_reconstruct_hierarchy, batches)

    cluster = LocalCluster(
        n_workers=2,
        threads_per_worker=1,
        processes=False,
        dashboard_address="",
    )
    with cluster, Client(cluster) as client:
        actual = DaskExecutor(client).map_batches(
            _reconstruct_hierarchy,
            (*tuple(reversed(batches)), batches[0]),
        )

    expected_view = _identity_view(expected[0])
    assert _identity_view(expected[1]) == expected_view
    assert [_identity_view(item) for item in actual] == [
        expected_view,
        expected_view,
        expected_view,
    ]


@pytest.mark.integration
def test_connected_support_is_serial_dask_order_and_retry_invariant() -> None:
    """Persistent-support corroboration and telemetry are invariant."""
    pixels = ((4, 2), (4, 8), (9, 8))
    labels = np.zeros((13, 13), dtype=np.int32)
    permuted = np.zeros_like(labels)
    for value, other, pixel in zip(
        (9, 2, 17),
        (31, 7, 22),
        pixels,
        strict=True,
    ):
        labels[pixel] = value
        permuted[pixel] = other
    plane = _hierarchy_cycle_plane(labels.shape, pixels, scale_order=1)
    support = np.zeros(labels.shape, dtype=np.bool_)
    support[4, 2:9] = True
    support[4:10, 8] = True
    records = build_detection_component_records(
        labels,
        np.asarray(labels > 0, dtype=np.float64),
        np.ones(labels.shape, dtype=np.bool_),
    )
    permuted_records = build_detection_component_records(
        permuted,
        np.asarray(permuted > 0, dtype=np.float64),
        np.ones(labels.shape, dtype=np.bool_),
    )
    batches: tuple[HierarchyBatch, ...] = (
        (labels, records, (plane,), support),
        (permuted, tuple(reversed(permuted_records)), (plane,), support),
    )
    expected = SerialExecutor().map_batches(_reconstruct_hierarchy, batches)

    cluster = LocalCluster(
        n_workers=2,
        threads_per_worker=1,
        processes=False,
        dashboard_address="",
    )
    with cluster, Client(cluster) as client:
        actual = DaskExecutor(client).map_batches(
            _reconstruct_hierarchy,
            (*tuple(reversed(batches)), batches[0]),
        )

    expected_view = _identity_view(expected[0])
    assert _identity_view(expected[1]) == expected_view
    assert [_identity_view(item) for item in actual] == [
        expected_view,
        expected_view,
        expected_view,
    ]
    diagnostics = expected[0].hierarchy_diagnostics
    assert diagnostics is not None
    assert diagnostics.connected_support_candidate_count == 1
    assert diagnostics.catalogue_source_count == 3
