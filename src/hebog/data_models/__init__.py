"""Small serializable scheduler-independent domain records."""

from hebog.data_models.catalogue_construction import CompletedCombinedCatalogue
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
from hebog.data_models.images import CelestialWcs, ImageMetadata, RestoringBeam
from hebog.data_models.multiscale import (
    CombinedCatalogueReduction,
    CombinedCatalogueShard,
    CombinedCatalogueState,
    CombinedIslandDisposition,
    CombinedIslandIdentity,
    CompactExtendedContextEdge,
    CompactSourceSupport,
    CompletedCombinedCatalogueState,
    CrossScaleAssociation,
    ExtendedEmissionMeasurement,
    ExtendedSourceIdentity,
    MultiscaleOmission,
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
    SourceFinderRequest,
    SourceFinderResult,
    SourceFindingDiagnostics,
    SourceScaleProvenance,
)

__all__ = [
    "CatalogueSourceMembership",
    "CelestialWcs",
    "CombinedCatalogueReduction",
    "CombinedCatalogueShard",
    "CombinedCatalogueState",
    "CombinedIslandDisposition",
    "CombinedIslandIdentity",
    "CompactExtendedContextEdge",
    "CompactSourceSupport",
    "CompletedCombinedCatalogue",
    "CompletedCombinedCatalogueState",
    "ContinuumSourceFindingDiagnostics",
    "CrossScaleAssociation",
    "DetectionComponentRecord",
    "ExtendedEmissionMeasurement",
    "ExtendedSourceIdentity",
    "FluxMeasurement",
    "GaussianComponent",
    "GaussianShape",
    "ImageBounds",
    "ImageMetadata",
    "Island",
    "MaterializedProduct",
    "MultiscaleOmission",
    "PartitionManifest",
    "ProductChunk",
    "ProductGenerationManifest",
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
    "TilePartition",
]
