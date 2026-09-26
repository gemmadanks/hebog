# pyright: reportMissingTypeStubs=false
"""Configurable scientific composition behind the public source finder."""

from __future__ import annotations

from collections.abc import Mapping

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
    local_rms_by_object_id,
)
from hebog.science.models import (
    CatalogueIsland,
    CatalogueSource,
    ContinuumProducts,
    TiledComponentTopology,
)


def build_configured_continuum_products(  # noqa: PLR0913
    header: fits.Header,
    *,
    component_count: int,
    topology: TiledComponentTopology,
    measurements: ComponentMeasurements,
    association: SourceAssociationResult,
    hierarchy: SourceAssociationResult,
    component_rows: tuple[CatalogueSource, ...],
    source_rows: tuple[CatalogueSource, ...],
    source_positions: Mapping[int, SourcePositionDiagnostics],
    component_local_rms: Mapping[int, float],
    source_local_rms: Mapping[int, float],
    islands: tuple[CatalogueIsland, ...],
    island_ids_by_owner: Mapping[int, tuple[str, ...]],
) -> ContinuumProducts | None:
    """Build terminal products from the published tiled passes.

    Every threshold and island limit has already been applied by the passes
    that published these records, so this step takes no configuration: an
    image whose admitted islands are all rejected publishes nothing.

    This step holds no plane at all. The row passes measured each owner's
    local noise by label, so it names that by catalogue identity; the islands
    arrive measured from the round that reconciled the retained mask's own
    connectivity; and every plane those records describe stays in the
    generation the pass wrote it to.
    """
    if component_count <= 0:
        return None
    catalogues = build_hebog_reconstructed_source_catalogues(
        header,
        component_measurements=measurements,
        association=association,
        hierarchy=hierarchy,
        component_rows=component_rows,
        source_rows=source_rows,
        source_positions=source_positions,
    )
    return ContinuumProducts(
        component_count=component_count,
        catalogue=catalogues.source_catalogue,
        component_catalogue=catalogues.component_catalogue,
        source_association=catalogues.association,
        local_rms_by_object_id=local_rms_by_object_id(
            association,
            component_local_rms=component_local_rms,
            source_local_rms=source_local_rms,
        ),
        islands=islands,
        island_ids_by_owner=island_ids_by_owner,
        deblended_parent_count=topology.deblended_parent_count,
        deferred_deblend_parent_count=topology.deferred_parent_count,
        measurement_dispositions=catalogues.measurement_dispositions,
    )
