# pyright: reportMissingTypeStubs=false
"""Phase-neutral records used by the installed scientific composition."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from hebog.algorithms.component_measurement import (
    FitParentMeasurement,
    SupportFeatureGroups,
)
from hebog.algorithms.reconciliation import DetectedIsland
from hebog.data_models.measurement_diagnostics import MeasurementDisposition
from hebog.data_models.source_association import (
    DetectionComponentRecord,
    SourceAssociationResult,
)
from hebog.science.catalogue_rows import CatalogueSource


@dataclass(frozen=True, slots=True)
class CatalogueIsland:
    """One measured detection island, before the public catalogue names it.

    An island is a connected region of the published retained mask, so its
    identity is its canonical first pixel rather than a label: labels depend
    on how the plane was partitioned, and the first pixel does not.
    """

    identifier: str
    pixel_count: int
    integrated_flux_jy: float
    local_rms_jy_per_beam: float
    mean_brightness_jy_per_beam: float

    def __post_init__(self) -> None:
        """Require one named island that owns at least one pixel."""
        if not self.identifier:
            raise ValueError("island identifier must not be empty")
        if self.pixel_count <= 0:
            raise ValueError("island pixel count must be positive")


@dataclass(frozen=True, slots=True)
class TiledMultiscaleDetection:
    """The detection pass's reconciled features, without any of its planes.

    These are the pass-B reductions of the tile-native composition described
    in ADR-008: the island records were reduced on the tasks that held the
    filter responses, and every plane the pass wrote stays in the published
    generation for a later pass to read by window. One record per scale order
    names the scales, so a caller needs no mask to count them.
    """

    detection_islands: tuple[DetectedIsland, ...]
    scale_islands_by_order: tuple[tuple[DetectedIsland, ...], ...]
    scale_nominal_beam_fwhms: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class TiledComponentTopology:
    """What the object pass decided, without the planes it published.

    Each parent was deblended inside the window that holds it, and the
    component numbering follows canonical parent order, so it does not move
    with tile geometry or completion order. The two ownership planes stay in
    the generation: the cores that wrote them already required direct
    ownership to be a valid subset of measurement ownership, and the stage
    required both to name the same components, numbered
    ``1..component_count``.
    """

    component_count: int
    deblended_parent_count: int
    deferred_parent_count: int


@dataclass(frozen=True, slots=True)
class TiledComponentFits:
    """The object pass's per-parent fits, without the support they published.

    Each fit parent was measured inside the window holding its support and
    the reviewed context margin, and each connected feature of the combined
    support contributed its extended groups inside its own window, so these
    records carry no image-sized array: the support plane stays in the
    generation the cores wrote it to, where the source passes read it by
    window.

    ``component_records`` describes every direct component in canonical
    first-pixel order. The fit parent that reads a component's pixels builds
    it, so the association decision and the hierarchy pass read one set of
    records that no later step measures again.
    """

    parents: tuple[FitParentMeasurement, ...]
    features: tuple[SupportFeatureGroups, ...]
    component_records: tuple[DetectionComponentRecord, ...]
    wide_parent_count: int = 0


@dataclass(frozen=True, slots=True)
class ContinuumProducts:
    """Binding associated sources and immutable component diagnostics.

    ``local_rms_by_object_id`` holds the median local noise over each
    component's and each source's own support, measured by the row pass that
    read the window it belongs to. An owner whose support carries no usable
    estimate is absent, which is what makes it unpublishable.

    ``islands`` are the retained mask's own connected regions, in canonical
    first-pixel order, and ``island_ids_by_owner`` names the islands each
    component's retained support reaches. Both come from the island round,
    which reconciled that connectivity across tiles.

    ``component_count`` is how many islands the caller's admission accepted,
    counted by the pass that applied it. Nothing here is a plane: the mask
    product streams from the generation the support pass wrote.
    """

    component_count: int
    catalogue: tuple[CatalogueSource, ...]
    component_catalogue: tuple[CatalogueSource, ...]
    source_association: SourceAssociationResult
    local_rms_by_object_id: Mapping[str, float]
    islands: tuple[CatalogueIsland, ...]
    island_ids_by_owner: Mapping[int, tuple[str, ...]]
    deblended_parent_count: int = 0
    deferred_deblend_parent_count: int = 0
    measurement_dispositions: tuple[MeasurementDisposition, ...] = ()
