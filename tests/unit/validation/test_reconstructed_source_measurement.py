"""Analytic one-pass measurement contracts for reconstructed sources."""

from __future__ import annotations

from collections.abc import Sequence
from math import log, pi
from typing import cast

import numpy as np
import numpy.typing as npt
import pytest
from astropy.io import fits  # pyright: ignore[reportMissingTypeStubs]
from astropy.wcs import WCS  # pyright: ignore[reportMissingTypeStubs]

from hebog.algorithms.multiscale_association import ScaleDetectionPlane
from hebog.data_models.multiscale import ScaleDetection
from hebog.validation.products import (
    build_hebog_reconstructed_source_catalogues,
    build_hebog_segment_catalogue,
)


def _header(shape: tuple[int, int]) -> fits.Header:
    header = fits.Header()
    header["NAXIS"] = 2
    header["NAXIS1"] = shape[1]
    header["NAXIS2"] = shape[0]
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["CRPIX1"] = (shape[1] + 1) / 2
    header["CRPIX2"] = (shape[0] + 1) / 2
    header["CRVAL1"] = 10.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0
    header["BMAJ"] = 2.0 / 3600.0
    header["BMIN"] = 1.0 / 3600.0
    header["BPA"] = 0.0
    return header


def _plane(
    entries: Sequence[tuple[str, Sequence[tuple[int, int]]]],
    shape: tuple[int, int],
    *,
    scale_order: int = 1,
) -> ScaleDetectionPlane:
    labels = np.zeros(shape, dtype=np.int32)
    records: list[ScaleDetection] = []
    for label_value, (identifier, pixels) in enumerate(entries, start=1):
        ordered = tuple(sorted(pixels))
        for pixel in ordered:
            labels[pixel] = label_value
        ys = tuple(item[0] for item in ordered)
        xs = tuple(item[1] for item in ordered)
        records.append(
            ScaleDetection(
                detection_id=identifier,
                parent_island_id=None,
                scale_order=scale_order,
                nominal_scale_beam_fwhm=float(2 ** (scale_order - 1)),
                support_pixel_count=len(ordered),
                valid_support_fraction=1.0,
                bounds_yx=(min(ys), max(ys) + 1, min(xs), max(xs) + 1),
                canonical_pixel_yx=ordered[0],
                peak_response_jy_per_beam=1.0,
                peak_signal_to_noise=5.0,
                touches_image_edge=False,
            )
        )
    return ScaleDetectionPlane(
        scale_order=scale_order,
        component_labels=labels,
        detections=tuple(records),
    )


def _measure(  # noqa: PLR0913
    labels: np.ndarray,
    image: np.ndarray,
    planes: tuple[ScaleDetectionPlane, ...],
    *,
    background: np.ndarray | None = None,
    direct_labels: np.ndarray | None = None,
    radius: float = 1.0,
):
    resolved_background = (
        np.zeros_like(image) if background is None else background
    )
    return build_hebog_reconstructed_source_catalogues(
        image,
        resolved_background,
        np.ones(image.shape, dtype=np.bool_),
        labels,
        direct_labels if direct_labels is not None else labels,
        np.zeros(labels.shape, dtype=np.bool_),
        planes,
        _header(image.shape),
        beam_major_fwhm_pixels=2.0,
        beam_minor_fwhm_pixels=1.0,
        measurement_aperture_radius_beams=radius,
        position_signal_jy_per_beam=image,
    )


@pytest.mark.parametrize("extent_beams", (4, 8, 12))
@pytest.mark.parametrize("varying_background", (False, True))
def test_persistent_source_support_seeds_measurement_before_outer_guard(
    extent_beams: int,
    varying_background: bool,
) -> None:
    """Persistent source-owned emission contributes original pixels once."""
    shape = (41, 61)
    beam_major = 2
    start_x = 12
    stop_x = start_x + extent_beams * beam_major
    source_support = tuple((20, x) for x in range(start_x, stop_x))
    labels = np.zeros(shape, dtype=np.int32)
    labels[source_support[0]] = 1
    signal = np.zeros(shape, dtype=np.float64)
    signal[20, start_x:stop_x] = 1.0
    background = np.zeros(shape, dtype=np.float64)
    if varying_background:
        background[:] = np.linspace(-0.25, 0.25, shape[1])
    planes = (
        _plane((("scale-measurement-support-1", source_support),), shape),
        _plane(
            (("scale-measurement-support-2", source_support),),
            shape,
            scale_order=2,
        ),
    )

    products = _measure(
        labels,
        signal + background,
        planes,
        background=background,
        radius=1.5,
    )

    beam_area = 2.0 * pi / (8.0 * log(2.0)) * 2.0
    assert len(products.source_catalogue) == 1
    assert products.source_catalogue[0].integrated_flux_jy == pytest.approx(
        len(source_support) / beam_area
    )


def test_hierarchy_uses_direct_seeds_not_expanded_measurement_owners() -> None:
    """Recovered ownership cannot manufacture finest-feature ambiguity."""
    shape = (9, 15)
    direct = np.zeros(shape, dtype=np.int32)
    direct[4, 2] = 1
    direct[4, 11] = 2
    measurement = np.zeros(shape, dtype=np.int32)
    measurement[4, 2:7] = 1
    measurement[4, 11] = 2
    image = np.asarray(measurement > 0, dtype=np.float64)
    fine = _plane(
        (
            ("scale-direct-left", ((4, 2),)),
            ("scale-recovered-left", ((4, 5), (4, 6))),
            ("scale-direct-right", ((4, 11),)),
        ),
        shape,
    )
    convergence = _plane(
        (
            (
                "scale-direct-convergence",
                tuple((4, x) for x in range(2, 12)),
            ),
        ),
        shape,
        scale_order=2,
    )
    persistence = _plane(
        (
            (
                "scale-direct-persistence",
                tuple((4, x) for x in range(2, 12)),
            ),
        ),
        shape,
        scale_order=3,
    )

    products = _measure(
        measurement,
        image,
        (fine, convergence, persistence),
        direct_labels=direct,
    )

    assert len(products.source_catalogue) == 1
    assert products.source_catalogue[0].component_count == 2
    assert products.association.hierarchy_diagnostics is not None


def test_reconstructed_measurement_rejects_unknown_aperture_policy() -> None:
    """The internal policy seam fails closed instead of changing ownership."""
    labels = np.zeros((5, 5), dtype=np.int32)
    labels[2, 2] = 1
    image = np.asarray(labels > 0, dtype=np.float64)

    with pytest.raises(ValueError, match="aperture tie policy is unsupported"):
        build_hebog_segment_catalogue(
            image,
            np.zeros_like(image),
            np.ones(image.shape, dtype=np.bool_),
            labels,
            _header(image.shape),
            beam_major_fwhm_pixels=2.0,
            beam_minor_fwhm_pixels=1.0,
            aperture_tie_policy="unsupported",  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("direct", "message"),
    (
        (np.ones((2, 2), dtype=np.float64), "integer plane"),
        (np.zeros((2, 2), dtype=np.int32), "identities must match"),
        (np.asarray([[0, 1], [0, 0]], dtype=np.int32), "valid subset"),
    ),
)
def test_direct_hierarchy_labels_fail_closed(
    direct: np.ndarray,
    message: str,
) -> None:
    """Hierarchy identities must be exact subsets of measurement owners."""
    measurement = np.asarray([[1, 0], [0, 0]], dtype=np.int32)
    image = np.asarray(measurement > 0, dtype=np.float64)
    planes = (_plane((("scale-owner", ((0, 0),)),), measurement.shape),)

    with pytest.raises(ValueError, match=message):
        _measure(
            measurement,
            image,
            planes,
            direct_labels=direct,
        )


@pytest.mark.parametrize("offset", ((0, 0), (0, 5), (5, 5)))
def test_source_flux_and_centroid_are_measured_once_at_edges(
    offset: tuple[int, int],
) -> None:
    """A common source has exact flux and midpoint at centre and boundaries."""
    shape = (13, 13)
    first = (2 + offset[0], 2 + offset[1])
    second = (2 + offset[0], 4 + offset[1])
    labels = np.zeros(shape, dtype=np.int32)
    labels[first] = 9
    labels[second] = 2
    image = np.zeros(shape, dtype=np.float64)
    image[first] = 1.0
    image[second] = 3.0
    parent = tuple((first[0], x) for x in range(first[1], second[1] + 1))
    products = _measure(
        labels,
        image,
        (_plane((("scale-source-parent", parent),), shape),),
    )

    assert len(products.source_catalogue) == 1
    source = products.source_catalogue[0]
    beam_area = 2.0 * pi / (8.0 * log(2.0)) * 2.0
    assert source.integrated_flux_jy == pytest.approx(4.0 / beam_area)
    pixel = cast(
        npt.NDArray[np.float64],
        WCS(_header(shape), relax=True).celestial.all_world2pix(  # pyright: ignore[reportUnknownMemberType]
            [[source.right_ascension_degrees, source.declination_degrees]],
            0,
        ),
    )[0]
    assert tuple(pixel) == pytest.approx(
        ((first[1] + 3.0 * second[1]) / 4.0, float(first[0]))
    )
    assert source.component_count == 2
    assert "reconstructed-catalogue-source" in source.quality_flags


def test_source_apertures_are_disjoint_and_count_every_pixel_once() -> None:
    """Overlapping source apertures partition the complete valid plane."""
    shape = (9, 9)
    labels = np.zeros(shape, dtype=np.int32)
    labels[4, 2] = 1
    labels[4, 6] = 2
    image = np.ones(shape, dtype=np.float64)
    planes = (
        _plane(
            (
                ("scale-left-source", ((4, 2),)),
                ("scale-right-source", ((4, 6),)),
            ),
            shape,
        ),
    )

    products = _measure(labels, image, planes, radius=10.0)

    beam_area = 2.0 * pi / (8.0 * log(2.0)) * 2.0
    assert len(products.source_catalogue) == 2
    assert sum(
        item.integrated_flux_jy for item in products.source_catalogue
    ) == pytest.approx(image.size / beam_area)


def test_nonpositive_source_aperture_falls_back_once_per_source() -> None:
    """A negative expanded aperture uses one exact source-support fallback."""
    shape = (9, 9)
    labels = np.zeros(shape, dtype=np.int32)
    labels[4, 3] = 1
    labels[4, 5] = 2
    image = np.full(shape, -1.0, dtype=np.float64)
    image[4, 3] = 2.0
    image[4, 5] = 3.0
    parent = tuple((4, x) for x in range(3, 6))

    products = _measure(
        labels,
        image,
        (_plane((("scale-fallback-parent", parent),), shape),),
        radius=2.0,
    )

    source = products.source_catalogue[0]
    beam_area = 2.0 * pi / (8.0 * log(2.0)) * 2.0
    assert source.integrated_flux_jy == pytest.approx(5.0 / beam_area)
    assert "association-aperture-nonpositive" in source.quality_flags
    assert "exact-owner-positive-residual-flux" in source.quality_flags
