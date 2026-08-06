# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Readable one-tile serial oracle for Phase 5 scale-filter selection."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, isfinite, sqrt
from typing import Literal, TypeVar

import numpy as np
import numpy.typing as npt
from scipy.signal import fftconvolve

FilterFamily = Literal[
    "beam-aware-matched-filter",
    "undecimated-wavelet",
]

_IMAGE_DIMENSIONS = 2
_FWHM_TO_SIGMA = 1.0 / (2.0 * sqrt(2.0 * np.log(2.0)))
_WAVELET_WIDTH_RATIO = sqrt(2.0)
_MINIMUM_TRUNCATION_SIGMA = 3.0
_MAXIMUM_TRUNCATION_SIGMA = 8.0
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
    major_sigma = beam.major_fwhm_pixels * width_beams * _FWHM_TO_SIGMA
    halo_pixels = ceil(truncation_sigma * major_sigma)
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
