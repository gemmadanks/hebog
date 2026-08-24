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
from hebog.data_models.source_finding import (
    MaterializedProduct,
    SourceFinderRequest,
    SourceFinderResult,
    SourceFindingDiagnostics,
)

__all__ = [
    "CelestialWcs",
    "CombinedCatalogueReduction",
    "CombinedCatalogueShard",
    "CombinedCatalogueState",
    "CombinedIslandDisposition",
    "CombinedIslandIdentity",
    "CompactExtendedContextEdge",
    "CompactSourceSupport",
    "CompletedCombinedCatalogueState",
    "CrossScaleAssociation",
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
    "SourceCandidate",
    "SourceCatalogue",
    "SourceFinderRequest",
    "SourceFinderResult",
    "SourceFindingDiagnostics",
    "SpectralModel",
    "TilePartition",
]
