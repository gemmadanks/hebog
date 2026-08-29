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
                scale_order=1,
                nominal_scale_beam_fwhm=1.0,
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
        scale_order=1,
        component_labels=labels,
        detections=tuple(records),
    )


def _measure(
    labels: np.ndarray,
    image: np.ndarray,
    planes: tuple[ScaleDetectionPlane, ...],
    *,
    radius: float = 1.0,
):
    return build_hebog_reconstructed_source_catalogues(
        image,
        np.zeros_like(image),
        np.ones(image.shape, dtype=np.bool_),
        labels,
        planes,
        _header(image.shape),
        beam_major_fwhm_pixels=2.0,
        beam_minor_fwhm_pixels=1.0,
        measurement_aperture_radius_beams=radius,
        position_signal_jy_per_beam=image,
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
