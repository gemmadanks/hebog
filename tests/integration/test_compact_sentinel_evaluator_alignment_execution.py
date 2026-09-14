# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Existing-Dask fixture contracts for compact sentinel alignment."""

from __future__ import annotations

import runpy
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS
from distributed import Client, LocalCluster

from hebog.data_models.source_association import (
    CatalogueSourceMembership,
    DetectionComponentRecord,
    SourceAssociationResult,
)
from hebog.executors import DaskExecutor, SerialExecutor
from hebog.validation.comparison import CatalogueSource
from hebog.validation.external_successor_compiler import ContinuumTruthObject

_ROOT = Path(__file__).parents[2]
_ADAPTER = runpy.run_path(
    str(_ROOT / "scripts/validation/compact_sentinel_source_unions.py")
)
PyBdsfGaussianRow = _ADAPTER["PyBdsfGaussianRow"]
PyBdsfSourceRow = _ADAPTER["PyBdsfSourceRow"]
derive_pybdsf_source_model_dominance = _ADAPTER[
    "derive_pybdsf_source_model_dominance"
]
project_hebog_source_unions = _ADAPTER["project_hebog_source_unions"]
_PROGRAM = runpy.run_path(
    str(_ROOT / "scripts/validation/compact_sentinel_alignment.py")
)
AlignedComponent = _PROGRAM["AlignedComponent"]
AlignedSource = _PROGRAM["AlignedSource"]
AlignedSummaryInput = _PROGRAM["AlignedSummaryInput"]
compile_aligned_summary = _PROGRAM["compile_aligned_summary"]


def _catalogue_row(
    identifier: str,
    centre_xy: tuple[float, float],
    *,
    header: fits.Header,
) -> CatalogueSource:
    """Return one fixture catalogue row in a shared celestial frame."""
    world = WCS(header, relax=True).celestial.all_pix2world([centre_xy], 0)[0]
    return CatalogueSource(
        identifier,
        float(world[0]),
        float(world[1]),
        1.0,
        1.0,
    )


def _adapter_projection(finder_id: str) -> dict[str, object]:
    """Compile one worker-safe projection without executing a finder."""
    if finder_id == "current-hebog":
        wcs = WCS(naxis=2)
        wcs.wcs.crpix = [1.0, 1.0]
        wcs.wcs.cdelt = np.asarray([-0.01, 0.01])
        wcs.wcs.crval = [10.0, -30.0]
        wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
        header = wcs.to_header()
        projection = project_hebog_source_unions(
            source_catalogue=(
                _catalogue_row("source-a", (1.0, 0.0), header=header),
            ),
            component_catalogue=(
                _catalogue_row("component-a", (1.0, 0.0), header=header),
            ),
            association=SourceAssociationResult(
                components=(
                    DetectionComponentRecord(
                        "component-a",
                        7,
                        (0, 1),
                        (0.0, 1.0),
                        None,
                    ),
                ),
                edges=(),
                memberships=(
                    CatalogueSourceMembership("source-a", ("component-a",)),
                ),
            ),
            measurement_component_labels=np.asarray(((7, 7),)),
            header=header,
        )
    else:
        projection = derive_pybdsf_source_model_dominance(
            source_rows=(PyBdsfSourceRow(0, 0, (0.5, 0.0), 1.0, 1),),
            gaussian_rows=(
                PyBdsfGaussianRow(
                    "gaussian-a",
                    0,
                    0,
                    (0.5, 0.0),
                    1.0,
                    1.0,
                    ((0.5, 0.0), (0.0, 0.5)),
                ),
            ),
            native_island_labels=np.asarray(((1, 1, 0, 2),)),
        )
    return {
        "components": [asdict(item) for item in projection.components],
        "finder_id": projection.finder_id,
        "native": projection.native_owner_label_plane.tolist(),
        "source_union": projection.source_union_label_plane.tolist(),
        "sources": [asdict(item) for item in projection.sources],
        "unowned": list(projection.unowned_native_support_labels),
    }


def _fixture(index: int) -> Any:
    """Return one small worker-serializable semantic-alignment fixture."""
    labels = np.asarray(((7, 7, 0, 9, 9),), dtype=np.int32)
    return AlignedSummaryInput(
        input_id=f"fixture-{index}",
        finder_id="current-hebog",
        truth=(
            ContinuumTruthObject(
                "truth",
                1,
                (2.0, 0.0),
                3.0,
                "astronomical-source",
                ("overall",),
            ),
        ),
        truth_label_plane=np.asarray(((1, 1, 0, 1, 1),), dtype=np.int32),
        sources=(
            AlignedSource(
                "source",
                ("component-a", "component-b"),
                (7, 9),
                (2.0, 0.0),
                3.0,
            ),
        ),
        components=(
            AlignedComponent("component-a", "source", 7, (1.0, 0.0), 1.0),
            AlignedComponent("component-b", "source", 9, (3.0, 0.0), 2.0),
        ),
        native_owner_label_plane=labels,
        source_union_label_plane=np.asarray(labels > 0, dtype=np.int32),
        native_topology_domain="component-owner",
        published_support_mask=labels > 0,
        beam_fwhm_pixels=2.0,
        adaptive_background_trigger="boundary",
    )


@pytest.mark.integration
def test_aligned_evaluator_is_serial_existing_dask_and_order_invariant() -> (
    None
):
    """Caller-owned Dask returns the exact ordered Serial summaries."""
    batches = tuple(_fixture(index) for index in range(3))
    serial = SerialExecutor().map_batches(compile_aligned_summary, batches)

    cluster = LocalCluster(
        n_workers=2,
        threads_per_worker=1,
        processes=False,
        dashboard_address="",
    )
    with cluster, Client(cluster) as client:
        dask = DaskExecutor(client).map_batches(
            compile_aligned_summary,
            tuple(reversed(batches)),
        )

    assert dask == list(reversed(serial))


@pytest.mark.integration
def test_source_union_adapters_are_existing_dask_and_order_invariant() -> None:
    """Both pure projections are invariant to worker and completion order."""
    finders = ("current-hebog", "released-pybdsf")
    serial = SerialExecutor().map_batches(_adapter_projection, finders)

    cluster = LocalCluster(
        n_workers=2,
        threads_per_worker=1,
        processes=False,
        dashboard_address="",
    )
    with cluster, Client(cluster) as client:
        dask = DaskExecutor(client).map_batches(
            _adapter_projection, tuple(reversed(finders))
        )

    assert dask == list(reversed(serial))
