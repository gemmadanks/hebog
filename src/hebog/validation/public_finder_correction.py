# pyright: reportMissingTypeStubs=false
"""Non-executable public source-finding records for Phase 5 correction."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Literal, cast

import numpy as np
import numpy.typing as npt
from astropy.io import fits

from hebog.algorithms.multiscale import BeamShapePixels
from hebog.data_models.catalogues import (
    FluxMeasurement,
    GaussianShape,
    SkyPosition,
    SourceCandidate,
    SpectralModel,
)
from hebog.data_models.source_association import SourceAssociationResult
from hebog.validation.comparison import CatalogueEllipse, CatalogueSource
from hebog.validation.contracts import PhaseFiveCorrectiveAReview
from hebog.validation.external_runners import file_sha256
from hebog.validation.phase_five_filter_review import ThresholdFilterResult
from hebog.validation.post_campaign_science import (
    CONTINUUM_MEASUREMENT_APERTURE_RADIUS_BEAMS,
    evaluate_public_finder_correction_candidate_products,
)
from hebog.validation.post_correction_recovery import (
    post_correction_candidate_configuration,
)
from hebog.validation.products import (
    build_hebog_associated_moment_catalogues,
    build_hebog_reconstructed_source_catalogues,
)

_ARCSECONDS_PER_DEGREE = 3600.0
_HALF_CIRCLE_DEGREES = 180.0
_FULL_CIRCLE_DEGREES = 360.0
_QUARTER_CIRCLE_DEGREES = 90.0
_SDC1_SIZE_CODE: Literal[2] = 2
_MOMENT_SHAPE_PROVENANCE = "segment-moment-equivalent-shape"
_PUBLIC_SUPPORT_POLICY = (
    "direct-seed-nearest-owner-half-beam-multiscale-recovery"
)
_PUBLIC_SHAPE_POLICY = "exact-owner-positive-residual-moment-equivalent"
_SOURCE_ASSOCIATION_POLICY = (
    "undilated-three-sigma-directional-fwhm-complete-link-v1"
)
_SOURCE_RECONSTRUCTION_POLICY = (
    "undilated-adjacent-scale-unambiguous-common-parent-v1"
)
_SOURCE_RECONSTRUCTION_ACTIVATION_POLICY = (
    "direct-seed-nearest-persistent-common-convergence-v2"
)
_SOURCE_RECONSTRUCTION_TELEMETRY_POLICY = (
    "array-free-hierarchy-activation-census-v1"
)
_SOURCE_HIERARCHY_PARENT_CONSTRUCTION_POLICY = (
    "b3-footprint-cycle-supported-adjacent-persistent-parent-v1"
)
_SOURCE_HIERARCHY_PARENT_TELEMETRY_POLICY = (
    "array-free-scale-parent-candidate-acceptance-census-v1"
)
_PERSISTENT_SUPPORT_CORROBORATION_POLICY = (
    "adjacent-significant-support-corroboration-no-membership-v1"
)
_TERMINAL_CYCLE_PARENT_POLICY = (
    "three-feature-cycle-all-constituents-adjacent-persistent-v1"
)
_TERMINAL_FEATURE_PERSISTENCE_POLICY = (
    "exact-or-mutually-unique-displaced-b3-support-child-v1"
)
_TERMINAL_FEATURE_PERSISTENCE_TELEMETRY_POLICY = (
    "array-free-terminal-persistence-rejection-census-v1"
)
_SOURCE_MEASUREMENT_POLICY = "disjoint-source-owned-aperture-moment-v1"
_CONNECTED_SUPPORT_POLICY = (
    "direct-seed-connected-half-beam-multiscale-recovery-v1"
)
_SOURCE_TOPOLOGY_POLICY = (
    "binding-catalogue-source-diagnostic-detection-component-v1"
)
_IMAGE_DIMENSIONS = 2


@dataclass(frozen=True, slots=True)
class PublicFinderCorrectionContinuumProducts:
    """Binding associated sources and immutable component diagnostics."""

    detection: ThresholdFilterResult
    catalogue: tuple[CatalogueSource, ...]
    valid_pixels: npt.NDArray[np.bool_]
    component_catalogue: tuple[CatalogueSource, ...]
    source_association: SourceAssociationResult


@dataclass(frozen=True, slots=True)
class Sdc1SourceFindingRecord:
    """Hebog fields with meanings shared by SDC1 source finding only."""

    identifier: str
    right_ascension_degrees: float
    declination_degrees: float
    apparent_integrated_flux_jy: float
    major_fwhm_arcseconds: float
    minor_fwhm_arcseconds: float
    position_angle_clockwise_from_west_degrees: float | None
    deconvolution_status: Literal["resolved", "unresolved"]
    size_code: Literal[2]
    core_fraction: None = None
    source_class: None = None
    official_global_score_eligible: Literal[False] = False

    def __post_init__(self) -> None:
        """Require physical source-finding fields and explicit absence."""
        values = (
            self.right_ascension_degrees,
            self.declination_degrees,
            self.apparent_integrated_flux_jy,
            self.major_fwhm_arcseconds,
            self.minor_fwhm_arcseconds,
        )
        if not self.identifier or not all(isfinite(value) for value in values):
            raise ValueError("SDC1 source-finding values must be finite")
        if not (
            0.0 <= self.right_ascension_degrees < _FULL_CIRCLE_DEGREES
            and -_QUARTER_CIRCLE_DEGREES
            <= self.declination_degrees
            <= _QUARTER_CIRCLE_DEGREES
        ):
            raise ValueError("SDC1 source-finding coordinates are invalid")
        if self.apparent_integrated_flux_jy <= 0.0:
            raise ValueError("SDC1 apparent flux must be positive")
        if not (
            self.major_fwhm_arcseconds >= self.minor_fwhm_arcseconds >= 0.0
        ):
            raise ValueError("SDC1 source-finding axes must be ordered")
        if self.deconvolution_status == "resolved":
            angle = self.position_angle_clockwise_from_west_degrees
            if (
                self.minor_fwhm_arcseconds <= 0.0
                or angle is None
                or not isfinite(angle)
                or not 0.0 <= angle < _HALF_CIRCLE_DEGREES
            ):
                raise ValueError("resolved SDC1 shape must be complete")
        elif self.deconvolution_status == "unresolved":
            if (
                self.major_fwhm_arcseconds != 0.0
                or self.minor_fwhm_arcseconds != 0.0
                or self.position_angle_clockwise_from_west_degrees is not None
            ):
                raise ValueError("unresolved SDC1 shape must remain axis-free")
        else:
            raise ValueError("SDC1 deconvolution status is unsupported")
        if (
            self.size_code != _SDC1_SIZE_CODE
            or self.core_fraction is not None
            or self.source_class is not None
            or self.official_global_score_eligible is not False
        ):
            raise ValueError(
                "SDC1 unsupported fields must remain explicitly unavailable"
            )


def build_sdc1_source_finding_records(
    sources: Sequence[CatalogueSource],
) -> tuple[Sdc1SourceFindingRecord, ...]:
    """Map characterized sources without I/O, scoring, or classification.

    This deliberately partial adapter cannot serialize an official submission
    or compute the global challenge score. It exposes only position, Gaussian
    FWHM size, and apparent integrated flux for a separately reviewed scorer.
    """
    output: list[Sdc1SourceFindingRecord] = []
    identifiers: set[str] = set()
    for source in sources:
        if source.identifier in identifiers:
            raise ValueError("SDC1 source-finding identifiers must be unique")
        identifiers.add(source.identifier)
        if _MOMENT_SHAPE_PROVENANCE not in source.quality_flags:
            raise ValueError(
                "SDC1 source-finding shape requires moment provenance"
            )
        shape = source.deconvolved_shape
        if source.deconvolution_status == "resolved" and shape is not None:
            major_arcseconds = (
                shape.major_fwhm_degrees * _ARCSECONDS_PER_DEGREE
            )
            minor_arcseconds = (
                shape.minor_fwhm_degrees * _ARCSECONDS_PER_DEGREE
            )
            position_angle = (
                shape.position_angle_degrees + 90.0
            ) % _HALF_CIRCLE_DEGREES
            status: Literal["resolved", "unresolved"] = "resolved"
        elif source.deconvolution_status == "unresolved" and shape is None:
            major_arcseconds = 0.0
            minor_arcseconds = 0.0
            position_angle = None
            status = "unresolved"
        else:
            raise ValueError(
                "SDC1 source-finding requires a resolved moment-equivalent "
                "shape or explicit unresolved state"
            )
        apparent_flux = (
            source.association_integrated_flux_jy
            if source.association_integrated_flux_jy is not None
            else source.integrated_flux_jy
        )
        output.append(
            Sdc1SourceFindingRecord(
                identifier=source.identifier,
                right_ascension_degrees=source.right_ascension_degrees,
                declination_degrees=source.declination_degrees,
                apparent_integrated_flux_jy=apparent_flux,
                major_fwhm_arcseconds=major_arcseconds,
                minor_fwhm_arcseconds=minor_arcseconds,
                position_angle_clockwise_from_west_degrees=position_angle,
                deconvolution_status=status,
                size_code=_SDC1_SIZE_CODE,
            )
        )
    return tuple(output)


def _public_gaussian_shape(
    shape: CatalogueEllipse,
) -> GaussianShape:
    """Map one validated comparison ellipse to the canonical public model."""
    return GaussianShape(
        major_fwhm_degrees=shape.major_fwhm_degrees,
        minor_fwhm_degrees=shape.minor_fwhm_degrees,
        position_angle_degrees=shape.position_angle_degrees,
        major_fwhm_error_degrees=shape.major_fwhm_error_degrees,
        minor_fwhm_error_degrees=shape.minor_fwhm_error_degrees,
        position_angle_error_degrees=shape.position_angle_error_degrees,
    )


def build_public_moment_source_candidate(
    source: CatalogueSource,
    *,
    local_rms_jy_per_beam: float,
    reference_frequency_hz: float,
) -> SourceCandidate:
    """Map one moment record to the canonical pipeline-neutral source row."""
    if _MOMENT_SHAPE_PROVENANCE not in source.quality_flags:
        raise ValueError("public source candidate requires moment provenance")
    fitted_shape = (
        _public_gaussian_shape(source.fitted_shape)
        if source.fitted_shape is not None
        else None
    )
    deconvolved_shape = (
        _public_gaussian_shape(source.deconvolved_shape)
        if source.deconvolved_shape is not None
        else None
    )
    return SourceCandidate(
        source_id=source.identifier,
        island_id=source.island_identifier or source.identifier,
        position=SkyPosition(
            right_ascension_degrees=source.right_ascension_degrees,
            declination_degrees=source.declination_degrees,
            right_ascension_error_degrees=(
                source.right_ascension_error_degrees
            ),
            declination_error_degrees=source.declination_error_degrees,
        ),
        flux=FluxMeasurement(
            peak_flux_jy_per_beam=source.peak_flux_jy_per_beam,
            peak_flux_error_jy_per_beam=source.peak_flux_error_jy_per_beam,
            integrated_flux_jy=source.integrated_flux_jy,
            integrated_flux_error_jy=source.integrated_flux_error_jy,
            local_rms_jy_per_beam=local_rms_jy_per_beam,
        ),
        spectral_model=SpectralModel(
            kind="reference-frequency-only",
            reference_frequency_hz=reference_frequency_hz,
            coefficients=(),
        ),
        fitted_shape=fitted_shape,
        deconvolved_shape=deconvolved_shape,
        deconvolved_major_fwhm_degrees=(source.deconvolved_major_fwhm_degrees),
        association_aperture_integrated_flux_jy=(
            source.association_integrated_flux_jy
        ),
        quality_flags=tuple(sorted(source.quality_flags)),
    )


def public_finder_correction_candidate_configuration(
    base_review_path: Path,
    correction_contract_path: Path,
) -> dict[str, object]:
    """Return the prospective correction without an executable runtime."""
    base = post_correction_candidate_configuration(base_review_path)
    continuum_value = base["continuum"]
    if not isinstance(continuum_value, dict):
        raise TypeError("base Continuum configuration must be a dictionary")
    continuum = dict(cast(dict[str, object], continuum_value))
    continuum.update(
        {
            "correction_contract_sha256": file_sha256(
                correction_contract_path
            ),
            "support_policy": _PUBLIC_SUPPORT_POLICY,
            "shape_policy": _PUBLIC_SHAPE_POLICY,
        }
    )
    return {"compact": base["compact"], "continuum": continuum}


def public_finder_source_association_candidate_configuration(
    base_review_path: Path,
    correction_contract_path: Path,
    source_association_pre_review_path: Path,
    implementation_decision_path: Path,
) -> dict[str, object]:
    """Return the non-executable source-association candidate identity."""
    base = public_finder_correction_candidate_configuration(
        base_review_path,
        correction_contract_path,
    )
    continuum_value = base["continuum"]
    if not isinstance(continuum_value, dict):
        raise TypeError("base Continuum configuration must be a dictionary")
    continuum = dict(cast(dict[str, object], continuum_value))
    continuum.update(
        {
            "source_association_policy": _SOURCE_ASSOCIATION_POLICY,
            "source_association_pre_review_sha256": file_sha256(
                source_association_pre_review_path
            ),
            "source_association_implementation_decision_sha256": (
                file_sha256(implementation_decision_path)
            ),
        }
    )
    return {"compact": base["compact"], "continuum": continuum}


def public_finder_source_reconstruction_candidate_configuration(
    base_review_path: Path,
    correction_contract_path: Path,
    source_reconstruction_pre_review_path: Path,
    implementation_decision_path: Path,
) -> dict[str, object]:
    """Return the non-executable source-reconstruction candidate identity."""
    base = public_finder_correction_candidate_configuration(
        base_review_path,
        correction_contract_path,
    )
    continuum_value = base["continuum"]
    if not isinstance(continuum_value, dict):
        raise TypeError("base Continuum configuration must be a dictionary")
    continuum = dict(cast(dict[str, object], continuum_value))
    continuum.update(
        {
            "source_reconstruction_policy": _SOURCE_RECONSTRUCTION_POLICY,
            "source_measurement_policy": _SOURCE_MEASUREMENT_POLICY,
            "connected_support_policy": _CONNECTED_SUPPORT_POLICY,
            "source_topology_policy": _SOURCE_TOPOLOGY_POLICY,
            "source_reconstruction_pre_review_sha256": file_sha256(
                source_reconstruction_pre_review_path
            ),
            "source_reconstruction_implementation_decision_sha256": (
                file_sha256(implementation_decision_path)
            ),
        }
    )
    return {"compact": base["compact"], "continuum": continuum}


def public_finder_source_reconstruction_root_cause_repair_configuration(  # noqa: PLR0913, PLR0917
    base_review_path: Path,
    correction_contract_path: Path,
    source_reconstruction_pre_review_path: Path,
    source_reconstruction_decision_path: Path,
    root_cause_pre_review_path: Path,
    root_cause_implementation_decision_path: Path,
) -> dict[str, object]:
    """Return the approved non-executable hierarchy-activation identity."""
    base = public_finder_source_reconstruction_candidate_configuration(
        base_review_path,
        correction_contract_path,
        source_reconstruction_pre_review_path,
        source_reconstruction_decision_path,
    )
    continuum_value = base["continuum"]
    if not isinstance(continuum_value, dict):
        raise TypeError("base Continuum configuration must be a dictionary")
    continuum = dict(cast(dict[str, object], continuum_value))
    continuum.update(
        {
            "source_reconstruction_activation_policy": (
                _SOURCE_RECONSTRUCTION_ACTIVATION_POLICY
            ),
            "source_reconstruction_telemetry_policy": (
                _SOURCE_RECONSTRUCTION_TELEMETRY_POLICY
            ),
            "source_reconstruction_root_cause_pre_review_sha256": (
                file_sha256(root_cause_pre_review_path)
            ),
            (
                "source_reconstruction_root_cause_implementation_"
                "decision_sha256"
            ): file_sha256(root_cause_implementation_decision_path),
        }
    )
    return {"compact": base["compact"], "continuum": continuum}


def public_finder_source_hierarchy_parent_construction_configuration(  # noqa: PLR0913, PLR0917
    base_review_path: Path,
    correction_contract_path: Path,
    source_reconstruction_pre_review_path: Path,
    source_reconstruction_decision_path: Path,
    root_cause_pre_review_path: Path,
    root_cause_implementation_decision_path: Path,
    parent_construction_pre_review_path: Path,
    parent_construction_implementation_decision_path: Path,
) -> dict[str, object]:
    """Return the approved non-executable parent-construction identity."""
    base = public_finder_source_reconstruction_root_cause_repair_configuration(
        base_review_path,
        correction_contract_path,
        source_reconstruction_pre_review_path,
        source_reconstruction_decision_path,
        root_cause_pre_review_path,
        root_cause_implementation_decision_path,
    )
    continuum_value = base["continuum"]
    if not isinstance(continuum_value, dict):
        raise TypeError("base Continuum configuration must be a dictionary")
    continuum = dict(cast(dict[str, object], continuum_value))
    continuum.update(
        {
            "source_hierarchy_parent_construction_policy": (
                _SOURCE_HIERARCHY_PARENT_CONSTRUCTION_POLICY
            ),
            "source_hierarchy_parent_telemetry_policy": (
                _SOURCE_HIERARCHY_PARENT_TELEMETRY_POLICY
            ),
            "source_hierarchy_parent_construction_pre_review_sha256": (
                file_sha256(parent_construction_pre_review_path)
            ),
            (
                "source_hierarchy_parent_construction_implementation_"
                "decision_sha256"
            ): file_sha256(parent_construction_implementation_decision_path),
        }
    )
    return {"compact": base["compact"], "continuum": continuum}


def public_finder_terminal_parent_correction_configuration(  # noqa: PLR0913, PLR0917
    base_review_path: Path,
    correction_contract_path: Path,
    source_reconstruction_pre_review_path: Path,
    source_reconstruction_decision_path: Path,
    root_cause_pre_review_path: Path,
    root_cause_implementation_decision_path: Path,
    parent_construction_pre_review_path: Path,
    parent_construction_implementation_decision_path: Path,
    terminal_parent_review_path: Path,
    terminal_parent_implementation_decision_path: Path,
) -> dict[str, object]:
    """Return the non-executable terminal-parent correction identity."""
    base = public_finder_source_hierarchy_parent_construction_configuration(
        base_review_path,
        correction_contract_path,
        source_reconstruction_pre_review_path,
        source_reconstruction_decision_path,
        root_cause_pre_review_path,
        root_cause_implementation_decision_path,
        parent_construction_pre_review_path,
        parent_construction_implementation_decision_path,
    )
    continuum_value = base["continuum"]
    if not isinstance(continuum_value, dict):
        raise TypeError("base Continuum configuration must be a dictionary")
    continuum = dict(cast(dict[str, object], continuum_value))
    continuum.update(
        {
            "persistent_support_corroboration_policy": (
                _PERSISTENT_SUPPORT_CORROBORATION_POLICY
            ),
            "terminal_cycle_parent_policy": _TERMINAL_CYCLE_PARENT_POLICY,
            "terminal_parent_review_sha256": file_sha256(
                terminal_parent_review_path
            ),
            "terminal_parent_implementation_decision_sha256": file_sha256(
                terminal_parent_implementation_decision_path
            ),
        }
    )
    return {"compact": base["compact"], "continuum": continuum}


def public_finder_terminal_feature_persistence_configuration(  # noqa: PLR0913, PLR0917
    base_review_path: Path,
    correction_contract_path: Path,
    source_reconstruction_pre_review_path: Path,
    source_reconstruction_decision_path: Path,
    root_cause_pre_review_path: Path,
    root_cause_implementation_decision_path: Path,
    parent_construction_pre_review_path: Path,
    parent_construction_implementation_decision_path: Path,
    terminal_parent_review_path: Path,
    terminal_parent_implementation_decision_path: Path,
    terminal_feature_pre_review_path: Path,
    terminal_feature_implementation_decision_path: Path,
) -> dict[str, object]:
    """Return the non-executable displaced-child persistence identity."""
    base = public_finder_terminal_parent_correction_configuration(
        base_review_path,
        correction_contract_path,
        source_reconstruction_pre_review_path,
        source_reconstruction_decision_path,
        root_cause_pre_review_path,
        root_cause_implementation_decision_path,
        parent_construction_pre_review_path,
        parent_construction_implementation_decision_path,
        terminal_parent_review_path,
        terminal_parent_implementation_decision_path,
    )
    continuum_value = base["continuum"]
    if not isinstance(continuum_value, dict):
        raise TypeError("base Continuum configuration must be a dictionary")
    continuum = dict(cast(dict[str, object], continuum_value))
    continuum.update(
        {
            "terminal_feature_persistence_policy": (
                _TERMINAL_FEATURE_PERSISTENCE_POLICY
            ),
            "terminal_feature_persistence_telemetry_policy": (
                _TERMINAL_FEATURE_PERSISTENCE_TELEMETRY_POLICY
            ),
            "terminal_feature_persistence_pre_review_sha256": file_sha256(
                terminal_feature_pre_review_path
            ),
            (
                "terminal_feature_persistence_implementation_decision_sha256"
            ): file_sha256(terminal_feature_implementation_decision_path),
        }
    )
    return {"compact": base["compact"], "continuum": continuum}


def _aligned_public_plane(
    values: npt.ArrayLike,
    *,
    name: str,
    shape: tuple[int, int] | None = None,
) -> npt.NDArray[np.float64]:
    """Return one real two-dimensional prospective input plane."""
    plane = np.asarray(values)
    if (
        plane.ndim != _IMAGE_DIMENSIONS
        or not np.issubdtype(plane.dtype, np.number)
        or np.iscomplexobj(plane)
        or (shape is not None and plane.shape != shape)
    ):
        raise ValueError(
            f"public-finder correction {name} must be an aligned real "
            "two-dimensional plane"
        )
    return np.asarray(plane, dtype=np.float64)


def build_public_finder_correction_continuum_products(  # noqa: PLR0913
    image_jy_per_beam: npt.ArrayLike,
    background_jy_per_beam: npt.ArrayLike,
    rms_jy_per_beam: npt.ArrayLike,
    header: fits.Header,
    *,
    beam: BeamShapePixels,
    review: PhaseFiveCorrectiveAReview,
) -> PublicFinderCorrectionContinuumProducts:
    """Build the prospective seeded-owner and moment-shape candidate."""
    image = _aligned_public_plane(image_jy_per_beam, name="image")
    background = _aligned_public_plane(
        background_jy_per_beam,
        name="background",
        shape=image.shape,
    )
    rms = _aligned_public_plane(
        rms_jy_per_beam,
        name="RMS",
        shape=image.shape,
    )
    valid = np.isfinite(image) & np.isfinite(background) & np.isfinite(rms)
    if np.any(np.isfinite(image) != valid):
        raise ValueError(
            "public-finder correction mean/RMS validity differs from image"
        )
    products = evaluate_public_finder_correction_candidate_products(
        image,
        valid,
        background,
        rms,
        beam=beam,
        review=review,
    )
    catalogues = build_hebog_associated_moment_catalogues(
        image,
        background,
        valid,
        products.detection.component_labels,
        products.significant_multiscale_support,
        products.detection.combined_snr,
        header,
        beam_major_fwhm_pixels=beam.major_fwhm_pixels,
        beam_minor_fwhm_pixels=beam.minor_fwhm_pixels,
        island_threshold_sigma=review.matrix.island_sigma,
        measurement_aperture_radius_beams=(
            CONTINUUM_MEASUREMENT_APERTURE_RADIUS_BEAMS
        ),
        position_signal_jy_per_beam=products.position_signal_jy_per_beam,
    )
    valid.setflags(write=False)
    return PublicFinderCorrectionContinuumProducts(
        detection=products.detection,
        catalogue=catalogues.source_catalogue,
        valid_pixels=valid,
        component_catalogue=catalogues.component_catalogue,
        source_association=catalogues.association,
    )


def build_public_finder_source_reconstruction_continuum_products(  # noqa: PLR0913
    image_jy_per_beam: npt.ArrayLike,
    background_jy_per_beam: npt.ArrayLike,
    rms_jy_per_beam: npt.ArrayLike,
    header: fits.Header,
    *,
    beam: BeamShapePixels,
    review: PhaseFiveCorrectiveAReview,
) -> PublicFinderCorrectionContinuumProducts:
    """Build the fixture-only common-parent reconstructed candidate."""
    image = _aligned_public_plane(image_jy_per_beam, name="image")
    background = _aligned_public_plane(
        background_jy_per_beam,
        name="background",
        shape=image.shape,
    )
    rms = _aligned_public_plane(
        rms_jy_per_beam,
        name="RMS",
        shape=image.shape,
    )
    valid = np.isfinite(image) & np.isfinite(background) & np.isfinite(rms)
    if np.any(np.isfinite(image) != valid):
        raise ValueError(
            "public-finder correction mean/RMS validity differs from image"
        )
    products = evaluate_public_finder_correction_candidate_products(
        image,
        valid,
        background,
        rms,
        beam=beam,
        review=review,
    )
    catalogues = build_hebog_reconstructed_source_catalogues(
        image,
        background,
        valid,
        products.detection.component_labels,
        products.direct_component_labels,
        products.significant_multiscale_support,
        products.scale_detection_planes,
        header,
        beam_major_fwhm_pixels=beam.major_fwhm_pixels,
        beam_minor_fwhm_pixels=beam.minor_fwhm_pixels,
        measurement_aperture_radius_beams=(
            CONTINUUM_MEASUREMENT_APERTURE_RADIUS_BEAMS
        ),
        position_signal_jy_per_beam=products.position_signal_jy_per_beam,
    )
    valid.setflags(write=False)
    return PublicFinderCorrectionContinuumProducts(
        detection=products.detection,
        catalogue=catalogues.source_catalogue,
        valid_pixels=valid,
        component_catalogue=catalogues.component_catalogue,
        source_association=catalogues.association,
    )
