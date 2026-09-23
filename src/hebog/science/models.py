# pyright: reportMissingTypeStubs=false
"""Phase-neutral records used by the installed scientific composition."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Self

import numpy as np
import numpy.typing as npt

from hebog.algorithms.component_measurement import (
    FitParentMeasurement,
    SupportFeatureGroups,
)
from hebog.algorithms.multiscale_association import ScaleDetectionRecords
from hebog.algorithms.reconciliation import DetectedIsland
from hebog.data_models.measurement_diagnostics import MeasurementDisposition
from hebog.data_models.source_association import SourceAssociationResult

_MINIMUM_DECLINATION_DEGREES = -90.0
_MAXIMUM_DECLINATION_DEGREES = 90.0
_FULL_CIRCLE_DEGREES = 360.0
_HALF_CIRCLE_DEGREES = 180.0


def _conversion_scale(
    unit: str,
    scales: dict[str, float],
    *,
    field_name: str,
) -> float:
    """Resolve one explicitly supported unit with a clear runtime error."""
    try:
        return scales[unit]
    except KeyError:
        supported = ", ".join(scales)
        raise ValueError(
            f"unsupported {field_name} {unit!r}; expected {supported}"
        ) from None


def _require_optional_positive(
    values: Sequence[float | None],
    *,
    field_name: str,
) -> None:
    """Require every available uncertainty to be finite and positive."""
    if any(
        value is not None and (not np.isfinite(value) or value <= 0)
        for value in values
    ):
        raise ValueError(f"{field_name} must be finite and positive")


@dataclass(frozen=True, slots=True)
class CatalogueEllipse:
    """One canonical catalogue ellipse and optional one-sigma errors."""

    major_fwhm_degrees: float
    minor_fwhm_degrees: float
    position_angle_degrees: float
    major_fwhm_error_degrees: float | None = None
    minor_fwhm_error_degrees: float | None = None
    position_angle_error_degrees: float | None = None

    def __post_init__(self) -> None:
        """Require a positive ordered ellipse modulo 180 degrees."""
        if (
            not np.isfinite(self.major_fwhm_degrees)
            or not np.isfinite(self.minor_fwhm_degrees)
            or self.major_fwhm_degrees <= 0
            or self.minor_fwhm_degrees <= 0
        ):
            raise ValueError(
                "catalogue ellipse axes must be finite and positive"
            )
        if self.minor_fwhm_degrees > self.major_fwhm_degrees:
            raise ValueError("catalogue ellipse axes must be ordered")
        if not np.isfinite(self.position_angle_degrees):
            raise ValueError("catalogue position angle must be finite")
        object.__setattr__(
            self,
            "position_angle_degrees",
            self.position_angle_degrees % _HALF_CIRCLE_DEGREES,
        )
        _require_optional_positive(
            (
                self.major_fwhm_error_degrees,
                self.minor_fwhm_error_degrees,
                self.position_angle_error_degrees,
            ),
            field_name="catalogue ellipse errors",
        )


@dataclass(frozen=True, slots=True)
class CatalogueSource:
    """One internal source-catalogue row in canonical physical units."""

    identifier: str
    right_ascension_degrees: float
    declination_degrees: float
    peak_flux_jy_per_beam: float
    integrated_flux_jy: float
    right_ascension_error_degrees: float | None = None
    declination_error_degrees: float | None = None
    peak_flux_error_jy_per_beam: float | None = None
    integrated_flux_error_jy: float | None = None
    fitted_shape: CatalogueEllipse | None = None
    deconvolved_shape: CatalogueEllipse | None = None
    deconvolved_major_fwhm_degrees: float | None = None
    deconvolution_status: Literal[
        "resolved",
        "major-axis-only",
        "unresolved",
        "unavailable",
    ] = "unavailable"
    island_identifier: str | None = None
    component_count: int | None = None
    quality_flags: tuple[str, ...] = ()
    association_integrated_flux_jy: float | None = None

    def _validate_optional_metadata(self) -> None:
        """Validate optional errors, associations, and quality flags."""
        _require_optional_positive(
            (
                self.right_ascension_error_degrees,
                self.declination_error_degrees,
                self.peak_flux_error_jy_per_beam,
                self.integrated_flux_error_jy,
            ),
            field_name="source errors",
        )
        if self.island_identifier is not None and not self.island_identifier:
            raise ValueError("island identifier must not be empty")
        if self.component_count is not None and self.component_count <= 0:
            raise ValueError("component count must be positive")
        if self.quality_flags != tuple(sorted(set(self.quality_flags))) or any(
            not flag for flag in self.quality_flags
        ):
            raise ValueError("quality flags must be non-empty and canonical")

    def _validate_deconvolution(self) -> None:
        """Keep full, one-axis, unresolved, and unavailable states clear."""
        if self.deconvolution_status == "resolved":
            if (
                self.deconvolved_shape is None
                or self.deconvolved_major_fwhm_degrees is not None
            ):
                raise ValueError("resolved deconvolution requires a shape")
        elif self.deconvolution_status == "major-axis-only":
            major = self.deconvolved_major_fwhm_degrees
            if (
                self.deconvolved_shape is not None
                or major is None
                or not np.isfinite(major)
                or major <= 0
            ):
                raise ValueError(
                    "major-axis-only deconvolution requires one positive axis"
                )
            if "major-axis-only" not in self.quality_flags:
                raise ValueError(
                    "major-axis-only deconvolution requires its quality flag"
                )
        elif (
            self.deconvolved_shape is not None
            or self.deconvolved_major_fwhm_degrees is not None
        ):
            raise ValueError(
                "only identifiable deconvolution may contain an axis"
            )
        if (
            self.deconvolution_status == "unresolved"
            and "unresolved" not in self.quality_flags
        ):
            raise ValueError(
                "unresolved deconvolution requires its quality flag"
            )

    def __post_init__(self) -> None:
        """Validate identity, coordinates, and positive finite fluxes."""
        if not self.identifier:
            raise ValueError("source identifier must not be empty")
        numeric_values = (
            self.right_ascension_degrees,
            self.declination_degrees,
            self.peak_flux_jy_per_beam,
            self.integrated_flux_jy,
        )
        if not all(np.isfinite(value) for value in numeric_values):
            raise ValueError("source coordinates and fluxes must be finite")
        if not (
            _MINIMUM_DECLINATION_DEGREES
            <= self.declination_degrees
            <= _MAXIMUM_DECLINATION_DEGREES
        ):
            raise ValueError("declination must be within [-90, 90] degrees")
        if self.peak_flux_jy_per_beam <= 0 or self.integrated_flux_jy <= 0:
            raise ValueError("source fluxes must be positive")
        association_flux = self.association_integrated_flux_jy
        if association_flux is not None and (
            not np.isfinite(association_flux) or association_flux <= 0
        ):
            raise ValueError(
                "association integrated flux must be finite and positive"
            )
        self._validate_optional_metadata()
        self._validate_deconvolution()
        normalized_right_ascension = (
            self.right_ascension_degrees % _FULL_CIRCLE_DEGREES
        )
        object.__setattr__(
            self,
            "right_ascension_degrees",
            normalized_right_ascension,
        )

    @classmethod
    def from_units(  # noqa: PLR0913
        cls,
        *,
        identifier: str,
        right_ascension: float,
        declination: float,
        angle_unit: Literal["deg", "arcsec"],
        peak_flux_density: float,
        peak_flux_unit: Literal["Jy/beam", "mJy/beam"],
        integrated_flux_density: float,
        integrated_flux_unit: Literal["Jy", "mJy"],
    ) -> Self:
        """Convert supported angular and flux units into canonical units."""
        angle_scale = _conversion_scale(
            angle_unit,
            {"deg": 1.0, "arcsec": 1.0 / 3600.0},
            field_name="angle_unit",
        )
        peak_flux_scale = _conversion_scale(
            peak_flux_unit,
            {"Jy/beam": 1.0, "mJy/beam": 0.001},
            field_name="peak_flux_unit",
        )
        integrated_flux_scale = _conversion_scale(
            integrated_flux_unit,
            {"Jy": 1.0, "mJy": 0.001},
            field_name="integrated_flux_unit",
        )
        return cls(
            identifier=identifier,
            right_ascension_degrees=right_ascension * angle_scale,
            declination_degrees=declination * angle_scale,
            peak_flux_jy_per_beam=peak_flux_density * peak_flux_scale,
            integrated_flux_jy=(
                integrated_flux_density * integrated_flux_scale
            ),
        )


@dataclass(frozen=True, slots=True)
class ThresholdFilterResult:
    """Candidate-neutral seeds and connected lower-threshold support."""

    retained_mask: npt.NDArray[np.bool_]
    component_labels: npt.NDArray[np.int32]
    component_count: int


@dataclass(frozen=True, slots=True)
class TiledMultiscaleDetection:
    """Published tiled detection planes and reconciled per-scale features.

    These are the pass-B products of the tile-native composition described in
    ADR-008. Every plane covers the complete image and is read from the
    published generation; the per-scale island records were reduced on the
    tasks that held the filter responses, so the responses themselves are
    never stored.
    """

    detection_labels: npt.NDArray[np.int32]
    reconstruction_mask: npt.NDArray[np.bool_]
    position_signal_jy_per_beam: npt.NDArray[np.float64]
    significant_scale_masks: tuple[npt.NDArray[np.bool_], ...]
    detection_islands: tuple[DetectedIsland, ...]
    scale_islands_by_order: tuple[tuple[DetectedIsland, ...], ...]
    scale_nominal_beam_fwhms: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class TiledSupportTopology:
    """Published support reductions no bounded halo can supply.

    These are the pass-C reductions described in ADR-008: the globally
    reconciled components of the eligible support, which decide which seed a
    support pixel may attach to, and the support corroborated at an adjacent
    scale, which decides which recovered support stays published.
    """

    support_component_labels: npt.NDArray[np.int32]
    persistent_scale_support: npt.NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class TiledSupportLabels:
    """The support pass's final labels and mask, as published per core.

    Island admission has already been applied, so every label here is one the
    caller's pixel-count limits admit.
    """

    component_labels: npt.NDArray[np.int32]
    measurement_labels: npt.NDArray[np.int32]
    publication_labels: npt.NDArray[np.int32]
    retained_mask: npt.NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class TiledComponentTopology:
    """The object pass's component ownership, as published per core.

    Each parent was deblended inside the window that holds it, and the
    component numbering follows canonical parent order, so it does not move
    with tile geometry or completion order.
    """

    direct_component_labels: npt.NDArray[np.int32]
    measurement_component_labels: npt.NDArray[np.int32]
    deblended_parent_count: int
    deferred_parent_count: int


@dataclass(frozen=True, slots=True)
class TiledComponentFits:
    """The object pass's per-parent fits and the support they published.

    Each fit parent was measured inside the window holding its support and
    the reviewed context margin, and each connected feature of the combined
    support contributed its extended groups inside its own window, so these
    records carry no image-sized array except the support plane itself.
    """

    parents: tuple[FitParentMeasurement, ...]
    measurement_support: npt.NDArray[np.bool_]
    features: tuple[SupportFeatureGroups, ...]


@dataclass(frozen=True, slots=True)
class ContinuumCandidateProducts:
    """Detection, ownership, and multiscale measurement products."""

    detection: ThresholdFilterResult
    direct_component_labels: npt.NDArray[np.int32]
    measurement_component_labels: npt.NDArray[np.int32]
    position_signal_jy_per_beam: npt.NDArray[np.float64]
    scale_detections: tuple[ScaleDetectionRecords, ...]


@dataclass(frozen=True, slots=True)
class ContinuumProducts:
    """Binding associated sources and immutable component diagnostics."""

    detection: ThresholdFilterResult
    measurement_component_labels: npt.NDArray[np.int32]
    catalogue: tuple[CatalogueSource, ...]
    component_catalogue: tuple[CatalogueSource, ...]
    source_association: SourceAssociationResult
    deblended_parent_count: int = 0
    deferred_deblend_parent_count: int = 0
    measurement_dispositions: tuple[MeasurementDisposition, ...] = ()
