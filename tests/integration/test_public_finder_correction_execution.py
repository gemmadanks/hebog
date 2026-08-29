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


def _hierarchy_plane(
    labels: npt.NDArray[np.int32],
    identifier: str,
    *,
    scale_order: int,
) -> ScaleDetectionPlane:
    """Build one exact common-parent plane for executor fixtures."""
    y_pixels, x_pixels = np.nonzero(labels > 0)
    support_labels = np.where(labels > 0, 1, 0).astype(np.int32)
    return ScaleDetectionPlane(
        scale_order=scale_order,
        component_labels=support_labels,
        detections=(
            ScaleDetection(
                detection_id=identifier,
                parent_island_id=None,
                scale_order=scale_order,
                nominal_scale_beam_fwhm=float(2 ** (scale_order - 1)),
                support_pixel_count=int(y_pixels.size),
                valid_support_fraction=1.0,
                bounds_yx=(
                    int(np.min(y_pixels)),
                    int(np.max(y_pixels)) + 1,
                    int(np.min(x_pixels)),
                    int(np.max(x_pixels)) + 1,
                ),
                canonical_pixel_yx=(int(y_pixels[0]), int(x_pixels[0])),
                peak_response_jy_per_beam=1.0,
                peak_signal_to_noise=5.0,
                touches_image_edge=False,
            ),
        ),
    )


def _reconstruct_hierarchy(batch: HierarchyBatch) -> SourceAssociationResult:
    """Apply common-parent reconstruction through a worker-safe boundary."""
    labels, records, planes = batch
    return associate_components_by_multiscale_hierarchy(
        records,
        labels,
        planes,
        np.ones(labels.shape, dtype=np.bool_),
    )


@pytest.mark.integration
def test_source_hierarchy_is_serial_dask_order_and_retry_invariant() -> None:
    """Common-parent membership ignores labels, tasks, and plane ordering."""
    labels = np.zeros((9, 17), dtype=np.int32)
    labels[4, 3] = 9
    labels[4, 13] = 2
    permuted = np.where(labels == 9, 31, np.where(labels == 2, 7, 0)).astype(
        np.int32
    )
    support = np.zeros(labels.shape, dtype=np.int32)
    support[4, 3:14] = 1
    fine = _hierarchy_plane(support, "scale-hierarchy-fine", scale_order=1)
    coarse = _hierarchy_plane(
        support,
        "scale-hierarchy-coarse",
        scale_order=2,
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
        (labels, records, (fine, coarse)),
        (permuted, permuted_records, (coarse, fine)),
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
