# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Bounded one-tile serial kernels for Phase 5 multiscale science."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import accumulate, pairwise
from math import ceil, isfinite, sqrt
from typing import Literal, TypeVar, cast

import numpy as np
import numpy.typing as npt
from scipy.ndimage import convolve1d, label
from scipy.signal import fftconvolve

from hebog.config import ResidualMultiscaleDetectionConfig

FilterFamily = Literal[
    "beam-aware-matched-filter",
    "undecimated-wavelet",
    "residual-b3-atrous",
]

_IMAGE_DIMENSIONS = 2
_FWHM_TO_SIGMA = 1.0 / (2.0 * sqrt(2.0 * np.log(2.0)))
_WAVELET_WIDTH_RATIO = sqrt(2.0)
_MINIMUM_TRUNCATION_SIGMA = 3.0
_MAXIMUM_TRUNCATION_SIGMA = 8.0
_MINIMUM_ATROUS_SCALE_COUNT = 2
_GAUSSIAN_BEAM_AREA_FACTOR = 1.1331
_ArrayScalar = TypeVar("_ArrayScalar", bound=np.generic)


@dataclass(frozen=True, slots=True)
class BeamShapePixels:
    """Elliptical restoring beam or noise correlation in pixel units."""

    major_fwhm_pixels: float
    minor_fwhm_pixels: float
    position_angle_degrees: float

    def __post_init__(self) -> None:
        """Require finite, positive, ordered beam axes."""
        values = (
            self.major_fwhm_pixels,
            self.minor_fwhm_pixels,
            self.position_angle_degrees,
        )
        if not all(isfinite(value) for value in values):
            raise ValueError("beam shape values must be finite")
        if self.major_fwhm_pixels <= 0 or self.minor_fwhm_pixels <= 0:
            raise ValueError("beam shape axes must be positive")
        if self.minor_fwhm_pixels > self.major_fwhm_pixels:
            raise ValueError("beam shape minor axis cannot exceed major")


@dataclass(frozen=True, slots=True)
class ScaleSmoothingKernel:
    """One shared normalized Gaussian smoothing component."""

    width_beams: float
    halo_pixels: int
    values: npt.NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class ScaleFilter:
    """One calibrated scale response built from shared smoothing kernels."""

    scale_order: int
    nominal_scale_beam_fwhm: float
    family: FilterFamily
    components: tuple[tuple[float, ScaleSmoothingKernel], ...]
    response_calibration: float
    response_kernel: npt.NDArray[np.float64]
    halo_pixels: int
    independent_noise_gain: float
    correlated_noise_gain: float
    truncation_fraction: float


@dataclass(frozen=True, slots=True)
class ScaleFilterBank:
    """Canonical filter plans and bounded structural costs for one family."""

    family: FilterFamily
    beam: BeamShapePixels
    noise_correlation: BeamShapePixels | None
    truncation_sigma: float
    filters: tuple[ScaleFilter, ...]
    dtype: Literal["float64"] = "float64"

    @property
    def maximum_halo_pixels(self) -> int:
        """Return the widest read-only halo required by any scale."""
        return max(item.halo_pixels for item in self.filters)

    @property
    def convolution_count_per_evaluation(self) -> int:
        """Return convolutions after shared wavelet smoothing reuse."""
        unique_smoothing_components = {
            component.width_beams
            for item in self.filters
            for _, component in item.components
        }
        return 2 * len(unique_smoothing_components) + len(self.filters)

    @property
    def temporary_plane_count(self) -> int:
        """Return the maximum simultaneous full-size temporary planes."""
        return 7 if self.family == "beam-aware-matched-filter" else 9


@dataclass(frozen=True, slots=True)
class ScaleFilterResponse:
    """One immutable physical response, local noise, and validity plane."""

    scale_order: int
    nominal_scale_beam_fwhm: float
    response_jy_per_beam: npt.NDArray[np.float64]
    effective_rms_jy_per_beam: npt.NDArray[np.float64]
    valid_support_fraction: npt.NDArray[np.float64]
    scientifically_valid: npt.NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class ScaleFilterBankResult:
    """Complete one-tile serial response with explicit bounded costs."""

    family: FilterFamily
    responses: tuple[ScaleFilterResponse, ...]
    convolution_count: int
    temporary_plane_count: int
    maximum_workspace_bytes: int


@dataclass(frozen=True, slots=True)
class PreparedScaleInputs:
    """Validated physical residual and reused Phase 2 RMS products."""

    residual_jy_per_beam: npt.NDArray[np.float64]
    rms_jy_per_beam: npt.NDArray[np.float64]
    scientifically_valid: npt.NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class ResidualAtrousScale:
    """One cumulative B3-spline scale and calibrated coefficient noise."""

    scale_order: int
    dilation_pixels: int
    cumulative_halo_pixels: int
    response_kernel: npt.NDArray[np.float64]
    independent_noise_gain: float
    correlated_noise_gain: float


@dataclass(frozen=True, slots=True)
class ResidualAtrousPlan:
    """Bounded three-scale residual B3-spline à trous construction."""

    beam: BeamShapePixels
    noise_correlation: BeamShapePixels | None
    base_kernel: npt.NDArray[np.float64]
    scales: tuple[ResidualAtrousScale, ...]
    dtype: Literal["float64"] = "float64"

    @property
    def scale_dilations_pixels(self) -> tuple[int, ...]:
        """Return the frozen dyadic holes between B3 coefficients."""
        return tuple(item.dilation_pixels for item in self.scales)

    @property
    def scale_halo_pixels(self) -> tuple[int, ...]:
        """Return cumulative finite halos at each adjacent smoothing."""
        return tuple(item.cumulative_halo_pixels for item in self.scales)

    @property
    def maximum_halo_pixels(self) -> int:
        """Return the widest cumulative halo required by the transform."""
        return self.scales[-1].cumulative_halo_pixels

    @property
    def convolution_count_per_evaluation(self) -> int:
        """Count sparse one-dimensional signal and support convolutions."""
        return 4 * len(self.scales)

    @property
    def temporary_plane_count(self) -> int:
        """Return the reviewed peak full-size scratch-plane count."""
        return 7


@dataclass(frozen=True, slots=True)
class ResidualAtrousResult:
    """One-tile corrective transform with transient scale provenance."""

    family: Literal["residual-b3-atrous"]
    responses: tuple[ScaleFilterResponse, ...]
    reconstructed_signal_jy_per_beam: npt.NDArray[np.float64]
    coarse_smoothing_jy_per_beam: npt.NDArray[np.float64]
    scientifically_valid: npt.NDArray[np.bool_]
    convolution_count: int
    temporary_plane_count: int
    maximum_workspace_bytes: int


@dataclass(frozen=True, slots=True)
class SignificantAtrousReconstruction:
    """Adjacent-scale positive signal and auditable scale detections."""

    signal_jy_per_beam: npt.NDArray[np.float64]
    support_mask: npt.NDArray[np.bool_]
    significant_scale_masks: tuple[npt.NDArray[np.bool_], ...]


@dataclass(frozen=True, slots=True)
class ResidualMultiscaleIslandDetection:
    """Seeded original-residual islands under the promoted scale policy."""

    combined_snr: npt.NDArray[np.float64]
    retained_mask: npt.NDArray[np.bool_]
    component_labels: npt.NDArray[np.int32]
    component_count: int
    minimum_island_pixels: int
    reconstruction: SignificantAtrousReconstruction


def _read_only(
    array: npt.NDArray[_ArrayScalar],
) -> npt.NDArray[_ArrayScalar]:
    """Prevent accidental mutation of governed kernels and results."""
    array.setflags(write=False)
    return array


def _elliptical_gaussian(
    beam: BeamShapePixels,
    *,
    width_beams: float,
    halo_pixels: int,
) -> npt.NDArray[np.float64]:
    """Return one centred beam-aligned Gaussian on a square support."""
    offsets = np.arange(-halo_pixels, halo_pixels + 1, dtype=np.float64)
    y_grid, x_grid = np.meshgrid(offsets, offsets, indexing="ij")
    angle = np.deg2rad(beam.position_angle_degrees)
    cosine = np.cos(angle)
    sine = np.sin(angle)
    major_offset = cosine * x_grid + sine * y_grid
    minor_offset = -sine * x_grid + cosine * y_grid
    major_sigma = beam.major_fwhm_pixels * width_beams * _FWHM_TO_SIGMA
    minor_sigma = beam.minor_fwhm_pixels * width_beams * _FWHM_TO_SIGMA
    return np.asarray(
        np.exp(
            -0.5
            * (
                np.square(major_offset / major_sigma)
                + np.square(minor_offset / minor_sigma)
            )
        ),
        dtype=np.float64,
    )


def _build_smoothing_kernel(
    beam: BeamShapePixels,
    *,
    width_beams: float,
    truncation_sigma: float,
) -> ScaleSmoothingKernel:
    """Build one L1-normalized smoothing component."""
    halo_pixels = scale_smoothing_halo_pixels(
        beam,
        width_beams=width_beams,
        truncation_sigma=truncation_sigma,
    )
    values = _elliptical_gaussian(
        beam,
        width_beams=width_beams,
        halo_pixels=halo_pixels,
    )
    values /= np.sum(values, dtype=np.float64)
    return ScaleSmoothingKernel(
        width_beams=width_beams,
        halo_pixels=halo_pixels,
        values=_read_only(values),
    )


def scale_smoothing_halo_pixels(
    beam: BeamShapePixels,
    *,
    width_beams: float,
    truncation_sigma: float,
) -> int:
    """Return one Gaussian filter radius without allocating its kernel."""
    if not isfinite(width_beams) or width_beams <= 0:
        raise ValueError("scale width must be finite and positive")
    if not isfinite(truncation_sigma) or not (
        _MINIMUM_TRUNCATION_SIGMA
        <= truncation_sigma
        <= _MAXIMUM_TRUNCATION_SIGMA
    ):
        raise ValueError("truncation_sigma must be finite and within [3, 8]")
    major_sigma = beam.major_fwhm_pixels * width_beams * _FWHM_TO_SIGMA
    return ceil(truncation_sigma * major_sigma)


def residual_atrous_scale_halos_pixels() -> tuple[int, ...]:
    """Return cumulative radii for the frozen dyadic B3 sequence."""
    return tuple(accumulate(2 * dilation for dilation in (1, 2, 4)))


def _centre_pad(
    values: npt.NDArray[np.float64],
    *,
    halo_pixels: int,
) -> npt.NDArray[np.float64]:
    """Centre one odd square kernel on a wider odd square support."""
    result = np.zeros(
        (2 * halo_pixels + 1, 2 * halo_pixels + 1),
        dtype=np.float64,
    )
    source_halo = values.shape[0] // 2
    start = halo_pixels - source_halo
    stop = start + values.shape[0]
    result[start:stop, start:stop] = values
    return result


def _unit_integrated_flux_template(
    beam: BeamShapePixels,
    *,
    nominal_scale_beam_fwhm: float,
    halo_pixels: int,
) -> npt.NDArray[np.float64]:
    """Return the nominal Gaussian brightness for one integrated-flux unit."""
    template = _elliptical_gaussian(
        beam,
        width_beams=nominal_scale_beam_fwhm,
        halo_pixels=halo_pixels,
    )
    template /= nominal_scale_beam_fwhm**2
    return template


def _noise_gain(
    response_kernel: npt.NDArray[np.float64],
    correlation: BeamShapePixels | None,
) -> float:
    """Return output standard deviation for unit-variance stationary noise."""
    if correlation is None:
        return float(np.sqrt(np.sum(np.square(response_kernel))))
    autocorrelation = fftconvolve(
        response_kernel,
        response_kernel[::-1, ::-1],
        mode="full",
    )
    halo_y = autocorrelation.shape[0] // 2
    halo_x = autocorrelation.shape[1] // 2
    y_offsets = np.arange(-halo_y, halo_y + 1, dtype=np.float64)
    x_offsets = np.arange(-halo_x, halo_x + 1, dtype=np.float64)
    y_grid, x_grid = np.meshgrid(y_offsets, x_offsets, indexing="ij")
    angle = np.deg2rad(correlation.position_angle_degrees)
    cosine = np.cos(angle)
    sine = np.sin(angle)
    major_offset = cosine * x_grid + sine * y_grid
    minor_offset = -sine * x_grid + cosine * y_grid
    major_sigma = correlation.major_fwhm_pixels * _FWHM_TO_SIGMA
    minor_sigma = correlation.minor_fwhm_pixels * _FWHM_TO_SIGMA
    covariance = np.exp(
        -0.5
        * (
            np.square(major_offset / major_sigma)
            + np.square(minor_offset / minor_sigma)
        )
    )
    variance = float(np.sum(autocorrelation * covariance, dtype=np.float64))
    return sqrt(max(variance, 0.0))


def _dilated_b3_kernel(
    base_kernel: npt.NDArray[np.float64], dilation_pixels: int
) -> npt.NDArray[np.float64]:
    """Insert dyadic holes into the standard five-tap B3 kernel."""
    kernel = np.zeros(4 * dilation_pixels + 1, dtype=np.float64)
    kernel[::dilation_pixels] = base_kernel
    return kernel


def build_residual_atrous_plan(
    beam: BeamShapePixels,
    *,
    noise_correlation: BeamShapePixels | None = None,
) -> ResidualAtrousPlan:
    """Build the frozen three-scale separable B3-spline à trous plan."""
    base_kernel = np.asarray([1.0, 4.0, 6.0, 4.0, 1.0], dtype=np.float64)
    base_kernel /= 16.0
    previous_smoothing = np.ones((1, 1), dtype=np.float64)
    scales: list[ResidualAtrousScale] = []
    for scale_order, (dilation_pixels, cumulative_halo) in enumerate(
        zip(
            (1, 2, 4),
            residual_atrous_scale_halos_pixels(),
            strict=True,
        ),
        start=1,
    ):
        sparse = _dilated_b3_kernel(base_kernel, dilation_pixels)
        stage_kernel = np.outer(sparse, sparse)
        current_smoothing = fftconvolve(
            previous_smoothing,
            stage_kernel,
            mode="full",
        )
        previous_padded = _centre_pad(
            previous_smoothing,
            halo_pixels=cumulative_halo,
        )
        response_kernel = np.asarray(
            previous_padded - current_smoothing,
            dtype=np.float64,
        )
        scales.append(
            ResidualAtrousScale(
                scale_order=scale_order,
                dilation_pixels=dilation_pixels,
                cumulative_halo_pixels=cumulative_halo,
                response_kernel=_read_only(response_kernel),
                independent_noise_gain=_noise_gain(response_kernel, None),
                correlated_noise_gain=_noise_gain(
                    response_kernel, noise_correlation
                ),
            )
        )
        previous_smoothing = current_smoothing
    return ResidualAtrousPlan(
        beam=beam,
        noise_correlation=noise_correlation,
        base_kernel=_read_only(base_kernel),
        scales=tuple(scales),
    )


def _validate_scales(
    scales: tuple[tuple[int, float], ...],
) -> None:
    """Require canonical positive scale order and width."""
    if not scales:
        raise ValueError("scale filter bank requires at least one scale")
    orders = tuple(order for order, _ in scales)
    widths = tuple(width for _, width in scales)
    if orders != tuple(sorted(set(orders))) or min(orders) < 1:
        raise ValueError(
            "scale orders must be positive, unique, and canonical"
        )
    if not all(isfinite(width) and width > 0 for width in widths):
        raise ValueError("scale widths must be finite and positive")
    if widths != tuple(sorted(set(widths))):
        raise ValueError("scale widths must be increasing and unique")


def build_scale_filter_bank(
    beam: BeamShapePixels,
    *,
    family: FilterFamily,
    scales: tuple[tuple[int, float], ...],
    truncation_sigma: float = 4.0,
    noise_correlation: BeamShapePixels | None = None,
) -> ScaleFilterBank:
    """Build calibrated matched or undecimated-wavelet filter plans."""
    if family not in {
        "beam-aware-matched-filter",
        "undecimated-wavelet",
    }:
        raise ValueError("unsupported scale filter family")
    _validate_scales(scales)
    if not isfinite(truncation_sigma) or not (
        _MINIMUM_TRUNCATION_SIGMA
        <= truncation_sigma
        <= _MAXIMUM_TRUNCATION_SIGMA
    ):
        raise ValueError("truncation_sigma must be finite and within [3, 8]")

    smoothing_cache: dict[float, ScaleSmoothingKernel] = {}

    def smoothing(width_beams: float) -> ScaleSmoothingKernel:
        cache_key = round(width_beams, 12)
        cached = smoothing_cache.get(cache_key)
        if cached is None:
            cached = _build_smoothing_kernel(
                beam,
                width_beams=width_beams,
                truncation_sigma=truncation_sigma,
            )
            smoothing_cache[cache_key] = cached
        return cached

    filters: list[ScaleFilter] = []
    for scale_order, nominal_width in scales:
        if family == "beam-aware-matched-filter":
            components = ((1.0, smoothing(nominal_width)),)
        else:
            components = (
                (1.0, smoothing(nominal_width / _WAVELET_WIDTH_RATIO)),
                (-1.0, smoothing(nominal_width * _WAVELET_WIDTH_RATIO)),
            )
        halo_pixels = max(item.halo_pixels for _, item in components)
        raw_response_kernel = np.zeros(
            (2 * halo_pixels + 1, 2 * halo_pixels + 1),
            dtype=np.float64,
        )
        for coefficient, component in components:
            raw_response_kernel += coefficient * _centre_pad(
                component.values,
                halo_pixels=halo_pixels,
            )
        template = _unit_integrated_flux_template(
            beam,
            nominal_scale_beam_fwhm=nominal_width,
            halo_pixels=halo_pixels,
        )
        unit_response = float(
            np.sum(raw_response_kernel * template, dtype=np.float64)
        )
        if not isfinite(unit_response) or unit_response <= 0:
            raise ValueError("scale filter has no positive nominal response")
        response_calibration = 1.0 / unit_response
        response_kernel = np.asarray(
            response_calibration * raw_response_kernel,
            dtype=np.float64,
        )
        independent_noise_gain = _noise_gain(response_kernel, None)
        correlated_noise_gain = _noise_gain(
            response_kernel,
            noise_correlation,
        )
        template_boundary = np.concatenate(
            (
                template[0, :],
                template[-1, :],
                template[:, 0],
                template[:, -1],
            )
        )
        relative_kernel_tail = float(
            np.max(np.abs(template_boundary))
            / template[halo_pixels, halo_pixels]
        )
        filters.append(
            ScaleFilter(
                scale_order=scale_order,
                nominal_scale_beam_fwhm=nominal_width,
                family=family,
                components=components,
                response_calibration=response_calibration,
                response_kernel=_read_only(response_kernel),
                halo_pixels=halo_pixels,
                independent_noise_gain=independent_noise_gain,
                correlated_noise_gain=correlated_noise_gain,
                truncation_fraction=relative_kernel_tail,
            )
        )
    return ScaleFilterBank(
        family=family,
        beam=beam,
        noise_correlation=noise_correlation,
        truncation_sigma=truncation_sigma,
        filters=tuple(filters),
    )


def _as_float_plane(
    values: npt.ArrayLike,
    *,
    name: str,
) -> npt.NDArray[np.float64]:
    """Convert one real two-dimensional scientific plane to float64."""
    array = np.asarray(values)
    if array.ndim != _IMAGE_DIMENSIONS:
        raise ValueError(f"{name} must be two-dimensional")
    if np.issubdtype(array.dtype, np.bool_) or not np.issubdtype(
        array.dtype,
        np.number,
    ):
        raise TypeError(f"{name} must contain real numeric values")
    if np.issubdtype(array.dtype, np.complexfloating):
        raise TypeError(f"{name} must contain real numeric values")
    return np.asarray(array, dtype=np.float64)


def prepare_scale_filter_inputs(
    image: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
    background: npt.ArrayLike,
    rms: npt.ArrayLike,
) -> PreparedScaleInputs:
    """Validate prepared Phase 2 products and form one physical residual."""
    image_array = _as_float_plane(image, name="image")
    background_array = _as_float_plane(background, name="background")
    rms_array = _as_float_plane(rms, name="rms")
    validity = np.asarray(valid_pixels)
    if validity.ndim != _IMAGE_DIMENSIONS:
        raise ValueError("valid_pixels must be two-dimensional")
    if not np.issubdtype(validity.dtype, np.bool_):
        raise TypeError("valid_pixels must be a boolean array")
    if not (
        image_array.shape
        == background_array.shape
        == rms_array.shape
        == validity.shape
    ):
        raise ValueError("scale-filter arrays must have the same shape")
    scientifically_valid = (
        np.asarray(validity, dtype=np.bool_)
        & np.isfinite(image_array)
        & np.isfinite(background_array)
        & np.isfinite(rms_array)
        & (rms_array > 0)
    )
    residual = np.zeros(image_array.shape, dtype=np.float64)
    np.subtract(
        image_array,
        background_array,
        out=residual,
        where=scientifically_valid,
    )
    usable_rms = np.zeros(image_array.shape, dtype=np.float64)
    np.copyto(usable_rms, rms_array, where=scientifically_valid)
    return PreparedScaleInputs(
        residual_jy_per_beam=_read_only(residual),
        rms_jy_per_beam=_read_only(usable_rms),
        scientifically_valid=_read_only(scientifically_valid),
    )


def _separable_sparse_smoothing(
    values: npt.NDArray[np.float64],
    base_kernel: npt.NDArray[np.float64],
    *,
    dilation_pixels: int,
) -> npt.NDArray[np.float64]:
    """Apply one sparse B3 stage without materializing a dense 2D kernel."""
    sparse_kernel = _dilated_b3_kernel(base_kernel, dilation_pixels)
    along_y = convolve1d(
        values,
        sparse_kernel,
        axis=0,
        mode="constant",
        cval=0.0,
    )
    return np.asarray(
        convolve1d(
            along_y,
            sparse_kernel,
            axis=1,
            mode="constant",
            cval=0.0,
        ),
        dtype=np.float64,
    )


def evaluate_residual_atrous(
    prepared_inputs: PreparedScaleInputs,
    plan: ResidualAtrousPlan,
    *,
    minimum_support_fraction: float,
    accepted_compact_model: npt.ArrayLike | None = None,
    accepted_compact_mask: npt.ArrayLike | None = None,
) -> ResidualAtrousResult:
    """Evaluate normalized adjacent B3 smoothings of a compact-clean residual.

    Accepted compact emission may be subtracted through a model or excluded
    through a mask. The returned coefficients are detection provenance; final
    masks and measurements must continue to use the original residual pixels.
    """
    if (
        not isfinite(minimum_support_fraction)
        or not 0 < minimum_support_fraction <= 1
    ):
        raise ValueError("minimum_support_fraction must be within (0, 1]")
    if (
        accepted_compact_model is not None
        and accepted_compact_mask is not None
    ):
        raise ValueError("compact emission must be subtracted or excluded")

    residual = np.array(
        prepared_inputs.residual_jy_per_beam,
        dtype=np.float64,
        copy=True,
    )
    input_validity = np.array(
        prepared_inputs.scientifically_valid,
        dtype=np.bool_,
        copy=True,
    )
    if accepted_compact_model is not None:
        compact_model = _as_float_plane(
            accepted_compact_model, name="accepted_compact_model"
        )
        if compact_model.shape != residual.shape:
            raise ValueError(
                "accepted compact model must match residual shape"
            )
        if not np.isfinite(compact_model[input_validity]).all():
            raise ValueError(
                "accepted compact model must be finite where valid"
            )
        np.subtract(
            residual,
            compact_model,
            out=residual,
            where=input_validity,
        )
    if accepted_compact_mask is not None:
        compact_mask = np.asarray(accepted_compact_mask)
        if compact_mask.shape != residual.shape:
            raise ValueError("accepted compact mask must match residual shape")
        if not np.issubdtype(compact_mask.dtype, np.bool_):
            raise TypeError("accepted compact mask must be boolean")
        input_validity &= ~compact_mask
        residual[~input_validity] = 0.0

    current_smoothing = residual
    current_support = np.asarray(input_validity, dtype=np.float64)
    responses: list[ScaleFilterResponse] = []
    for scale in plan.scales:
        next_support = _separable_sparse_smoothing(
            current_support,
            plan.base_kernel,
            dilation_pixels=scale.dilation_pixels,
        )
        numerator = _separable_sparse_smoothing(
            current_smoothing * current_support,
            plan.base_kernel,
            dilation_pixels=scale.dilation_pixels,
        )
        next_smoothing = np.zeros(residual.shape, dtype=np.float64)
        np.divide(
            numerator,
            next_support,
            out=next_smoothing,
            where=next_support > 0,
        )
        scale_validity = input_validity & (
            next_support >= minimum_support_fraction
        )
        coefficient = np.full(residual.shape, np.nan, dtype=np.float64)
        np.subtract(
            current_smoothing,
            next_smoothing,
            out=coefficient,
            where=scale_validity,
        )
        effective_rms = np.full(residual.shape, np.nan, dtype=np.float64)
        propagated_rms = np.zeros(residual.shape, dtype=np.float64)
        np.divide(
            prepared_inputs.rms_jy_per_beam * scale.correlated_noise_gain,
            next_support,
            out=propagated_rms,
            where=next_support > 0,
        )
        np.copyto(effective_rms, propagated_rms, where=scale_validity)
        responses.append(
            ScaleFilterResponse(
                scale_order=scale.scale_order,
                nominal_scale_beam_fwhm=float(2 ** (scale.scale_order - 1)),
                response_jy_per_beam=_read_only(coefficient),
                effective_rms_jy_per_beam=_read_only(effective_rms),
                valid_support_fraction=_read_only(
                    np.asarray(next_support, dtype=np.float64)
                ),
                scientifically_valid=_read_only(
                    np.asarray(scale_validity, dtype=np.bool_)
                ),
            )
        )
        current_smoothing = next_smoothing
        current_support = next_support

    final_validity = input_validity & (
        current_support >= minimum_support_fraction
    )
    reconstructed = np.full(residual.shape, np.nan, dtype=np.float64)
    np.subtract(
        residual,
        current_smoothing,
        out=reconstructed,
        where=final_validity,
    )
    coarse_smoothing = np.full(residual.shape, np.nan, dtype=np.float64)
    np.copyto(coarse_smoothing, current_smoothing, where=final_validity)
    plane_bytes = residual.size * np.dtype(np.float64).itemsize
    retained_plane_count = 4 * len(responses) + 3
    kernel_bytes = plan.base_kernel.nbytes + sum(
        item.response_kernel.nbytes for item in plan.scales
    )
    return ResidualAtrousResult(
        family="residual-b3-atrous",
        responses=tuple(responses),
        reconstructed_signal_jy_per_beam=_read_only(reconstructed),
        coarse_smoothing_jy_per_beam=_read_only(coarse_smoothing),
        scientifically_valid=_read_only(
            np.asarray(final_validity, dtype=np.bool_)
        ),
        convolution_count=plan.convolution_count_per_evaluation,
        temporary_plane_count=plan.temporary_plane_count,
        maximum_workspace_bytes=(
            (plan.temporary_plane_count + retained_plane_count) * plane_bytes
            + kernel_bytes
        ),
    )


def reconstruct_significant_atrous(
    result: ResidualAtrousResult,
    *,
    detection_sigma: float,
    island_sigma: float,
    minimum_support_fraction: float,
) -> SignificantAtrousReconstruction:
    """Reconstruct positive coefficients persistent at adjacent scales."""
    if not (isfinite(detection_sigma) and isfinite(island_sigma)):
        raise ValueError("à trous thresholds must be finite")
    if detection_sigma <= island_sigma or island_sigma <= 0:
        raise ValueError(
            "thresholds require detection_sigma > island_sigma > 0"
        )
    if (
        not isfinite(minimum_support_fraction)
        or not 0 < minimum_support_fraction <= 1
    ):
        raise ValueError("minimum support fraction must be within (0, 1]")
    if len(result.responses) < _MINIMUM_ATROUS_SCALE_COUNT:
        raise ValueError("à trous reconstruction requires adjacent scales")
    scale_orders = tuple(response.scale_order for response in result.responses)
    if scale_orders != tuple(range(1, len(result.responses) + 1)):
        raise ValueError(
            "à trous responses require canonical adjacent scale orders"
        )
    scale_snrs = calibrated_scale_snrs(
        result.responses,
        minimum_support_fraction=minimum_support_fraction,
    )
    shape = scale_snrs[0].shape
    significant = tuple(
        _read_only(np.asarray(item >= island_sigma, dtype=np.bool_))
        for item in scale_snrs
    )
    adjacent_support = np.logical_or.reduce(
        tuple(
            current & following for current, following in pairwise(significant)
        )
    )
    component_labels, _ = cast(
        tuple[npt.NDArray[np.int32], int],
        label(
            adjacent_support,
            structure=np.ones((3, 3), dtype=np.int8),
        ),
    )
    maximum_snr = np.maximum.reduce(scale_snrs)
    seed_labels = np.unique(component_labels[maximum_snr >= detection_sigma])
    seed_labels = seed_labels[seed_labels > 0]
    retained_support = np.isin(component_labels, seed_labels)
    reconstructed = np.zeros(shape, dtype=np.float64)
    for response, scale_significant in zip(
        result.responses, significant, strict=True
    ):
        add_support = retained_support & scale_significant
        np.add(
            reconstructed,
            response.response_jy_per_beam,
            out=reconstructed,
            where=add_support,
        )
    return SignificantAtrousReconstruction(
        signal_jy_per_beam=_read_only(reconstructed),
        support_mask=_read_only(np.asarray(retained_support, dtype=np.bool_)),
        significant_scale_masks=significant,
    )


def calibrated_scale_snrs(
    responses: tuple[ScaleFilterResponse, ...],
    *,
    minimum_support_fraction: float,
) -> tuple[npt.NDArray[np.float64], ...]:
    """Return immutable calibrated SNR planes for aligned scale responses."""
    if not responses:
        raise ValueError("scale responses must not be empty")
    if (
        not isfinite(minimum_support_fraction)
        or not 0 < minimum_support_fraction <= 1
    ):
        raise ValueError("minimum support fraction must be within (0, 1]")
    shape = responses[0].response_jy_per_beam.shape
    scale_snrs: list[npt.NDArray[np.float64]] = []
    for response in responses:
        arrays = (
            response.response_jy_per_beam,
            response.effective_rms_jy_per_beam,
            response.valid_support_fraction,
            response.scientifically_valid,
        )
        if any(array.shape != shape for array in arrays):
            raise ValueError("scale responses must have the same shape")
        scale_validity = (
            response.scientifically_valid
            & (response.valid_support_fraction >= minimum_support_fraction)
            & np.isfinite(response.response_jy_per_beam)
            & np.isfinite(response.effective_rms_jy_per_beam)
            & (response.effective_rms_jy_per_beam > 0)
        )
        scale_snr = np.full(shape, -np.inf, dtype=np.float64)
        np.divide(
            response.response_jy_per_beam,
            response.effective_rms_jy_per_beam,
            out=scale_snr,
            where=scale_validity,
        )
        scale_snrs.append(_read_only(scale_snr))
    return tuple(scale_snrs)


def _maximum_calibrated_scale_snr(
    shape: tuple[int, int],
    responses: tuple[ScaleFilterResponse, ...],
    *,
    minimum_support_fraction: float,
) -> npt.NDArray[np.float64]:
    """Combine scale evidence only where noise and support are available."""
    scale_snrs = calibrated_scale_snrs(
        responses,
        minimum_support_fraction=minimum_support_fraction,
    )
    if scale_snrs[0].shape != shape:
        raise ValueError("scale responses must match the residual shape")
    return np.maximum.reduce(scale_snrs)


def detect_residual_multiscale_islands(
    prepared_inputs: PreparedScaleInputs,
    matched_filter: ScaleFilterBankResult,
    atrous_result: ResidualAtrousResult,
    beam: BeamShapePixels,
    config: ResidualMultiscaleDetectionConfig,
) -> ResidualMultiscaleIslandDetection:
    """Seed and grow promoted islands on original residual pixels."""
    if matched_filter.family != "beam-aware-matched-filter":
        raise ValueError("multiscale seed aid must be the matched filter")
    if atrous_result.family != "residual-b3-atrous":
        raise ValueError("multiscale representation must be residual B3")
    shape = prepared_inputs.residual_jy_per_beam.shape
    if (
        prepared_inputs.rms_jy_per_beam.shape != shape
        or prepared_inputs.scientifically_valid.shape != shape
    ):
        raise ValueError("prepared multiscale inputs must have the same shape")
    reconstruction = reconstruct_significant_atrous(
        atrous_result,
        detection_sigma=config.detection_threshold_sigma,
        island_sigma=config.island_threshold_sigma,
        minimum_support_fraction=config.minimum_scale_support_fraction,
    )
    combined_snr = _maximum_calibrated_scale_snr(
        shape,
        matched_filter.responses,
        minimum_support_fraction=config.minimum_scale_support_fraction,
    )
    atrous_snr = _maximum_calibrated_scale_snr(
        shape,
        atrous_result.responses,
        minimum_support_fraction=config.minimum_scale_support_fraction,
    )
    atrous_snr[~reconstruction.support_mask] = -np.inf
    np.maximum(combined_snr, atrous_snr, out=combined_snr)

    direct_snr = np.full(shape, -np.inf, dtype=np.float64)
    direct_validity = (
        prepared_inputs.scientifically_valid
        & np.isfinite(prepared_inputs.residual_jy_per_beam)
        & np.isfinite(prepared_inputs.rms_jy_per_beam)
        & (prepared_inputs.rms_jy_per_beam > 0)
    )
    np.divide(
        prepared_inputs.residual_jy_per_beam,
        prepared_inputs.rms_jy_per_beam,
        out=direct_snr,
        where=direct_validity,
    )
    np.maximum(combined_snr, direct_snr, out=combined_snr)
    combined_snr[~direct_validity] = -np.inf

    original_support = direct_validity & (
        direct_snr >= config.island_threshold_sigma
    )
    raw_labels, _ = cast(
        tuple[npt.NDArray[np.int32], int],
        label(original_support, structure=np.ones((3, 3), dtype=np.int8)),
    )
    seed_labels = np.unique(
        raw_labels[combined_snr >= config.detection_threshold_sigma]
    )
    seed_labels = seed_labels[seed_labels > 0]
    retained = np.isin(raw_labels, seed_labels)

    minimum_island_pixels = minimum_residual_island_pixels(beam, config)
    label_count = int(np.max(raw_labels)) + 1
    retained_counts = np.bincount(raw_labels[retained], minlength=label_count)
    accepted = retained_counts >= minimum_island_pixels
    direct_maxima = np.full(label_count, -np.inf, dtype=np.float64)
    np.maximum.at(direct_maxima, raw_labels.ravel(), direct_snr.ravel())
    accepted |= direct_maxima >= config.detection_threshold_sigma
    accepted[0] = False
    accepted_labels = np.flatnonzero(accepted)
    retained = np.isin(raw_labels, accepted_labels)
    component_labels = np.where(retained, raw_labels, 0).astype(
        np.int32,
        copy=False,
    )
    return ResidualMultiscaleIslandDetection(
        combined_snr=_read_only(combined_snr),
        retained_mask=_read_only(np.asarray(retained, dtype=np.bool_)),
        component_labels=_read_only(component_labels),
        component_count=int(np.count_nonzero(np.unique(component_labels) > 0)),
        minimum_island_pixels=minimum_island_pixels,
        reconstruction=reconstruction,
    )


def minimum_residual_island_pixels(
    beam: BeamShapePixels,
    config: ResidualMultiscaleDetectionConfig,
) -> int:
    """Return the promoted one-beam residual-island area floor."""
    return max(
        1,
        ceil(
            config.minimum_island_area_beams
            * _GAUSSIAN_BEAM_AREA_FACTOR
            * beam.major_fwhm_pixels
            * beam.minor_fwhm_pixels
        ),
    )


def evaluate_scale_filter_bank(
    prepared_inputs: PreparedScaleInputs,
    filter_bank: ScaleFilterBank,
    *,
    minimum_support_fraction: float,
) -> ScaleFilterBankResult:
    """Evaluate every configured scale from already prepared Phase 2 planes."""
    if (
        not isfinite(minimum_support_fraction)
        or not 0 < minimum_support_fraction <= 1
    ):
        raise ValueError("minimum_support_fraction must be within (0, 1]")
    residual = prepared_inputs.residual_jy_per_beam
    usable_rms = prepared_inputs.rms_jy_per_beam
    input_validity = prepared_inputs.scientifically_valid
    valid_float = np.asarray(input_validity, dtype=np.float64)
    smoothing_cache: dict[
        float,
        tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]],
    ] = {}
    responses: list[ScaleFilterResponse] = []

    for scale_filter in filter_bank.filters:
        component_responses: list[npt.NDArray[np.float64]] = []
        component_supports: list[npt.NDArray[np.float64]] = []
        for _, component in scale_filter.components:
            cached = smoothing_cache.get(component.width_beams)
            if cached is None:
                numerator = fftconvolve(
                    residual,
                    component.values,
                    mode="same",
                )
                support = fftconvolve(
                    valid_float,
                    component.values,
                    mode="same",
                )
                smoothed = np.zeros(residual.shape, dtype=np.float64)
                np.divide(
                    numerator,
                    support,
                    out=smoothed,
                    where=support > 0,
                )
                cached = (
                    np.asarray(smoothed, dtype=np.float64),
                    np.asarray(support, dtype=np.float64),
                )
                smoothing_cache[component.width_beams] = cached
            component_responses.append(cached[0])
            component_supports.append(cached[1])

        raw_response = np.zeros(residual.shape, dtype=np.float64)
        for (coefficient, _), component_response in zip(
            scale_filter.components,
            component_responses,
            strict=True,
        ):
            raw_response += coefficient * component_response
        calibrated_response = scale_filter.response_calibration * raw_response
        support_fraction = np.minimum.reduce(component_supports)
        scientifically_valid = input_validity & (
            support_fraction >= minimum_support_fraction
        )

        response = np.full(residual.shape, np.nan, dtype=np.float64)
        np.copyto(
            response,
            calibrated_response,
            where=scientifically_valid,
        )
        variance = fftconvolve(
            np.square(usable_rms) * valid_float,
            np.square(scale_filter.response_kernel),
            mode="same",
        )
        np.maximum(variance, 0.0, out=variance)
        effective_rms = np.full(residual.shape, np.nan, dtype=np.float64)
        noise_ratio = (
            scale_filter.correlated_noise_gain
            / scale_filter.independent_noise_gain
        )
        propagated = np.zeros(residual.shape, dtype=np.float64)
        np.divide(
            np.sqrt(variance) * noise_ratio,
            support_fraction,
            out=propagated,
            where=support_fraction > 0,
        )
        np.copyto(
            effective_rms,
            propagated,
            where=scientifically_valid,
        )
        responses.append(
            ScaleFilterResponse(
                scale_order=scale_filter.scale_order,
                nominal_scale_beam_fwhm=(scale_filter.nominal_scale_beam_fwhm),
                response_jy_per_beam=_read_only(response),
                effective_rms_jy_per_beam=_read_only(effective_rms),
                valid_support_fraction=_read_only(
                    np.asarray(support_fraction, dtype=np.float64)
                ),
                scientifically_valid=_read_only(
                    np.asarray(scientifically_valid, dtype=np.bool_)
                ),
            )
        )

    plane_bytes = residual.size * np.dtype(np.float64).itemsize
    retained_plane_count = 4 * len(responses)
    kernel_bytes = sum(
        item.response_kernel.nbytes
        + sum(component.values.nbytes for _, component in item.components)
        for item in filter_bank.filters
    )
    return ScaleFilterBankResult(
        family=filter_bank.family,
        responses=tuple(responses),
        convolution_count=filter_bank.convolution_count_per_evaluation,
        temporary_plane_count=filter_bank.temporary_plane_count,
        maximum_workspace_bytes=(
            (filter_bank.temporary_plane_count + retained_plane_count)
            * plane_bytes
            + kernel_bytes
        ),
    )
