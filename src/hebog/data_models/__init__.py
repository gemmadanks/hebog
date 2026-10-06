"""Small serializable scheduler-independent domain records."""

from hebog.data_models.catalogues import (
    FluxMeasurement,
    GaussianComponent,
    GaussianShape,
    Island,
    SkyPosition,
    SourceCandidate,
    SourceCatalogue,
    SpectralModel,
)
from hebog.data_models.generations import ProductGenerationManifest
from hebog.data_models.images import (
    CelestialWcs,
    ImageMetadata,
    RestoringBeam,
    SuppliedImageMetadata,
)
from hebog.data_models.multiscale import (
    CrossScaleAssociation,
    ScaleDetection,
)
from hebog.data_models.partitioning import (
    ImageBounds,
    PartitionManifest,
    TilePartition,
)
from hebog.data_models.products import ProductChunk
from hebog.data_models.source_association import (
    CatalogueSourceMembership,
    DetectionComponentRecord,
    SourceAssociationEdge,
    SourceAssociationResult,
)
from hebog.data_models.source_finding import (
    ContinuumSourceFindingDiagnostics,
    MaterializedProduct,
    PublicSourceFindingDiagnostics,
    PublicSourceFindingProvenance,
    SourceFinderRequest,
    SourceFinderResult,
    SourceFindingDiagnostics,
    SourceScaleProvenance,
    WideObjectCounts,
)

__all__ = [
    "CatalogueSourceMembership",
    "CelestialWcs",
    "ContinuumSourceFindingDiagnostics",
    "CrossScaleAssociation",
    "DetectionComponentRecord",
    "FluxMeasurement",
    "GaussianComponent",
    "GaussianShape",
    "ImageBounds",
    "ImageMetadata",
    "Island",
    "MaterializedProduct",
    "PartitionManifest",
    "ProductChunk",
    "ProductGenerationManifest",
    "PublicSourceFindingDiagnostics",
    "PublicSourceFindingProvenance",
    "RestoringBeam",
    "ScaleDetection",
    "SkyPosition",
    "SourceAssociationEdge",
    "SourceAssociationResult",
    "SourceCandidate",
    "SourceCatalogue",
    "SourceFinderRequest",
    "SourceFinderResult",
    "SourceFindingDiagnostics",
    "SourceScaleProvenance",
    "SpectralModel",
    "SuppliedImageMetadata",
    "TilePartition",
    "WideObjectCounts",
]
