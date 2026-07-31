"""Small serializable scheduler-independent domain records."""

from hebog.data_models.images import CelestialWcs, ImageMetadata, RestoringBeam
from hebog.data_models.partitioning import (
    ImageBounds,
    PartitionManifest,
    TilePartition,
)
from hebog.data_models.products import (
    ProductChunk,
    ProductChunkRecord,
    ZarrProductChunk,
)
from hebog.data_models.source_finding import (
    SourceFinderRequest,
    SourceFinderResult,
)

__all__ = [
    "CelestialWcs",
    "ImageBounds",
    "ImageMetadata",
    "PartitionManifest",
    "ProductChunk",
    "ProductChunkRecord",
    "RestoringBeam",
    "SourceFinderRequest",
    "SourceFinderResult",
    "TilePartition",
    "ZarrProductChunk",
]
