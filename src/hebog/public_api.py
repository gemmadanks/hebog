# pyright: reportUnknownMemberType=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
"""Outer I/O implementation of the public source-finding facade."""

from __future__ import annotations

import hashlib
import importlib
import json
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from importlib.resources import files
from math import prod
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from typing import TYPE_CHECKING, Any, Literal, Protocol, cast

import numpy as np
import numpy.typing as npt
from astropy.io import fits
from astropy.wcs.utils import wcs_to_celestial_frame
from scipy.ndimage import find_objects, label

from hebog.algorithms.astrometry import (
    celestial_wcs_from_metadata,
    compact_geometry_from_wcs,
)
from hebog.algorithms.label_groups import label_windows
from hebog.algorithms.multiscale import BeamShapePixels
from hebog.algorithms.partitioning import plan_image_partitions
from hebog.config import BackgroundRmsConfig, SourceFinderConfig
from hebog.data_models import (
    CatalogueSourceMembership,
    FluxMeasurement,
    GaussianComponent,
    GaussianShape,
    ImageBounds,
    Island,
    PublicSourceFindingDiagnostics,
    PublicSourceFindingProvenance,
    SkyPosition,
    SourceCandidate,
    SourceCatalogue,
    SourceFinderRequest,
    SourceFinderResult,
    SpectralModel,
)
from hebog.data_models.images import ImageMetadata, RestoringBeam
from hebog.data_models.measurement_diagnostics import MeasurementDisposition
from hebog.executors import Executor
from hebog.io import FitsImageSource, ZarrProductSink
from hebog.io.base import ImageWindow
from hebog.io.filesystem import rename_without_replacement
from hebog.io.materialization import (
    write_catalogue_fits_product,
    write_diagnostics_product,
    write_mask_fits_product,
    write_rms_fits_product,
)
from hebog.pipeline import (
    InvalidSourceFinderInputError,
    SourceFinderError,
    SourceFinderImageTooLargeError,
    SourceFinderOutputExistsError,
    UnsupportedSourceFinderConfigurationError,
)
from hebog.stages.detection import run_detection_stage

if TYPE_CHECKING:  # pragma: no cover - import-time typing only
    from hebog.science.models import (
        TiledComponentFits,
        TiledComponentTopology,
        TiledMultiscaleDetection,
        TiledSupportLabels,
    )
    from hebog.science.profile import ContinuumScienceProfile

_MAXIMUM_PREVIEW_DIMENSION = 1024
_TILE_SHAPE_YX = (128, 128)
ADMITTED_TILE_CORE_PIXELS = 2048
"""Smallest tile core the scalability contract admits, in pixels."""
_SUPPORT_TILES_PER_BATCH = 4
_OWNER_BATCH_READ_PIXELS = 4 * 1024 * 1024
_DETECTION_THRESHOLD_SIGMA = 5.0
_ISLAND_THRESHOLD_SIGMA = 3.0
_MINIMUM_ISLAND_PIXELS = 7
_COMPOSITION_NAME = "phase-5-evidence-bound-public-catalogue-v22"
_PROFILE_RESOURCE = "reviewed_continuum_profile.json"
_FWHM_PER_SIGMA = 2.0 * np.sqrt(2.0 * np.log(2.0))
# Finite-difference WCS Jacobians carry ~1e-8 pixel round-off. Quantising the
# derived beam axes to 1e-6 pixel keeps whole-pixel beams exact, so ``ceil``
# aperture radii and kernel halos cannot flip with a sub-mas WCS change.
_BEAM_AXIS_DECIMALS = 6
_SCIENTIFIC_MODULES = (
    "hebog.algorithms.astrometry",
    "hebog.algorithms.background",
    "hebog.algorithms.component_measurement",
    "hebog.algorithms.component_topology",
    "hebog.algorithms.deblending",
    "hebog.algorithms.detection",
    "hebog.algorithms.extended_measurement",
    "hebog.algorithms.fitting",
    "hebog.algorithms.labelling",
    "hebog.algorithms.measurement",
    "hebog.algorithms.multiscale",
    "hebog.algorithms.multiscale_association",
    "hebog.algorithms.multiscale_tiles",
    "hebog.algorithms.reconciliation",
    "hebog.algorithms.source_association",
    "hebog.data_models.catalogues",
    "hebog.data_models.fitting",
    "hebog.data_models.measurement_diagnostics",
    "hebog.data_models.source_finding",
    "hebog.public_api",
    "hebog.public_science",
    "hebog.science.catalogues",
    "hebog.science.configuration",
    "hebog.science.continuum",
    "hebog.science.models",
    "hebog.science.profile",
    "hebog.stages.background",
    "hebog.stages.detection",
    "hebog.stages.multiscale",
)


class _WindowReadable(Protocol):
    """Read bounded global image windows without scheduler state."""

    def read_window(self, bounds: ImageBounds) -> ImageWindow:
        """Read one bounded global window."""
        ...


@dataclass(frozen=True, slots=True)
class _ScientificProducts:
    """Exact evaluated science plus the candidate-owned background/RMS."""

    image: npt.NDArray[np.float64]
    background: npt.NDArray[np.float64]
    rms: npt.NDArray[np.float64]
    terminal: Any | None


def _require_unclaimed_output(output: Path) -> None:
    """Reject any existing destination, including a dangling symlink."""
    if output.exists() or output.is_symlink():
        raise SourceFinderOutputExistsError(
            f"source-finder output already exists: {output}"
        )


def _publish_bundle(unpublished: Path, output: Path) -> None:
    """Claim the destination and publish the staged bundle into it.

    Another writer may claim the destination while the analysis runs, so the
    publication itself, not an earlier check, decides ownership. Products
    appear in one rename; see
    :func:`hebog.io.filesystem.rename_without_replacement` for the moment the
    claimed path becomes visible.
    """
    try:
        rename_without_replacement(unpublished, output)
    except FileExistsError as error:
        raise SourceFinderOutputExistsError(
            f"source-finder output already exists: {output}"
        ) from error


def _file_sha256(path: Path) -> str:
    """Return one streaming lowercase SHA-256 identity."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha256(value: object) -> str:
    """Hash one JSON-compatible value under canonical serialization."""
    payload = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _configuration_qualification(
    config: SourceFinderConfig,
) -> Literal["development-unqualified", "custom-unqualified"]:
    """Do not transfer historical qualification to the repaired finder."""
    if (
        config.detection_threshold_sigma != _DETECTION_THRESHOLD_SIGMA
        or config.island_threshold_sigma != _ISLAND_THRESHOLD_SIGMA
        or config.minimum_island_pixels != _MINIMUM_ISLAND_PIXELS
        or config.maximum_island_pixels is not None
    ):
        return "custom-unqualified"
    return "development-unqualified"


def _supported_celestial_frame(metadata: ImageMetadata) -> bool:
    """Accept ICRS, or FK5 J2000 whose positions are transformed to ICRS.

    FK5 J2000 is the frame the FITS WCS standard assigns to ``EQUINOX = 2000``
    without ``RADESYS``, as written by common radio imagers. Every published
    sky position and beam angle is transformed through Astropy's frame tie.
    """
    frame_name = metadata.celestial_wcs.coordinate_frame
    if frame_name == "icrs":
        return True
    if frame_name != "fk5":
        return False
    frame = cast(
        Any, wcs_to_celestial_frame(celestial_wcs_from_metadata(metadata))
    )
    return bool(np.isclose(frame.equinox.jyear, 2000.0, rtol=0.0, atol=1e-9))


def _qualified_metadata(metadata: ImageMetadata) -> None:
    """Require the evaluated physical frame, unit, and bounded size."""
    if metadata.unit != "Jy/beam":
        raise UnsupportedSourceFinderConfigurationError(
            "the public source finder requires BUNIT=Jy/beam"
        )
    if not _supported_celestial_frame(metadata):
        raise UnsupportedSourceFinderConfigurationError(
            "the public source finder requires an ICRS or FK5 J2000 "
            "celestial WCS"
        )
    if max(metadata.shape_yx) > _MAXIMUM_PREVIEW_DIMENSION:
        raise SourceFinderImageTooLargeError(
            "the public source finder supports at most 1024 pixels per "
            "image dimension"
        )


def _header_with_metadata(
    header: fits.Header,
    metadata: ImageMetadata,
) -> fits.Header:
    """Fill beam keywords the header omits from validated image metadata.

    The scientific composition reads the beam from the header. A keyword with
    an undefined value is missing, as in metadata validation, which has
    already refused any supplied value that duplicates a defined keyword, so
    defined header values are never changed.
    """
    completed = header.copy()
    beam = metadata.beam
    for keyword, value in (
        ("BMAJ", beam.major_fwhm_degrees),
        ("BMIN", beam.minor_fwhm_degrees),
        ("BPA", beam.position_angle_degrees),
    ):
        if completed.get(keyword) is None:
            completed[keyword] = value
    return completed


def _full_bounds(metadata: ImageMetadata) -> ImageBounds:
    """Return the complete bounded image plane."""
    return ImageBounds(0, metadata.shape_yx[0], 0, metadata.shape_yx[1])


def _profile_bytes() -> bytes:
    """Read the immutable reviewed science profile from the installed wheel."""
    return files("hebog.resources").joinpath(_PROFILE_RESOURCE).read_bytes()


@lru_cache(maxsize=1)
def _scientific_composition_sha256() -> str:
    """Bind every module that implements the evaluated terminal composition."""
    digest = hashlib.sha256()
    for module_name in _SCIENTIFIC_MODULES:
        module = importlib.import_module(module_name)
        module_path_value = getattr(module, "__file__", None)
        if module_path_value is None:
            raise SourceFinderError(
                f"cannot identify scientific module {module_name}"
            )
        digest.update(module_name.encode())
        digest.update(b"\0")
        digest.update(Path(module_path_value).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _beam_shape_pixels(metadata: ImageMetadata) -> BeamShapePixels:
    """Transform the restoring beam into local image-pixel coordinates."""
    height, width = metadata.shape_yx
    geometry = compact_geometry_from_wcs(
        metadata.beam,
        celestial_wcs_from_metadata(metadata),
        ((width - 1) / 2.0, (height - 1) / 2.0),
    )
    covariance = geometry.restoring_beam_covariance_pixels_squared
    if covariance is None:  # pragma: no cover - produced by this function
        raise SourceFinderError("restoring-beam pixel geometry is unavailable")
    covariance_xx, covariance_xy, covariance_yy = covariance
    matrix = np.asarray(
        ((covariance_xx, covariance_xy), (covariance_xy, covariance_yy)),
        dtype=np.float64,
    )
    eigenvalues, eigenvectors = np.linalg.eigh(matrix)
    major_index = int(np.argmax(eigenvalues))
    minor_index = 1 - major_index
    major_vector = eigenvectors[:, major_index]
    major_fwhm_pixels = round(
        float(np.sqrt(eigenvalues[major_index]) * _FWHM_PER_SIGMA),
        _BEAM_AXIS_DECIMALS,
    )
    minor_fwhm_pixels = round(
        float(np.sqrt(eigenvalues[minor_index]) * _FWHM_PER_SIGMA),
        _BEAM_AXIS_DECIMALS,
    )
    if major_fwhm_pixels == minor_fwhm_pixels:
        angle = 0.0
    else:
        angle = float(
            np.rad2deg(np.arctan2(major_vector[1], major_vector[0])) % 180.0
        )
    return BeamShapePixels(
        major_fwhm_pixels=major_fwhm_pixels,
        minor_fwhm_pixels=minor_fwhm_pixels,
        position_angle_degrees=angle,
    )


def _public_background_config(
    image_shape_yx: tuple[int, int],
    config: BackgroundRmsConfig,
    *,
    source_finder: SourceFinderConfig,
) -> BackgroundRmsConfig:
    """Reconcile refinement seeds and spatial meshes with public inputs."""
    adaptive = config.adaptive
    if adaptive is not None and (
        source_finder.island_threshold_sigma
        >= adaptive.candidate_threshold_sigma
    ):
        # Protected seeds must exceed the public support-growth threshold.
        # The validated caller detection threshold already has that ordering.
        config = replace(
            config,
            adaptive=replace(
                adaptive,
                candidate_threshold_sigma=source_finder.detection_threshold_sigma,
            ),
        )
    limiting_dimension = min(image_shape_yx)
    largest_window = max(config.coarse.window_shape_yx)
    if limiting_dimension < largest_window:
        return config
    fraction = min(
        1.0,
        config.maximum_spatial_window_fraction
        * limiting_dimension
        / largest_window,
    )
    if (
        fraction < 1.0
        and prod(image_shape_yx) > config.maximum_constant_map_pixels
    ):
        raise ValueError(
            "spatial mesh protection exceeds bounded image admission"
        )
    return replace(
        config,
        coarse=replace(
            config.coarse,
            window_shape_yx=tuple(
                max(1, int(size * fraction))
                for size in config.coarse.window_shape_yx
            ),
            step_yx=tuple(
                max(1, int(size * fraction)) for size in config.coarse.step_yx
            ),
        ),
        maximum_spatial_window_fraction=1.0,
    )


def _estimate_background_rms(  # noqa: PLR0913
    source: FitsImageSource,
    metadata: ImageMetadata,
    config: SourceFinderConfig,
    executor: Executor,
    work_directory: Path,
    *,
    generation_id: str,
) -> tuple[ZarrProductSink, npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Run the exact candidate-owned bounded background/RMS stage."""
    from hebog.science.configuration import (  # noqa: PLC0415
        source_finder_configs,
    )
    from hebog.stages.background import (  # noqa: PLC0415
        MultiscaleSourceProtection,
    )

    manifest = plan_image_partitions(
        image_shape_yx=metadata.shape_yx,
        tile_core_shape_yx=_TILE_SHAPE_YX,
        halo_yx=(0, 0),
    )
    sink = ZarrProductSink(
        work_directory / "background.zarr",
        manifest,
        generation_id=generation_id,
    )
    candidate_detection = source_finder_configs()[0]
    detection_config = replace(
        candidate_detection,
        source_finder=config,
        background_rms=(
            _public_background_config(
                metadata.shape_yx,
                candidate_detection.background_rms,
                source_finder=config,
            )
            if config.profile == "continuum"
            else candidate_detection.background_rms
        ),
    )
    run_detection_stage(
        source,
        manifest,
        detection_config,
        executor,
        sink,
        protect_coarse_source_support=(
            config.profile == "continuum"
            and detection_config.background_rms.coarse.window_shape_yx
            != candidate_detection.background_rms.coarse.window_shape_yx
        ),
        refine_local_noise=(
            config.profile == "continuum"
            and min(metadata.shape_yx)
            >= max(candidate_detection.background_rms.coarse.window_shape_yx)
        ),
        multiscale_protection=(
            MultiscaleSourceProtection(
                _beam_shape_pixels(metadata),
                config,
                float(
                    json.loads(_profile_bytes())["matrix"][
                        "support_fraction_bounds"
                    ][0]
                ),
            )
            if config.profile == "continuum"
            else None
        ),
    )
    bounds = _full_bounds(metadata)
    return (
        sink,
        np.asarray(
            sink.read_completed_window("background", bounds),
            dtype=np.float64,
        ),
        np.asarray(
            sink.read_completed_window("rms", bounds),
            dtype=np.float64,
        ),
    )


def detect_multiscale_products(  # noqa: PLR0913
    source: _WindowReadable,
    background_rms_source: ZarrProductSink,
    executor: Executor,
    work_directory: Path,
    *,
    image_shape_yx: tuple[int, int],
    beam: BeamShapePixels,
    review: ContinuumScienceProfile,
    generation_id: str,
    tile_core_pixels: int = ADMITTED_TILE_CORE_PIXELS,
) -> tuple[ZarrProductSink, TiledMultiscaleDetection]:
    """Run the tiled detection pass and read its published planes.

    The composition owns no filter response plane: the pass publishes the
    planes a later pass reads, and reduces each scale feature's peak while
    its response is still on the task that evaluated it.

    ``tile_core_pixels`` is the non-overlapping output core each task owns.
    It defaults to the smallest core the scalability contract admits, and is
    widened when the widest filter halo would exceed a quarter of it. Tile
    geometry changes which task computes a value, never the value. One tile
    per batch is already a coarse task at that core, so batching adds nothing
    here.
    """
    from hebog.algorithms.multiscale_tiles import (  # noqa: PLC0415
        scale_filter_halo_pixels,
    )
    from hebog.science.continuum import (  # noqa: PLC0415
        residual_detection_config,
    )
    from hebog.science.models import (  # noqa: PLC0415
        TiledMultiscaleDetection,
    )
    from hebog.stages.multiscale import (  # noqa: PLC0415
        MultiscaleStageConfig,
        run_multiscale_stage,
    )

    halo = scale_filter_halo_pixels(beam)
    core = max(tile_core_pixels, 4 * halo + 1)
    manifest = plan_image_partitions(
        image_shape_yx=image_shape_yx,
        tile_core_shape_yx=(core, core),
        halo_yx=(halo, halo),
    )
    sink = ZarrProductSink(
        work_directory / "multiscale.zarr",
        manifest,
        generation_id=generation_id,
    )
    result = run_multiscale_stage(
        source,
        background_rms_source,
        manifest,
        config=MultiscaleStageConfig(
            beam=beam,
            detection=residual_detection_config(review),
            maximum_tiles_per_batch=1,
        ),
        executor=executor,
        sink=sink,
    )
    bounds = ImageBounds(0, image_shape_yx[0], 0, image_shape_yx[1])

    def plane(product_name: str, dtype: str) -> npt.NDArray[Any]:
        """Read one published detection plane over the whole image."""
        return np.asarray(
            sink.read_completed_window(product_name, bounds),
            dtype=dtype,
        )

    return sink, TiledMultiscaleDetection(
        detection_labels=plane("detection-labels", "int32"),
        reconstruction_mask=plane("reconstruction-mask", "bool"),
        position_signal_jy_per_beam=plane("position-signal", "float64"),
        significant_scale_masks=tuple(
            plane(f"scale-{order}-significant", "bool")
            for order in range(1, len(result.scale_islands_by_order) + 1)
        ),
        detection_islands=result.detection_islands,
        scale_islands_by_order=result.scale_islands_by_order,
        scale_nominal_beam_fwhms=result.scale_nominal_beam_fwhms,
    )


def reduce_support_topology(  # noqa: PLR0913
    detection_source: ZarrProductSink,
    executor: Executor,
    work_directory: Path,
    *,
    image_shape_yx: tuple[int, int],
    scale_orders: tuple[int, ...],
    generation_id: str,
    tile_core_pixels: int = ADMITTED_TILE_CORE_PIXELS,
) -> ZarrProductSink:
    """Reconcile the support pass's global topology and read its planes.

    Neither reduction is bounded by a halo: support components follow paths of
    arbitrary length, and adjacent-scale persistence is a record graph over
    the whole image. Both are reconciled from compact per-core summaries and
    published as owned cores, and the generation is returned so the support
    rounds read them by window.
    """
    from hebog.stages.support import (  # noqa: PLC0415
        SupportTopologyStageConfig,
        run_support_topology_stage,
    )

    manifest = plan_image_partitions(
        image_shape_yx=image_shape_yx,
        tile_core_shape_yx=(tile_core_pixels, tile_core_pixels),
        halo_yx=(0, 0),
    )
    sink = ZarrProductSink(
        work_directory / "support.zarr",
        manifest,
        generation_id=generation_id,
    )
    run_support_topology_stage(
        detection_source,
        manifest,
        config=SupportTopologyStageConfig(
            scale_orders=scale_orders,
            maximum_tiles_per_batch=_SUPPORT_TILES_PER_BATCH,
        ),
        executor=executor,
        sink=sink,
    )
    return sink


def publish_support_labels(  # noqa: PLR0913
    detection_source: ZarrProductSink,
    support_source: ZarrProductSink,
    executor: Executor,
    work_directory: Path,
    *,
    image_shape_yx: tuple[int, int],
    beam: BeamShapePixels,
    detection_islands: tuple[Any, ...],
    config: SourceFinderConfig,
    review: ContinuumScienceProfile,
    generation_id: str,
    tile_core_pixels: int = ADMITTED_TILE_CORE_PIXELS,
) -> tuple[TiledSupportLabels, ZarrProductSink]:
    """Decide owner connectivity and publish the support pass's labels.

    Two of the decisions here are scoped to an owner rather than to a tile,
    so they are taken once per owner from the window holding it and applied
    by the core that owns each pixel. The caller's island admission is
    applied in the same write.
    """
    from hebog.algorithms.extended_measurement import (  # noqa: PLC0415
        segment_refinement_halo_pixels,
    )
    from hebog.science.models import TiledSupportLabels  # noqa: PLC0415
    from hebog.stages.publication import (  # noqa: PLC0415
        PublicationStageConfig,
        run_publication_stage,
    )

    halo = segment_refinement_halo_pixels(beam.major_fwhm_pixels)
    core = max(tile_core_pixels, 4 * halo + 1)
    manifest = plan_image_partitions(
        image_shape_yx=image_shape_yx,
        tile_core_shape_yx=(core, core),
        halo_yx=(halo, halo),
    )
    sink = ZarrProductSink(
        work_directory / "publication.zarr",
        manifest,
        generation_id=generation_id,
    )
    run_publication_stage(
        detection_source,
        support_source,
        manifest,
        detection_islands=detection_islands,
        config=PublicationStageConfig(
            beam=beam,
            island_threshold_sigma=review.matrix.island_sigma,
            minimum_island_pixels=config.minimum_island_pixels,
            maximum_island_pixels=config.maximum_island_pixels,
            maximum_tiles_per_batch=1,
            maximum_batch_read_pixels=_OWNER_BATCH_READ_PIXELS,
        ),
        executor=executor,
        sink=sink,
    )
    bounds = ImageBounds(0, image_shape_yx[0], 0, image_shape_yx[1])

    def plane(product_name: str, dtype: str) -> npt.NDArray[Any]:
        """Read one published support plane over the whole image."""
        return np.asarray(
            sink.read_completed_window(product_name, bounds),
            dtype=dtype,
        )

    return (
        TiledSupportLabels(
            component_labels=plane("component-labels", "int32"),
            measurement_labels=plane("measurement-labels", "int32"),
            publication_labels=plane("publication-labels", "int32"),
            retained_mask=plane("retained-mask", "bool"),
        ),
        sink,
    )


def publish_component_topology(  # noqa: PLR0913
    support_source: ZarrProductSink,
    detection_source: ZarrProductSink,
    executor: Executor,
    work_directory: Path,
    *,
    image_shape_yx: tuple[int, int],
    config: SourceFinderConfig,
    generation_id: str,
    tile_core_pixels: int = ADMITTED_TILE_CORE_PIXELS,
) -> tuple[ZarrProductSink, TiledComponentTopology]:
    """Deblend every parent in its own window and read the components.

    Deblending needs a parent's complete support and nothing beyond it, so
    the object pass decides one parent per task and the cores write the
    component labels they own.
    """
    from hebog.science.continuum import (  # noqa: PLC0415
        compact_deblend_config,
    )
    from hebog.science.models import (  # noqa: PLC0415
        TiledComponentTopology,
    )
    from hebog.stages.objects import (  # noqa: PLC0415
        ComponentTopologyStageConfig,
        run_component_topology_stage,
    )

    manifest = plan_image_partitions(
        image_shape_yx=image_shape_yx,
        tile_core_shape_yx=(tile_core_pixels, tile_core_pixels),
        halo_yx=(0, 0),
    )
    sink = ZarrProductSink(
        work_directory / "components.zarr",
        manifest,
        generation_id=generation_id,
    )
    result = run_component_topology_stage(
        support_source,
        detection_source,
        manifest,
        config=ComponentTopologyStageConfig(
            deblend=compact_deblend_config(config),
            maximum_tiles_per_batch=_SUPPORT_TILES_PER_BATCH,
            maximum_batch_read_pixels=_OWNER_BATCH_READ_PIXELS,
        ),
        executor=executor,
        sink=sink,
    )
    bounds = ImageBounds(0, image_shape_yx[0], 0, image_shape_yx[1])
    return sink, TiledComponentTopology(
        direct_component_labels=np.asarray(
            sink.read_completed_window("component-direct-labels", bounds),
            dtype=np.int32,
        ),
        measurement_component_labels=np.asarray(
            sink.read_completed_window(
                "component-measurement-labels",
                bounds,
            ),
            dtype=np.int32,
        ),
        deblended_parent_count=result.deblended_parent_count,
        deferred_parent_count=result.deferred_parent_count,
    )


def publish_component_fits(  # noqa: PLR0913, PLR0917
    source: _WindowReadable,
    background_rms_source: ZarrProductSink,
    detection_source: ZarrProductSink,
    component_source: ZarrProductSink,
    executor: Executor,
    work_directory: Path,
    *,
    image_shape_yx: tuple[int, int],
    beam: BeamShapePixels,
    header: fits.Header,
    config: SourceFinderConfig,
    review: ContinuumScienceProfile,
    generation_id: str,
    tile_core_pixels: int = ADMITTED_TILE_CORE_PIXELS,
) -> TiledComponentFits:
    """Fit every measurement parent in its own context window.

    Owners whose fit contexts touch need a joint model, so the contexts are
    reconciled first and each fit parent is then measured inside the window
    holding it. The cores combine the persistent measurement support the
    parents contributed.
    """
    from hebog.algorithms.multiscale import (  # noqa: PLC0415
        build_residual_atrous_plan,
    )
    from hebog.science.configuration import (  # noqa: PLC0415
        source_finder_configs,
    )
    from hebog.science.continuum import (  # noqa: PLC0415
        compact_deblend_config,
    )
    from hebog.science.models import TiledComponentFits  # noqa: PLC0415
    from hebog.stages.objects import (  # noqa: PLC0415
        ComponentFitStageConfig,
        FitParentStageConfig,
        run_component_fit_stage,
        run_fit_parent_stage,
    )

    _, _, moment_config, fit_config, _ = source_finder_configs()
    fit_config = replace(fit_config, integrated_flux_bias_correction_sigma=0.0)
    atrous_plan = build_residual_atrous_plan(beam, noise_correlation=beam)
    context_margin = int(fit_config.context_margin_pixels)
    core = max(tile_core_pixels, 4 * context_margin + 1)
    fit_parent_manifest = plan_image_partitions(
        image_shape_yx=image_shape_yx,
        tile_core_shape_yx=(core, core),
        halo_yx=(context_margin, context_margin),
    )
    fit_parent_sink = ZarrProductSink(
        work_directory / "fit-parents.zarr",
        fit_parent_manifest,
        generation_id=generation_id,
    )
    run_fit_parent_stage(
        component_source,
        fit_parent_manifest,
        config=FitParentStageConfig(
            context_margin_pixels=context_margin,
            maximum_tiles_per_batch=_SUPPORT_TILES_PER_BATCH,
        ),
        executor=executor,
        sink=fit_parent_sink,
    )
    manifest = plan_image_partitions(
        image_shape_yx=image_shape_yx,
        tile_core_shape_yx=(tile_core_pixels, tile_core_pixels),
        halo_yx=(0, 0),
    )
    sink = ZarrProductSink(
        work_directory / "component-fits.zarr",
        manifest,
        generation_id=generation_id,
    )
    result = run_component_fit_stage(
        source,
        background_rms_source,
        detection_source,
        component_source,
        fit_parent_sink,
        manifest,
        config=ComponentFitStageConfig(
            moment=moment_config,
            fit=fit_config,
            atrous_plan=atrous_plan,
            detection_sigma=config.detection_threshold_sigma,
            island_sigma=config.island_threshold_sigma,
            minimum_pixels=config.minimum_island_pixels,
            maximum_bounds_pixels=(
                compact_deblend_config(config).maximum_compact_bounds_pixels
            ),
            minimum_support_fraction=(
                review.matrix.support_fraction_bounds[0]
            ),
            maximum_tiles_per_batch=_SUPPORT_TILES_PER_BATCH,
            maximum_batch_read_pixels=_OWNER_BATCH_READ_PIXELS,
        ),
        wcs_header_text=header.tostring(),
        beam=RestoringBeam(
            cast(float, header["BMAJ"]),
            cast(float, header["BMIN"]),
            cast(float, header["BPA"]) if "BPA" in header else 0.0,
        ),
        executor=executor,
        sink=sink,
    )
    bounds = ImageBounds(0, image_shape_yx[0], 0, image_shape_yx[1])
    return TiledComponentFits(
        parents=result.parents,
        measurement_support=np.asarray(
            sink.read_completed_window("measurement-support", bounds),
            dtype=np.bool_,
        ),
    )


def _analyse_image(  # noqa: PLR0913
    request: SourceFinderRequest,
    source: FitsImageSource,
    metadata: ImageMetadata,
    executor: Executor,
    work_directory: Path,
    *,
    config: SourceFinderConfig,
    header: fits.Header,
) -> _ScientificProducts:
    """Resolve the frozen terminal composition without changing its science."""
    from hebog.public_science import (  # noqa: PLC0415
        build_configured_continuum_products,
    )
    from hebog.science.profile import (  # noqa: PLC0415
        configured_science_profile,
        load_continuum_science_profile,
    )

    bounds = _full_bounds(metadata)
    image = np.asarray(source.read_window(bounds).values, dtype=np.float64)
    generation_id = (
        f"public-{hashlib.sha256(request.run_id.encode()).hexdigest()}"
    )
    background_rms_source, background, rms = _estimate_background_rms(
        source,
        metadata,
        config,
        executor,
        work_directory,
        generation_id=generation_id,
    )
    usable_rms = np.isfinite(rms) & (rms > 0)
    if not np.any(usable_rms):
        return _ScientificProducts(
            image=image,
            background=background,
            rms=np.full(metadata.shape_yx, np.nan, dtype=np.float64),
            terminal=None,
        )
    review = configured_science_profile(
        load_continuum_science_profile(_profile_bytes()),
        config,
    )
    beam = _beam_shape_pixels(metadata)
    detection_source, multiscale = detect_multiscale_products(
        source,
        background_rms_source,
        executor,
        work_directory,
        image_shape_yx=metadata.shape_yx,
        beam=beam,
        review=review,
        generation_id=generation_id,
    )
    support_source = reduce_support_topology(
        detection_source,
        executor,
        work_directory,
        image_shape_yx=metadata.shape_yx,
        scale_orders=tuple(
            range(1, len(multiscale.significant_scale_masks) + 1)
        ),
        generation_id=generation_id,
    )
    support_labels, labels_source = publish_support_labels(
        detection_source,
        support_source,
        executor,
        work_directory,
        image_shape_yx=metadata.shape_yx,
        beam=beam,
        detection_islands=multiscale.detection_islands,
        config=config,
        review=review,
        generation_id=generation_id,
    )
    component_source, topology = publish_component_topology(
        labels_source,
        detection_source,
        executor,
        work_directory,
        image_shape_yx=metadata.shape_yx,
        config=config,
        generation_id=generation_id,
    )
    terminal = build_configured_continuum_products(
        image,
        background,
        rms,
        header,
        beam=beam,
        review=review,
        config=config,
        multiscale=multiscale,
        labels=support_labels,
        topology=topology,
        component_fits=publish_component_fits(
            source,
            background_rms_source,
            detection_source,
            component_source,
            executor,
            work_directory,
            image_shape_yx=metadata.shape_yx,
            beam=beam,
            header=header,
            config=config,
            review=review,
            generation_id=generation_id,
        ),
    )
    return _ScientificProducts(image, background, rms, terminal)


def _shape(value: Any | None) -> GaussianShape | None:
    """Project one evaluated ellipse into the public catalogue model."""
    if value is None:
        return None
    return GaussianShape(
        major_fwhm_degrees=float(value.major_fwhm_degrees),
        minor_fwhm_degrees=float(value.minor_fwhm_degrees),
        position_angle_degrees=float(value.position_angle_degrees),
        major_fwhm_error_degrees=value.major_fwhm_error_degrees,
        minor_fwhm_error_degrees=value.minor_fwhm_error_degrees,
        position_angle_error_degrees=value.position_angle_error_degrees,
    )


def _source_candidate(
    value: Any,
    *,
    island_id: str,
    local_rms: float,
    reference_frequency_hz: float,
    additional_island_ids: tuple[str, ...] = (),
) -> SourceCandidate:
    """Project one evaluated source without changing its measurements."""
    quality_flags = set(value.quality_flags)
    if value.deconvolved_major_fwhm_degrees is not None:
        quality_flags.add("major-axis-only")
    else:
        quality_flags.discard("major-axis-only")
    return SourceCandidate(
        source_id=str(value.identifier),
        island_id=island_id,
        additional_island_ids=additional_island_ids,
        position=SkyPosition(
            right_ascension_degrees=float(value.right_ascension_degrees),
            declination_degrees=float(value.declination_degrees),
            right_ascension_error_degrees=(
                value.right_ascension_error_degrees
            ),
            declination_error_degrees=value.declination_error_degrees,
        ),
        flux=FluxMeasurement(
            peak_flux_jy_per_beam=float(value.peak_flux_jy_per_beam),
            peak_flux_error_jy_per_beam=value.peak_flux_error_jy_per_beam,
            integrated_flux_jy=float(value.integrated_flux_jy),
            integrated_flux_error_jy=value.integrated_flux_error_jy,
            local_rms_jy_per_beam=local_rms,
        ),
        spectral_model=SpectralModel(
            kind="reference-frequency-only",
            reference_frequency_hz=reference_frequency_hz,
            coefficients=(),
        ),
        fitted_shape=_shape(value.fitted_shape),
        deconvolved_shape=_shape(value.deconvolved_shape),
        deconvolved_major_fwhm_degrees=(value.deconvolved_major_fwhm_degrees),
        association_aperture_integrated_flux_jy=(
            value.association_integrated_flux_jy
        ),
        quality_flags=tuple(sorted(quality_flags)),
    )


def _support_local_rms(
    labels: npt.NDArray[np.integer[Any]],
    label_values: tuple[int, ...],
    products: _ScientificProducts,
    windows: tuple[tuple[slice, slice] | None, ...],
) -> float:
    """Return the median RMS over the exact support of these labels.

    The windows bound the work to the labels' own pixels, so a catalogue of
    many sources does not scan the whole image for each of them.

    Raises:
        SourceFinderError: If no supported pixel has a usable local RMS.
    """
    crop = _label_value_window(windows, label_values)
    if crop is not None:
        support = np.isin(labels[crop], label_values)
        rms = products.rms[crop]
        valid = support & np.isfinite(rms) & (rms > 0)
        if np.any(valid):
            return float(np.median(rms[valid]))
    raise SourceFinderError("catalogue support has no valid local RMS")


def _label_value_window(
    windows: tuple[tuple[slice, slice] | None, ...],
    label_values: tuple[int, ...],
) -> tuple[slice, slice] | None:
    """Return the window holding every one of these labels."""
    crops = [
        windows[value - 1]
        for value in label_values
        if 0 < value <= len(windows) and windows[value - 1] is not None
    ]
    if not crops:
        return None
    return (
        slice(
            min(crop[0].start for crop in crops if crop is not None),
            max(crop[0].stop for crop in crops if crop is not None),
        ),
        slice(
            min(crop[1].start for crop in crops if crop is not None),
            max(crop[1].stop for crop in crops if crop is not None),
        ),
    )


def _empty_catalogue(
    run_id: str,
    reference_frequency_hz: float,
) -> SourceCatalogue:
    """Return one valid source-free public catalogue."""
    return SourceCatalogue.create(
        catalogue_id=f"catalogue-{hashlib.sha256(run_id.encode()).hexdigest()}",
        coordinate_frame="icrs",
        position_epoch="J2000.0",
        reference_frequency_hz=reference_frequency_hz,
        islands=(),
        sources=(),
        gaussian_components=(),
    )


def _memberships(terminal: Any, profile: str) -> tuple[Any, ...]:
    """Select source associations or explicit singleton compact sources."""
    association = terminal.source_association
    if profile == "continuum":
        return cast(tuple[Any, ...], association.memberships)
    return tuple(
        CatalogueSourceMembership(
            source_id=component.component_id,
            component_ids=(component.component_id,),
        )
        for component in association.components
    )


def _detection_islands(
    products: _ScientificProducts,
    metadata: ImageMetadata,
    publication_mask: npt.NDArray[np.bool_],
    measurement_labels: npt.NDArray[np.integer[Any]],
) -> tuple[list[Island], dict[int, tuple[str, ...]]]:
    """Keep true mask connectivity separate from fitted source associations."""
    labels, _ = cast(
        tuple[npt.NDArray[np.int32], int],
        label(publication_mask, np.ones((3, 3), dtype=np.bool_)),
    )
    beam = _beam_shape_pixels(metadata)
    beam_area = (
        np.pi
        * beam.major_fwhm_pixels
        * beam.minor_fwhm_pixels
        / (4.0 * np.log(2.0))
    )
    islands: list[Island] = []
    identifiers: dict[int, str] = {}
    for index, bounds in enumerate(find_objects(labels), start=1):
        assert bounds is not None
        support = labels[bounds] == index
        first_y, first_x = np.unravel_index(np.argmax(support), support.shape)
        identifier = (
            f"island-detection-{int(first_y) + bounds[0].start}"
            f"-{int(first_x) + bounds[1].start}"
        )
        identifiers[index] = identifier
        residual = (products.image[bounds] - products.background[bounds])[
            support
        ]
        local_rms = products.rms[bounds][support]
        islands.append(
            Island(
                island_id=identifier,
                pixel_count=int(support.sum()),
                integrated_flux_jy=float(residual.sum() / beam_area),
                integrated_flux_error_jy=None,
                local_rms_jy_per_beam=float(np.median(local_rms)),
                mean_brightness_jy_per_beam=float(residual.mean()),
            )
        )
    positive = publication_mask & (measurement_labels > 0)
    pairs = np.unique(
        np.column_stack(
            (
                measurement_labels[positive],
                labels[positive],
            )
        ),
        axis=0,
    )
    owners: dict[int, list[str]] = {}
    for component_index, island_index in pairs:
        owners.setdefault(int(component_index), []).append(
            identifiers[int(island_index)]
        )
    return islands, {
        index: tuple(sorted(values)) for index, values in owners.items()
    }


def _public_catalogue(
    products: _ScientificProducts,
    metadata: ImageMetadata,
    *,
    run_id: str,
    profile: str,
) -> tuple[SourceCatalogue, npt.NDArray[np.bool_]]:
    """Project the exact evaluated source topology into stable public rows."""
    terminal = products.terminal
    if terminal is None:
        return (
            _empty_catalogue(run_id, metadata.reference_frequency_hz),
            np.zeros(metadata.shape_yx, dtype=np.bool_),
        )
    association = terminal.source_association
    labels = np.asarray(terminal.measurement_component_labels)
    components_by_id = {
        component.component_id: component
        for component in association.components
    }
    component_rows = {
        component.identifier: component
        for component in terminal.component_catalogue
    }
    source_rows = {source.identifier: source for source in terminal.catalogue}
    component_windows = label_windows(labels)
    source_candidates: list[SourceCandidate] = []
    gaussian_components: list[GaussianComponent] = []
    publication_mask = np.array(
        terminal.detection.retained_mask, dtype=np.bool_, copy=True
    )
    islands, component_islands = _detection_islands(
        products, metadata, publication_mask, labels
    )
    measured_components = {
        entry.object_id
        for entry in terminal.measurement_dispositions
        if entry.object_kind == "component" and entry.status == "measured"
    }
    for membership in _memberships(terminal, profile):
        source_id = membership.source_id
        source_row = (
            source_rows.get(source_id)
            if profile == "continuum"
            else component_rows.get(source_id)
        )
        if source_row is None or (
            "exact-owner-positive-residual-flux" in source_row.quality_flags
        ):
            continue
        label_values = tuple(
            components_by_id[component_id].label_value
            for component_id in membership.component_ids
        )
        local_rms = _support_local_rms(
            labels,
            label_values,
            products,
            component_windows,
        )
        island_ids = tuple(
            sorted(
                {
                    island
                    for value in label_values
                    for island in component_islands.get(value, ())
                }
            )
        )
        if not island_ids:
            # A measured owner may have lost all publication support. Keep
            # its disposition, not a catalogue row with a fictitious island.
            continue
        source_candidates.append(
            _source_candidate(
                source_row,
                island_id=island_ids[0],
                additional_island_ids=island_ids[1:],
                local_rms=local_rms,
                reference_frequency_hz=metadata.reference_frequency_hz,
            )
        )
        for component_id in membership.component_ids:
            if component_id not in measured_components:
                continue
            component_row = component_rows[component_id]
            component_label = components_by_id[component_id].label_value
            if component_label not in component_islands:
                continue
            component_rms = _support_local_rms(
                labels,
                (component_label,),
                products,
                component_windows,
            )
            candidate = _source_candidate(
                component_row,
                island_id=component_islands[component_label][0],
                additional_island_ids=component_islands[component_label][1:],
                local_rms=component_rms,
                reference_frequency_hz=metadata.reference_frequency_hz,
            )
            if candidate.fitted_shape is None:
                raise SourceFinderError(
                    "measured Gaussian has no fitted shape"
                )
            gaussian_components.append(
                GaussianComponent(
                    gaussian_component_id=component_id,
                    source_id=source_id,
                    island_id=candidate.island_id,
                    additional_island_ids=candidate.additional_island_ids,
                    position=candidate.position,
                    flux=candidate.flux,
                    spectral_model=candidate.spectral_model,
                    fitted_shape=candidate.fitted_shape,
                    deconvolved_shape=candidate.deconvolved_shape,
                    deconvolved_major_fwhm_degrees=(
                        candidate.deconvolved_major_fwhm_degrees
                    ),
                    quality_flags=candidate.quality_flags,
                )
            )
    catalogue = SourceCatalogue.create(
        catalogue_id=f"catalogue-{hashlib.sha256(run_id.encode()).hexdigest()}",
        coordinate_frame="icrs",
        position_epoch="J2000.0",
        reference_frequency_hz=metadata.reference_frequency_hz,
        islands=islands,
        sources=source_candidates,
        gaussian_components=gaussian_components,
    )
    publication_mask.setflags(write=False)
    return catalogue, publication_mask


def _public_dispositions(
    terminal: Any | None, catalogue: SourceCatalogue, profile: str
) -> tuple[MeasurementDisposition, ...]:
    """Link all measured/absent identities to the selected public profile."""
    if terminal is None:
        return ()
    components = tuple(
        entry
        for entry in terminal.measurement_dispositions
        if entry.object_kind == "component"
    )
    sources = (
        tuple(
            entry.model_copy(
                update={
                    "object_kind": "source",
                    "member_component_ids": (entry.object_id,),
                }
            )
            for entry in components
        )
        if profile == "compact"
        else tuple(
            entry
            for entry in terminal.measurement_dispositions
            if entry.object_kind == "source"
        )
    )
    published = {
        "source": {row.source_id for row in catalogue.sources},
        "component": {
            row.gaussian_component_id for row in catalogue.gaussian_components
        },
    }
    return tuple(
        entry.model_copy(
            update={
                "catalogue_row_published": (
                    entry.object_id in published[entry.object_kind]
                ),
            }
        )
        for entry in sorted(
            (*components, *sources),
            key=lambda item: (item.object_kind, item.object_id),
        )
    )


def _final_product(product: Any, output: Path) -> Any:
    """Rebase one immutable product record after bundle publication."""
    return product.model_copy(update={"path": output / product.path.name})


def _materialize_bundle(  # noqa: PLR0913
    request: SourceFinderRequest,
    config: SourceFinderConfig,
    metadata: ImageMetadata,
    products: _ScientificProducts,
    unpublished: Path,
    *,
    input_sha256: str,
    wall_seconds: float,
) -> SourceFinderResult:
    """Write and validate one unpublished complete public product bundle."""
    catalogue, mask = _public_catalogue(
        products,
        metadata,
        run_id=request.run_id,
        profile=config.profile,
    )
    rms_status = (
        "valid"
        if np.any(np.isfinite(products.rms) & (products.rms > 0))
        else "unavailable"
    )
    catalogue_product = write_catalogue_fits_product(
        unpublished / "catalogue.fits",
        catalogue,
    )
    rms_product = write_rms_fits_product(
        unpublished / "rms.fits",
        metadata,
        (np.asarray(products.rms, dtype=np.float64),),
        dtype=np.dtype("float64"),
        scientific_status=rms_status,
    )
    mask_product = write_mask_fits_product(
        unpublished / "source-mask.fits",
        metadata,
        (mask,),
    )
    profile_payload = _profile_bytes()
    diagnostics = PublicSourceFindingDiagnostics(
        run_id=request.run_id,
        profile=config.profile,
        profile_limitations=(
            ("extended-emission-incomplete",)
            if config.profile == "compact"
            else ()
        ),
        configuration_qualification=_configuration_qualification(config),
        source_count=len(catalogue.sources),
        gaussian_component_count=len(catalogue.gaussian_components),
        island_count=len(catalogue.islands),
        deblended_parent_count=(
            products.terminal.deblended_parent_count
            if products.terminal is not None
            else 0
        ),
        deferred_deblend_parent_count=(
            products.terminal.deferred_deblend_parent_count
            if products.terminal is not None
            else 0
        ),
        measurement_dispositions=_public_dispositions(
            products.terminal, catalogue, config.profile
        ),
        rms_scientific_status=cast(Any, rms_status),
        provenance=PublicSourceFindingProvenance(
            input_sha256=input_sha256,
            configuration_sha256=_canonical_sha256(asdict(config)),
            scientific_profile_sha256=hashlib.sha256(
                profile_payload
            ).hexdigest(),
            scientific_composition_sha256=(_scientific_composition_sha256()),
            scientific_composition=_COMPOSITION_NAME,
            supplied_image_metadata=request.supplied_metadata,
        ),
    )
    diagnostics_product = write_diagnostics_product(
        unpublished / "diagnostics.json",
        diagnostics,
    )
    output = request.output_directory
    return SourceFinderResult(
        run_id=request.run_id,
        catalogue=_final_product(catalogue_product, output),
        rms=_final_product(rms_product, output),
        mask=_final_product(mask_product, output),
        diagnostics=_final_product(diagnostics_product, output),
        source_count=len(catalogue.sources),
        gaussian_component_count=len(catalogue.gaussian_components),
        island_count=len(catalogue.islands),
        wall_seconds=wall_seconds,
    )


def find_sources(
    request: SourceFinderRequest,
    config: SourceFinderConfig,
    executor: Executor,
) -> SourceFinderResult:
    """Analyse one supported FITS image and atomically publish its products.

    The public finder supports ICRS or FK5 J2000 ``Jy/beam`` images no larger
    than 1024 pixels on either axis; catalogue positions are ICRS. Relative
    request paths are bound to the caller's working directory before any
    executor task is built. Caller thresholds are executed exactly;
    diagnostics distinguish the unqualified development candidate from custom
    unqualified science. ``compact`` intentionally omits extended-emission
    association.
    """
    output = Path(request.output_directory).absolute()
    _require_unclaimed_output(output)
    image_path = Path(request.image_path).absolute()
    request = replace(request, image_path=image_path, output_directory=output)
    try:
        source = FitsImageSource(image_path, request.supplied_metadata)
        metadata = source.metadata()
        header = _header_with_metadata(
            cast(fits.Header, fits.getheader(image_path)), metadata
        )
    except (OSError, ValueError) as error:
        raise InvalidSourceFinderInputError(
            f"invalid FITS source-finder input: {image_path}"
        ) from error
    _qualified_metadata(metadata)
    try:
        input_sha256 = _file_sha256(image_path)
    except OSError as error:
        raise InvalidSourceFinderInputError(
            f"invalid FITS source-finder input: {image_path}"
        ) from error
    output.parent.mkdir(parents=True, exist_ok=True)
    started = monotonic()
    try:
        with TemporaryDirectory(
            prefix=f".{output.name}.",
            dir=output.parent,
        ) as temporary_directory:
            temporary = Path(temporary_directory)
            scientific = _analyse_image(
                request,
                source,
                metadata,
                executor,
                temporary / "work",
                config=config,
                header=header,
            )
            unpublished = temporary / "bundle"
            unpublished.mkdir()
            result = _materialize_bundle(
                request,
                config,
                metadata,
                scientific,
                unpublished,
                input_sha256=input_sha256,
                wall_seconds=monotonic() - started,
            )
            _publish_bundle(unpublished, output)
    finally:
        # This call owns the source it opened, so it releases the input
        # when the run ends rather than leaving it to the collector.
        source.close()
    return result.model_copy(update={"wall_seconds": monotonic() - started})
