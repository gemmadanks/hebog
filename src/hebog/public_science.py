# pyright: reportMissingTypeStubs=false
"""Configurable scientific composition behind the public source finder."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import numpy.typing as npt
from astropy.io import fits

from hebog.algorithms.component_measurement import ComponentMeasurements
from hebog.data_models.measurement_diagnostics import (
    SourcePositionDiagnostics,
)
from hebog.data_models.source_association import (
    SourceAssociationResult,
)
from hebog.science.catalogues import (
    build_hebog_reconstructed_source_catalogues,
)
from hebog.science.continuum import (
    build_continuum_candidate_products,
)
from hebog.science.models import (
    CatalogueSource,
    ContinuumProducts,
    TiledComponentTopology,
    TiledMultiscaleDetection,
    TiledSupportLabels,
)

_IMAGE_DIMENSIONS = 2


def _aligned_plane(
    values: npt.ArrayLike,
    *,
    name: str,
    shape: tuple[int, int] | None = None,
) -> npt.NDArray[np.float64]:
    """Return one aligned real two-dimensional public science plane."""
    plane = np.asarray(values)
    if (
        plane.ndim != _IMAGE_DIMENSIONS
        or not np.issubdtype(plane.dtype, np.number)
        or np.iscomplexobj(plane)
        or (shape is not None and plane.shape != shape)
    ):
        raise ValueError(
            f"public source-finder {name} must be an aligned real "
            "two-dimensional plane"
        )
    return np.asarray(plane, dtype=np.float64)


def build_configured_continuum_products(  # noqa: PLR0913
    image_jy_per_beam: npt.ArrayLike,
    background_jy_per_beam: npt.ArrayLike,
    rms_jy_per_beam: npt.ArrayLike,
    header: fits.Header,
    *,
    multiscale: TiledMultiscaleDetection,
    labels: TiledSupportLabels,
    topology: TiledComponentTopology,
    measurements: ComponentMeasurements,
    association: SourceAssociationResult,
    hierarchy: SourceAssociationResult,
    source_labels: npt.NDArray[np.int32],
    source_measurement_labels: npt.NDArray[np.int32],
    component_rows: tuple[CatalogueSource, ...],
    source_rows: tuple[CatalogueSource, ...],
    source_positions: Mapping[int, SourcePositionDiagnostics],
) -> ContinuumProducts | None:
    """Build terminal products from the published tiled passes.

    Every threshold and island limit has already been applied by the passes
    that published these records, so this step takes no configuration: an
    image whose admitted islands are all rejected publishes nothing.
    """
    image = _aligned_plane(image_jy_per_beam, name="image")
    background = _aligned_plane(
        background_jy_per_beam,
        name="background",
        shape=image.shape,
    )
    rms = _aligned_plane(rms_jy_per_beam, name="RMS", shape=image.shape)
    valid = np.isfinite(image) & np.isfinite(background) & np.isfinite(rms)
    if np.any(np.isfinite(image) != valid):
        raise ValueError(
            "public source-finder mean/RMS validity differs from image"
        )
    positive_rms = valid & (rms > 0.0)
    if not np.any(np.asarray(labels.component_labels) > 0):
        return None
    retained = build_continuum_candidate_products(
        positive_rms,
        multiscale=multiscale,
        labels=labels,
    )
    catalogues = build_hebog_reconstructed_source_catalogues(
        valid,
        topology.measurement_component_labels,
        topology.direct_component_labels,
        header,
        component_measurements=measurements,
        association=association,
        hierarchy=hierarchy,
        source_labels=source_labels,
        source_measurement_labels=source_measurement_labels,
        component_rows=component_rows,
        source_rows=source_rows,
        source_positions=source_positions,
    )
    valid.setflags(write=False)
    return ContinuumProducts(
        detection=retained.detection,
        measurement_component_labels=(topology.measurement_component_labels),
        catalogue=catalogues.source_catalogue,
        valid_pixels=valid,
        component_catalogue=catalogues.component_catalogue,
        source_association=catalogues.association,
        deblended_parent_count=topology.deblended_parent_count,
        deferred_deblend_parent_count=topology.deferred_parent_count,
        measurement_dispositions=catalogues.measurement_dispositions,
    )
