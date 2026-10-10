# pyright: reportUnknownMemberType=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
"""Outer I/O implementation of the public source-finding facade."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import warnings
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field, replace
from functools import lru_cache
from importlib.resources import files
from math import ceil, prod
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING, Any, Literal, cast

import numpy as np
import numpy.typing as npt
from astropy.io import fits
from astropy.wcs.utils import wcs_to_celestial_frame

from hebog.algorithms.astrometry import (
    celestial_wcs_from_metadata,
    compact_geometry_from_wcs,
)
from hebog.algorithms.multiscale import BeamShapePixels
from hebog.config import SourceFinderConfig
from hebog.data_models import (
    CatalogueSourceMembership,
    FluxMeasurement,
    GaussianComponent,
    GaussianShape,
    Island,
    PublicSourceFindingDiagnostics,
    PublicSourceFindingProvenance,
    SkyPosition,
    SourceCandidate,
    SourceCatalogue,
    SourceFinderRequest,
    SourceFinderResult,
    SpectralModel,
    WideObjectCounts,
)
from hebog.data_models.catalogues import POSITION_EPOCH
from hebog.data_models.images import ImageMetadata
from hebog.data_models.measurement_diagnostics import MeasurementDisposition
from hebog.executors import Executor
from hebog.io import FitsImageSource, InvalidFitsImageError, ZarrProductSink
from hebog.io.base import WindowReadable
from hebog.io.filesystem import rename_without_replacement
from hebog.io.materialization import (
    write_catalogue_fits_product,
    write_diagnostics_product,
    write_mask_fits_product,
    write_rms_fits_product,
)
from hebog.io.staging import reclaim_abandoned_staging, staging_directory
from hebog.pipeline import (
    InvalidSourceFinderInputError,
    SourceFinderError,
    SourceFinderImageTooLargeError,
    SourceFinderOutputExistsError,
    SourceFinderStagingWarning,
    UnsupportedSourceFinderConfigurationError,
)
from hebog.stages.composition import (
    restoring_beam_from_header,
    run_stages,
)

if TYPE_CHECKING:  # pragma: no cover - import-time typing only
    from importlib.resources.abc import Traversable

    from hebog.science.profile import ContinuumScienceProfile


_MAXIMUM_PREVIEW_DIMENSION = 15402
# The widest restoring beam, in pixels of FWHM along its major axis, that the
# finder is measured to serve. The background and noise meshes are fixed in
# pixels, and on injected isolated sources every source at SNR 10 or more is
# published at beams of 3 to 10 pixels under both profiles; from 12 pixels the
# continuum profile misses some, because a fine noise window that holds a
# source takes its emission for noise. Scaling the meshes with the beam is
# deferred, so a wider beam is refused. The limit is well inside the beam at
# which local-noise refinement would exceed its read bound.
_MAXIMUM_BEAM_FWHM_PIXELS = 10.0
# The width in pixels comes through a finite-difference WCS Jacobian whose
# round-off differs between platforms by up to about a millionth of the
# width: a beam stated as exactly 10 pixels can read 10.000001 on Linux and
# 10 on macOS. The limit compares the width to a thousandth of a pixel, so
# a beam stated at the limit is admitted on every platform.
_BEAM_LIMIT_DECIMALS = 3
_MASK_BLOCK_ROWS = 128
_DETECTION_THRESHOLD_SIGMA = 5.0
_ISLAND_THRESHOLD_SIGMA = 3.0
_MINIMUM_ISLAND_PIXELS = 7
_COMPOSITION_NAME = "phase-5-evidence-bound-public-catalogue-v22"
_PROFILE_RESOURCE = "reviewed_continuum_profile.json"
_FWHM_PER_SIGMA = 2.0 * np.sqrt(2.0 * np.log(2.0))
# The finite-difference WCS Jacobian is good to about 1e-10 of the local
# scale, and its round-off differs between platforms. Quantising the derived
# beam axes to 1e-6 pixel keeps whole-pixel beams exact on every platform,
# so ``ceil`` aperture radii and kernel halos cannot flip with the platform
# or a sub-mas WCS change.
_BEAM_AXIS_DECIMALS = 6
_SCIENTIFIC_MODULES = (
    "hebog.algorithms",
    "hebog.algorithms.astrometry",
    "hebog.algorithms.background",
    "hebog.algorithms.component_measurement",
    "hebog.algorithms.component_topology",
    "hebog.algorithms.deblending",
    "hebog.algorithms.detection",
    "hebog.algorithms.extended_measurement",
    "hebog.algorithms.fft",
    "hebog.algorithms.fitting",
    "hebog.algorithms.label_groups",
    "hebog.algorithms.labelling",
    "hebog.algorithms.measurement",
    "hebog.algorithms.multiscale",
    "hebog.algorithms.multiscale_association",
    "hebog.algorithms.multiscale_tiles",
    "hebog.algorithms.owner_connectivity",
    "hebog.algorithms.reconciliation",
    "hebog.algorithms.source_association",
    "hebog.config",
    "hebog.data_models",
    "hebog.data_models.astrometry",
    "hebog.data_models.catalogues",
    "hebog.data_models.fitting",
    "hebog.data_models.generations",
    "hebog.data_models.images",
    "hebog.data_models.measurement",
    "hebog.data_models.measurement_diagnostics",
    "hebog.data_models.multiscale",
    "hebog.data_models.partitioning",
    "hebog.data_models.products",
    "hebog.data_models.source_association",
    "hebog.data_models.source_finding",
    "hebog.executors",
    "hebog.executors.base",
    "hebog.executors.dask",
    "hebog.executors.serial",
    "hebog.executors.threads",
    "hebog.io",
    "hebog.io.base",
    "hebog.io.filesystem",
    "hebog.io.fits",
    "hebog.io.materialization",
    "hebog.io.pixel_validity",
    "hebog.io.staging",
    "hebog.io.zarr",
    "hebog.pipeline",
    "hebog.public_api",
    "hebog.public_science",
    "hebog.science",
    "hebog.science.catalogue_rows",
    "hebog.science.catalogues",
    "hebog.science.configuration",
    "hebog.science.continuum",
    "hebog.science.models",
    "hebog.science.profile",
    "hebog.stages",
    "hebog.stages.association",
    "hebog.stages.background",
    "hebog.stages.batching",
    "hebog.stages.catalogue_rows",
    "hebog.stages.composition",
    "hebog.stages.detection",
    "hebog.stages.islands",
    "hebog.stages.multiscale",
    "hebog.stages.objects",
    "hebog.stages.publication",
    "hebog.stages.sources",
    "hebog.stages.support",
)
"""Every module the finder imports, less ``_UNBOUND_MODULES``.

A unit test derives the finder's import closure from its import statements
and requires this list to equal it less the exemptions, so a module the
finder starts to import fails that test until it is bound or exempted. The
list is written out rather than derived when a run starts, because parsing
every module's imports would add about half a second to each run.
"""
_UNBOUND_MODULES = {
    "hebog": (
        "The package initializer only re-exports the public names and holds "
        "the version that Release Please rewrites at every release."
    ),
    "hebog.algorithms.partitioning": (
        "It plans tile geometry only, and every product is required to be "
        "the same on any tile grid, which the tile-invariance tests assert."
    ),
}
"""Modules the finder imports that the composition hash leaves out, and why.

Each must be shown not to decide a result. A unit test requires each to be
still imported and not bound, and the public product reference names them.
"""
_SCIENTIFIC_RESOURCES = "hebog.resources"
"""Package whose every data file the composition hash binds."""


@dataclass(frozen=True, slots=True)
class _ScientificProducts:
    """Exact evaluated science plus the candidate-owned background/RMS.

    The image, the background and the RMS are carried as the sources that
    published them rather than as planes, so nothing after the science holds
    an array that grows with the image, and no step after the science reads a
    window: every object was measured by the pass that held its tile.
    ``rms_scientific_status`` records the one decision the estimate makes
    about itself: whether any pixel has a usable local noise estimate.
    ``component_source`` is named for the same reason: the bundle needs no
    ownership plane, but a caller comparing these records with pixels reads
    that ownership from the generation that wrote it.
    """

    source: WindowReadable
    background_rms_source: ZarrProductSink
    publication_source: ZarrProductSink | None
    component_source: ZarrProductSink | None
    rms_scientific_status: Literal["valid", "unavailable"]
    terminal: Any | None
    wide_object_counts: WideObjectCounts = field(
        default_factory=WideObjectCounts
    )


def _require_unclaimed_output(output: Path) -> None:
    """Reject any existing destination, including a dangling symlink."""
    if output.exists() or output.is_symlink():
        raise SourceFinderOutputExistsError(
            f"source-finder output already exists: {output}"
        )


def _report_leftover_staging(output: Path) -> None:
    """Reclaim what stopped runs left beside the output, and report it all.

    A leftover never stops the run: the new run stages in a directory of
    its own, and the operator is told about each one with a warning.
    """
    for leftover in reclaim_abandoned_staging(output):
        # Attribute the warning to the caller of ``hebog.find_sources``.
        warnings.warn(
            leftover.notice, SourceFinderStagingWarning, stacklevel=4
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


def _frame_description(metadata: ImageMetadata) -> str:
    """Name a celestial frame with its equinox where it has one."""
    frame = cast(
        Any, wcs_to_celestial_frame(celestial_wcs_from_metadata(metadata))
    )
    equinox = getattr(frame, "equinox", None)
    name = str(frame.name).upper()
    return name if equinox is None else f"{name}, equinox {equinox.value:g}"


def _require_bounded_shape(image_shape_yx: tuple[int, int]) -> None:
    """Refuse a narrow image that one background estimate cannot read.

    The background meshes are 150 pixels wide and may span at most a quarter
    of the image's shorter side. Below 600 pixels they are shrunk, or one
    estimate is made for the whole image, and either reads the image in one
    task, which is bounded at a million pixels.
    """
    from hebog.science.configuration import (  # noqa: PLC0415
        source_finder_configs,
    )

    background = source_finder_configs()[0].background_rms
    narrow_below = ceil(
        max(background.coarse.window_shape_yx)
        / background.maximum_spatial_window_fraction
    )
    limit = background.maximum_constant_map_pixels
    if min(image_shape_yx) < narrow_below and prod(image_shape_yx) > limit:
        raise SourceFinderImageTooLargeError(
            f"the public source finder supports at most {limit:,} pixels in "
            f"an image whose shorter side is under {narrow_below} pixels, "
            f"not {image_shape_yx[0]} by {image_shape_yx[1]}"
        )


def _require_sampled_beam(metadata: ImageMetadata) -> None:
    """Refuse a restoring beam wider in pixels than the finder is measured for.

    The check comes before any filter is built: a beam given in the wrong
    unit, or a pixel scale that is nearly zero, is thousands of pixels wide.
    """
    try:
        beam = _beam_shape_pixels(metadata)
    except (np.linalg.LinAlgError, ValueError) as error:
        raise UnsupportedSourceFinderConfigurationError(
            "the restoring beam has no finite size in pixels at the image "
            "centre; check the beam and the pixel scale"
        ) from error
    # Written so that a width that is not a number is refused as well.
    width = round(beam.major_fwhm_pixels, _BEAM_LIMIT_DECIMALS)
    if not width <= _MAXIMUM_BEAM_FWHM_PIXELS:
        raise UnsupportedSourceFinderConfigurationError(
            "the public source finder supports a restoring beam of at most "
            f"{_MAXIMUM_BEAM_FWHM_PIXELS:g} pixels FWHM, not "
            f"{beam.major_fwhm_pixels:g}: its background and noise meshes "
            "are fixed in pixels, and on injected sources they miss sources "
            "from 12 pixels of beam; see the limitations in the input header "
            "contract"
        )


def _qualified_metadata(metadata: ImageMetadata) -> None:
    """Require the evaluated unit, frame, bounded size and beam sampling."""
    if metadata.unit != "Jy/beam":
        raise UnsupportedSourceFinderConfigurationError(
            "the public source finder requires BUNIT=Jy/beam, not "
            f"{metadata.unit}"
        )
    if not _supported_celestial_frame(metadata):
        raise UnsupportedSourceFinderConfigurationError(
            "the public source finder requires an ICRS or FK5 J2000 "
            "celestial WCS, not "
            f"{_frame_description(metadata)}"
        )
    if max(metadata.shape_yx) > _MAXIMUM_PREVIEW_DIMENSION:
        raise SourceFinderImageTooLargeError(
            "the public source finder supports at most "
            f"{_MAXIMUM_PREVIEW_DIMENSION} pixels per image dimension"
        )
    _require_bounded_shape(metadata.shape_yx)
    _require_sampled_beam(metadata)


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


def _profile_bytes() -> bytes:
    """Read the immutable reviewed science profile from the installed wheel."""
    return (
        files(_SCIENTIFIC_RESOURCES).joinpath(_PROFILE_RESOURCE).read_bytes()
    )


@lru_cache(maxsize=1)
def _scientific_composition_sha256() -> str:
    """Bind the finder's modules and every packaged resource.

    The modules are every one the finder imports except the named
    exemptions. They are located rather than imported, so hashing never
    loads the optional Dask executor. The hash is computed once a process,
    when the first run records its provenance.
    """
    digest = hashlib.sha256()
    for name, content in _scientific_composition_sources():
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    return digest.hexdigest()


def _scientific_composition_sources() -> Iterator[tuple[str, bytes]]:
    """Yield each bound module's and resource's name and bytes, in order."""
    for module_name in _SCIENTIFIC_MODULES:
        specification = importlib.util.find_spec(module_name)
        if specification is None or specification.origin is None:
            raise SourceFinderError(
                f"cannot identify scientific module {module_name}"
            )
        yield module_name, Path(specification.origin).read_bytes()
    yield from _resource_files(
        files(_SCIENTIFIC_RESOURCES), _SCIENTIFIC_RESOURCES
    )


def _resource_files(
    directory: Traversable, name: str
) -> Iterator[tuple[str, bytes]]:
    """Yield every file below one resource directory, by path, in order."""
    for item in sorted(directory.iterdir(), key=lambda item: item.name):
        path = f"{name}/{item.name}"
        if not item.is_dir():
            yield path, item.read_bytes()
        elif item.name != "__pycache__":
            yield from _resource_files(item, path)


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


def _stage_inputs(
    metadata: ImageMetadata,
    config: SourceFinderConfig,
) -> tuple[BeamShapePixels, ContinuumScienceProfile]:
    """Return the beam in pixel axes and the profile the stages apply.

    The profile is the installed one under the caller's thresholds.
    """
    from hebog.science.profile import (  # noqa: PLC0415
        configured_science_profile,
        load_continuum_science_profile,
    )

    return _beam_shape_pixels(metadata), configured_science_profile(
        load_continuum_science_profile(_profile_bytes()),
        config,
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
    """Run the stage sequence and build the terminal catalogues it feeds."""
    from hebog.public_science import (  # noqa: PLC0415
        build_configured_continuum_products,
    )

    beam, review = _stage_inputs(metadata, config)
    stages = run_stages(
        source,
        metadata,
        executor,
        work_directory,
        config=config,
        wcs_header_text=header.tostring(),
        restoring_beam=restoring_beam_from_header(header),
        beam=beam,
        review=review,
        generation_id=(
            f"public-{hashlib.sha256(request.run_id.encode()).hexdigest()}"
        ),
    )
    published = stages.published
    if published is None:
        return _ScientificProducts(
            source=source,
            background_rms_source=stages.background_rms_source,
            publication_source=None,
            component_source=None,
            rms_scientific_status=stages.rms_scientific_status,
            terminal=None,
        )
    records = published.records
    terminal = build_configured_continuum_products(
        header,
        component_count=records.accepted_island_count,
        topology=records.topology,
        measurements=records.measurements,
        association=records.association,
        hierarchy=records.hierarchy,
        component_rows=records.component_rows,
        source_rows=records.source_rows,
        source_positions=records.source_positions,
        component_local_rms=records.component_local_rms,
        source_local_rms=records.source_local_rms,
        islands=records.islands,
        island_ids_by_owner=records.island_ids_by_owner,
    )
    return _ScientificProducts(
        source=source,
        background_rms_source=stages.background_rms_source,
        publication_source=published.publication_source,
        component_source=published.component_source,
        rms_scientific_status=stages.rms_scientific_status,
        terminal=terminal,
        wide_object_counts=published.wide_object_counts,
    )


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


def _published_local_rms(terminal: Any, object_id: str) -> float:
    """Return the local noise the row pass measured over this owner's support.

    The pass that measured the owner's row read the estimate with it, so the
    catalogue quotes that value rather than reading the owner's window again.

    Raises:
        SourceFinderError: If no pixel the owner holds had a usable local RMS.
    """
    local_rms = terminal.local_rms_by_object_id.get(object_id)
    if local_rms is None:
        raise SourceFinderError("catalogue support has no valid local RMS")
    return float(local_rms)


def _empty_catalogue(
    run_id: str,
    reference_frequency_hz: float,
) -> SourceCatalogue:
    """Return one valid source-free public catalogue."""
    return SourceCatalogue.create(
        catalogue_id=f"catalogue-{hashlib.sha256(run_id.encode()).hexdigest()}",
        coordinate_frame="icrs",
        position_epoch=POSITION_EPOCH,
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


def _published_islands(terminal: Any) -> list[Island]:
    """Project the measured islands the retained mask's own rounds published.

    An island's flux is a signed sum over the pixels its mask retains, so it
    carries no uncertainty; every other field the public row needs was
    measured in the window that held the island.
    """
    return [
        Island(
            island_id=island.identifier,
            pixel_count=island.pixel_count,
            integrated_flux_jy=island.integrated_flux_jy,
            integrated_flux_error_jy=None,
            local_rms_jy_per_beam=island.local_rms_jy_per_beam,
            mean_brightness_jy_per_beam=island.mean_brightness_jy_per_beam,
        )
        for island in terminal.islands
    ]


def _public_catalogue(
    products: _ScientificProducts,
    metadata: ImageMetadata,
    *,
    run_id: str,
    profile: str,
) -> SourceCatalogue:
    """Project the exact evaluated source topology into stable public rows.

    Every row, every island and every local noise value was measured by the
    pass that held the window it belongs to, so this projection reads no
    pixels: it names records.
    """
    terminal = products.terminal
    if terminal is None:
        return _empty_catalogue(run_id, metadata.reference_frequency_hz)
    return _projected_catalogue(
        metadata,
        terminal,
        run_id=run_id,
        profile=profile,
    )


def _projected_catalogue(
    metadata: ImageMetadata,
    terminal: Any,
    *,
    run_id: str,
    profile: str,
) -> SourceCatalogue:
    """Project one evaluated composition that published at least one owner."""
    association = terminal.source_association
    components_by_id = {
        component.component_id: component
        for component in association.components
    }
    component_rows = {
        component.identifier: component
        for component in terminal.component_catalogue
    }
    source_rows = {source.identifier: source for source in terminal.catalogue}
    source_candidates: list[SourceCandidate] = []
    gaussian_components: list[GaussianComponent] = []
    islands = _published_islands(terminal)
    component_islands = terminal.island_ids_by_owner
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
        if source_row is None:
            continue
        label_values = tuple(
            components_by_id[component_id].label_value
            for component_id in membership.component_ids
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
            # Support publication keeps a retained pixel for every admitted
            # owner, and a component outside it takes its parent's islands,
            # so a measured source can never lack one. Refuse rather than
            # drop the row or invent an island.
            raise SourceFinderError("measured source reaches no island")
        source_candidates.append(
            _source_candidate(
                source_row,
                island_id=island_ids[0],
                additional_island_ids=island_ids[1:],
                local_rms=_published_local_rms(terminal, source_id),
                reference_frequency_hz=metadata.reference_frequency_hz,
            )
        )
        for component_id in membership.component_ids:
            if component_id not in measured_components:
                continue
            component_row = component_rows[component_id]
            component_label = components_by_id[component_id].label_value
            if component_label not in component_islands:
                raise SourceFinderError("measured Gaussian reaches no island")
            candidate = _source_candidate(
                component_row,
                island_id=component_islands[component_label][0],
                additional_island_ids=component_islands[component_label][1:],
                local_rms=_published_local_rms(terminal, component_id),
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
        position_epoch=POSITION_EPOCH,
        reference_frequency_hz=metadata.reference_frequency_hz,
        islands=islands,
        sources=source_candidates,
        gaussian_components=gaussian_components,
    )
    return catalogue


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


def _mask_row_blocks(
    products: _ScientificProducts,
    metadata: ImageMetadata,
) -> Iterator[npt.NDArray[np.bool_]]:
    """Yield the published retained mask as full-width row blocks.

    The mask product is the support pass's own retained mask, so it streams
    from that generation rather than from a plane the driver kept. An image
    whose estimate no pixel can use never reached the pass, and publishes an
    empty mask, which is what its consumers read as "nothing retained".
    """
    height, width = metadata.shape_yx
    if products.publication_source is None:
        for start in range(0, height, _MASK_BLOCK_ROWS):
            yield np.zeros(
                (min(_MASK_BLOCK_ROWS, height - start), width),
                dtype=np.bool_,
            )
        return
    rows = min(
        height,
        products.publication_source.manifest.tile_core_shape_yx[0],
    )
    for block in products.publication_source.iter_completed_row_blocks(
        "retained-mask",
        max_block_bytes=rows * width * np.dtype(np.bool_).itemsize,
    ):
        yield np.asarray(block, dtype=np.bool_)


def _rms_row_blocks(
    products: _ScientificProducts,
    metadata: ImageMetadata,
) -> Iterator[npt.NDArray[np.float64]]:
    """Yield the published RMS as full-width row blocks of one tile row.

    An estimate no pixel can use publishes an all-NaN product, which is what
    ``unavailable`` means to its consumers, so those rows are generated
    rather than read back from a store that holds the unusable estimate.
    Either way the block held at once grows with image width alone.
    """
    height, width = metadata.shape_yx
    block_rows = min(
        height,
        products.background_rms_source.manifest.tile_core_shape_yx[0],
    )
    if products.rms_scientific_status == "unavailable":
        for start in range(0, height, block_rows):
            yield np.full(
                (min(block_rows, height - start), width),
                np.nan,
                dtype=np.float64,
            )
        return
    for block in products.background_rms_source.iter_completed_row_blocks(
        "rms",
        max_block_bytes=block_rows * width * np.dtype(np.float64).itemsize,
    ):
        yield np.asarray(block, dtype=np.float64)


def _materialize_bundle(  # noqa: PLR0913
    request: SourceFinderRequest,
    config: SourceFinderConfig,
    metadata: ImageMetadata,
    products: _ScientificProducts,
    unpublished: Path,
    *,
    provenance: PublicSourceFindingProvenance,
    wall_seconds: float,
) -> SourceFinderResult:
    """Write and validate one unpublished complete public product bundle."""
    catalogue = _public_catalogue(
        products,
        metadata,
        run_id=request.run_id,
        profile=config.profile,
    )
    rms_status = products.rms_scientific_status
    catalogue_product = write_catalogue_fits_product(
        unpublished / "catalogue.fits",
        catalogue,
    )
    rms_product = write_rms_fits_product(
        unpublished / "rms.fits",
        metadata,
        _rms_row_blocks(products, metadata),
        dtype=np.dtype("float64"),
        scientific_status=rms_status,
    )
    mask_product = write_mask_fits_product(
        unpublished / "source-mask.fits",
        metadata,
        _mask_row_blocks(products, metadata),
    )
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
        wide_object_counts=products.wide_object_counts,
        measurement_dispositions=_public_dispositions(
            products.terminal, catalogue, config.profile
        ),
        rms_scientific_status=rms_status,
        provenance=provenance,
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


def _read_input(
    source: FitsImageSource,
    image_path: Path,
) -> tuple[ImageMetadata, fits.Header]:
    """Read the validated metadata and the header the science reads."""
    try:
        metadata = source.metadata()
        return metadata, _header_with_metadata(source.header(), metadata)
    except InvalidFitsImageError as error:
        # The reader names the keyword or layout at fault, and the file.
        raise InvalidSourceFinderInputError(
            f"invalid FITS source-finder input: {error}"
        ) from error
    except (OSError, ValueError) as error:
        raise InvalidSourceFinderInputError(
            f"invalid FITS source-finder input: {image_path}"
        ) from error


def _provenance(
    request: SourceFinderRequest,
    config: SourceFinderConfig,
) -> PublicSourceFindingProvenance:
    """Bind a run to its input, configuration and science before it starts.

    Every identity is known before the first pixel is analysed, so one that
    cannot be computed stops the run then and not after hours of work.
    """
    try:
        input_sha256 = _file_sha256(request.image_path)
    except OSError as error:
        raise InvalidSourceFinderInputError(
            f"invalid FITS source-finder input: {request.image_path}"
        ) from error
    return PublicSourceFindingProvenance(
        input_sha256=input_sha256,
        configuration_sha256=_canonical_sha256(asdict(config)),
        scientific_profile_sha256=hashlib.sha256(_profile_bytes()).hexdigest(),
        scientific_composition_sha256=_scientific_composition_sha256(),
        scientific_composition=_COMPOSITION_NAME,
        supplied_image_metadata=request.supplied_metadata,
    )


def find_sources(
    request: SourceFinderRequest,
    config: SourceFinderConfig,
    executor: Executor,
) -> SourceFinderResult:
    """Analyse one supported FITS image and atomically publish its products.

    The public finder supports ICRS or FK5 J2000 ``Jy/beam`` images no larger
    than 15,402 pixels on either axis; catalogue positions are ICRS. An image
    outside the input header contract is refused before the analysis starts,
    and the input file is released whatever the outcome. Relative
    request paths are bound to the caller's working directory before any
    executor task is built. Caller thresholds are executed exactly;
    diagnostics distinguish the unqualified development candidate from custom
    unqualified science. ``compact`` intentionally omits extended-emission
    association.

    The run stages its work in a hidden directory beside the output, which
    records its owner. A failed run raises only once no task it submitted
    is still running, and removes everything it staged. A killed run
    leaves its staging directory; the next run to the same output removes
    it once its owner has provably stopped, and otherwise leaves it in
    place, reporting each with a ``SourceFinderStagingWarning``.
    """
    output = Path(request.output_directory).absolute()
    _require_unclaimed_output(output)
    image_path = Path(request.image_path).absolute()
    request = replace(request, image_path=image_path, output_directory=output)
    source = FitsImageSource(image_path, request.supplied_metadata)
    try:
        metadata, header = _read_input(source, image_path)
        _qualified_metadata(metadata)
        provenance = _provenance(request, config)
        output.parent.mkdir(parents=True, exist_ok=True)
        _report_leftover_staging(output)
        started = monotonic()
        with staging_directory(output, run_id=request.run_id) as temporary:
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
                provenance=provenance,
                wall_seconds=monotonic() - started,
            )
            _publish_bundle(unpublished, output)
    finally:
        # This call owns the source it opened, so it releases the input
        # when the run ends, or is refused, rather than leaving it to the
        # collector: a caller handling the error may want to move the file.
        source.close()
    return result.model_copy(update={"wall_seconds": monotonic() - started})
