# pyright: reportUnknownMemberType=false
# pyright: reportMissingTypeStubs=false
"""Outer I/O implementation of the public source-finding facade."""

from __future__ import annotations

import hashlib
import importlib
import json
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from typing import Any, Literal, cast

import numpy as np
import numpy.typing as npt
from astropy.io import fits

from hebog.algorithms.astrometry import compact_geometry_at_pixel
from hebog.algorithms.multiscale import BeamShapePixels
from hebog.algorithms.partitioning import plan_image_partitions
from hebog.config import SourceFinderConfig
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
from hebog.data_models.images import ImageMetadata
from hebog.executors import Executor
from hebog.io import FitsImageSource, ZarrProductSink
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

_MAXIMUM_PREVIEW_DIMENSION = 1024
_TILE_SHAPE_YX = (128, 128)
_DETECTION_THRESHOLD_SIGMA = 5.0
_ISLAND_THRESHOLD_SIGMA = 3.0
_MINIMUM_ISLAND_PIXELS = 7
_COMPOSITION_NAME = "phase-5-configurable-publication-scale-persistence-v2"
_PROFILE_RESOURCE = "phase_5_continuum_review.json"
_FWHM_PER_SIGMA = 2.0 * np.sqrt(2.0 * np.log(2.0))
_SCIENTIFIC_MODULES = (
    "hebog.algorithms.astrometry",
    "hebog.algorithms.background",
    "hebog.algorithms.detection",
    "hebog.algorithms.extended_measurement",
    "hebog.algorithms.labelling",
    "hebog.algorithms.measurement",
    "hebog.algorithms.multiscale",
    "hebog.algorithms.multiscale_association",
    "hebog.algorithms.reconciliation",
    "hebog.algorithms.source_association",
    "hebog.public_api",
    "hebog.public_science",
    "hebog.stages.background",
    "hebog.stages.detection",
    "hebog.validation.hebog_campaign",
    "hebog.validation.mask_origin_sibling_pair",
    "hebog.validation.phase_five_filter_review",
    "hebog.validation.post_campaign_science",
    "hebog.validation.post_correction_recovery",
    "hebog.validation.products",
    "hebog.validation.public_finder_correction",
    "hebog.validation.publication_scale_persistence",
    "hebog.validation.publication_snr_repair",
)


@dataclass(frozen=True, slots=True)
class _ScientificProducts:
    """Exact evaluated science plus the candidate-owned background/RMS."""

    image: npt.NDArray[np.float64]
    background: npt.NDArray[np.float64]
    rms: npt.NDArray[np.float64]
    terminal: Any | None


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
) -> Literal["phase-5-reference", "custom-unqualified"]:
    """Classify caller science without restricting executable thresholds."""
    if (
        config.detection_threshold_sigma != _DETECTION_THRESHOLD_SIGMA
        or config.island_threshold_sigma != _ISLAND_THRESHOLD_SIGMA
        or config.minimum_island_pixels != _MINIMUM_ISLAND_PIXELS
        or config.maximum_island_pixels is not None
    ):
        return "custom-unqualified"
    return "phase-5-reference"


def _qualified_metadata(metadata: ImageMetadata) -> None:
    """Require the evaluated physical frame, unit, and bounded size."""
    if metadata.unit != "Jy/beam":
        raise UnsupportedSourceFinderConfigurationError(
            "the Phase 5 public preview requires BUNIT=Jy/beam"
        )
    if metadata.celestial_wcs.coordinate_frame != "icrs":
        raise UnsupportedSourceFinderConfigurationError(
            "the Phase 5 public preview requires an ICRS celestial WCS"
        )
    if max(metadata.shape_yx) > _MAXIMUM_PREVIEW_DIMENSION:
        raise SourceFinderImageTooLargeError(
            "the Phase 5 public preview supports at most 1024 pixels per "
            "image dimension"
        )


def _full_bounds(metadata: ImageMetadata) -> ImageBounds:
    """Return the complete bounded Phase 5 preview plane."""
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
    geometry = compact_geometry_at_pixel(
        metadata,
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
    if np.isclose(
        eigenvalues[major_index],
        eigenvalues[minor_index],
        rtol=1e-12,
        atol=0.0,
    ):
        angle = 0.0
    else:
        angle = float(
            np.rad2deg(np.arctan2(major_vector[1], major_vector[0])) % 180.0
        )
    return BeamShapePixels(
        major_fwhm_pixels=float(
            np.sqrt(eigenvalues[major_index]) * _FWHM_PER_SIGMA
        ),
        minor_fwhm_pixels=float(
            np.sqrt(eigenvalues[minor_index]) * _FWHM_PER_SIGMA
        ),
        position_angle_degrees=angle,
    )


def _estimate_background_rms(  # noqa: PLR0913
    source: FitsImageSource,
    metadata: ImageMetadata,
    config: SourceFinderConfig,
    executor: Executor,
    work_directory: Path,
    *,
    generation_id: str,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Run the exact candidate-owned bounded background/RMS stage."""
    from hebog.validation.hebog_campaign import (  # noqa: PLC0415
        phase_five_corrected_candidate_configs,
    )

    manifest = plan_image_partitions(
        image_shape_yx=metadata.shape_yx,
        tile_core_shape_yx=_TILE_SHAPE_YX,
        halo_yx=(0, 0),
    )
    sink = ZarrProductSink(
        work_directory / "detection.zarr",
        manifest,
        generation_id=generation_id,
    )
    detection_config = replace(
        phase_five_corrected_candidate_configs()[0],
        source_finder=config,
    )
    run_detection_stage(
        source,
        manifest,
        detection_config,
        executor,
        sink,
    )
    bounds = _full_bounds(metadata)
    return (
        np.asarray(
            sink.read_completed_window("background", bounds),
            dtype=np.float64,
        ),
        np.asarray(
            sink.read_completed_window("rms", bounds),
            dtype=np.float64,
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
    from hebog.validation.contracts import (  # noqa: PLC0415
        PhaseFiveCorrectiveAReview,
    )

    bounds = _full_bounds(metadata)
    image = np.asarray(source.read_window(bounds).values, dtype=np.float64)
    background, rms = _estimate_background_rms(
        source,
        metadata,
        config,
        executor,
        work_directory,
        generation_id=(
            f"public-{hashlib.sha256(request.run_id.encode()).hexdigest()}"
        ),
    )
    usable_rms = np.isfinite(rms) & (rms > 0)
    if not np.any(usable_rms):
        return _ScientificProducts(
            image=image,
            background=background,
            rms=np.full(metadata.shape_yx, np.nan, dtype=np.float64),
            terminal=None,
        )
    review = PhaseFiveCorrectiveAReview.model_validate_json(_profile_bytes())
    terminal = build_configured_continuum_products(
        image,
        background,
        rms,
        header,
        beam=_beam_shape_pixels(metadata),
        review=review,
        config=config,
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


def _support_statistics(
    labels: npt.NDArray[np.integer[Any]],
    label_values: tuple[int, ...],
    products: _ScientificProducts,
) -> tuple[npt.NDArray[np.bool_], float, float]:
    """Return exact support, local RMS, and mean residual brightness."""
    support = np.isin(labels, label_values)
    valid = support & np.isfinite(products.rms) & (products.rms > 0)
    if not np.any(valid):
        raise SourceFinderError("catalogue support has no valid local RMS")
    local_rms = float(np.median(products.rms[valid]))
    residual = products.image - products.background
    return support, local_rms, float(np.mean(residual[valid]))


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
    source_candidates: list[SourceCandidate] = []
    gaussian_components: list[GaussianComponent] = []
    islands: list[Island] = []
    publication_mask = np.zeros(metadata.shape_yx, dtype=np.bool_)
    for membership in _memberships(terminal, profile):
        source_id = membership.source_id
        source_row = (
            source_rows[source_id]
            if profile == "continuum"
            else component_rows[source_id]
        )
        label_values = tuple(
            components_by_id[component_id].label_value
            for component_id in membership.component_ids
        )
        support, local_rms, mean_brightness = _support_statistics(
            labels,
            label_values,
            products,
        )
        publication_mask |= support
        source_candidates.append(
            _source_candidate(
                source_row,
                island_id=source_id,
                local_rms=local_rms,
                reference_frequency_hz=metadata.reference_frequency_hz,
            )
        )
        islands.append(
            Island(
                island_id=source_id,
                pixel_count=int(np.count_nonzero(support)),
                integrated_flux_jy=float(source_row.integrated_flux_jy),
                integrated_flux_error_jy=source_row.integrated_flux_error_jy,
                local_rms_jy_per_beam=local_rms,
                mean_brightness_jy_per_beam=mean_brightness,
            )
        )
        for component_id in membership.component_ids:
            component_row = component_rows[component_id]
            component_label = components_by_id[component_id].label_value
            _, component_rms, _ = _support_statistics(
                labels,
                (component_label,),
                products,
            )
            candidate = _source_candidate(
                component_row,
                island_id=source_id,
                local_rms=component_rms,
                reference_frequency_hz=metadata.reference_frequency_hz,
            )
            if candidate.fitted_shape is None:
                raise SourceFinderError(
                    "evaluated Gaussian component has no fitted shape"
                )
            gaussian_components.append(
                GaussianComponent(
                    gaussian_component_id=component_id,
                    source_id=source_id,
                    island_id=source_id,
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
        rms_scientific_status=cast(Any, rms_status),
        provenance=PublicSourceFindingProvenance(
            input_sha256=input_sha256,
            configuration_sha256=_canonical_sha256(asdict(config)),
            scientific_profile_sha256=hashlib.sha256(
                profile_payload
            ).hexdigest(),
            scientific_composition_sha256=(_scientific_composition_sha256()),
            scientific_composition=_COMPOSITION_NAME,
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

    The Phase 5 scientific preview supports ICRS ``Jy/beam`` images no larger
    than 1024 pixels on either axis. Caller thresholds are executed exactly;
    diagnostics distinguish the Phase 5 reference configuration from custom
    unqualified science. ``compact`` intentionally omits extended-emission
    association.
    """
    output = Path(request.output_directory)
    if output.exists():
        raise SourceFinderOutputExistsError(
            f"source-finder output already exists: {output}"
        )
    image_path = Path(request.image_path)
    try:
        source = FitsImageSource(image_path)
        metadata = source.metadata()
        header = cast(fits.Header, fits.getheader(image_path))
        input_sha256 = _file_sha256(image_path)
    except (OSError, ValueError) as error:
        raise InvalidSourceFinderInputError(
            f"invalid FITS source-finder input: {image_path}"
        ) from error
    _qualified_metadata(metadata)
    output.parent.mkdir(parents=True, exist_ok=True)
    started = monotonic()
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
        unpublished.replace(output)
    return result.model_copy(update={"wall_seconds": monotonic() - started})
