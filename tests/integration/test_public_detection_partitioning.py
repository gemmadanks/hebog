# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownVariableType=false
"""One-tile/many-tile agreement for the public tiled passes."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import numpy as np
import numpy.typing as npt
import pytest
from astropy.io import fits
from scipy.ndimage import label

from hebog.algorithms.extended_measurement import (
    assign_seeded_multiscale_support,
    refine_multiscale_segment_labels,
    refine_persistent_publication_labels,
)
from hebog.algorithms.multiscale import BeamShapePixels
from hebog.algorithms.multiscale_association import (
    build_scale_detection_plane_from_islands,
    persistent_adjacent_scale_support,
)
from hebog.config import SourceFinderConfig
from hebog.science.profile import (
    configured_science_profile,
    load_continuum_science_profile,
)
from hebog.validation.tiled_detection import (
    PublishedContinuumInputs,
    publish_continuum_inputs,
)

pytestmark = pytest.mark.integration

_ROOT = Path(__file__).parents[2]
_BEAM = BeamShapePixels(2.0, 1.6, 0.0)
_TOLERANCE = 2e-13
_MINIMUM_ISLAND_PIXELS = 7


def _image() -> npt.NDArray[np.float64]:
    """Return sources on every edge, corner and interior tile boundary."""
    shape = (200, 240)
    yy, xx = np.mgrid[: shape[0], : shape[1]]
    centres = (
        (0, 0),
        (0, 120),
        (0, 239),
        (100, 0),
        (199, 0),
        (199, 120),
        (199, 239),
        (60, 60),
        (80, 80),
        (120, 180),
        (100, 119),
        (100, 122),
    )
    image = np.zeros(shape, dtype=np.float64)
    for centre_y, centre_x in centres:
        image += 12.0 * np.exp(
            -((yy - centre_y) ** 2 + (xx - centre_x) ** 2) / 2.0
        )
    return image + 6.0 * np.exp(
        -((yy - 150) ** 2 / 200.0 + (xx - 60) ** 2 / 400.0)
    )


def _header(shape: tuple[int, int]) -> fits.Header:
    """Return one valid one-arcsecond celestial fixture header."""
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
    header["BMAJ"] = _BEAM.major_fwhm_pixels / 3600.0
    header["BMIN"] = _BEAM.minor_fwhm_pixels / 3600.0
    header["BPA"] = 0.0
    return header


def _retain(
    labels: npt.NDArray[np.int32],
    accepted: npt.NDArray[np.int32],
) -> npt.NDArray[np.int32]:
    """Apply the caller's island admission the way the published planes do."""
    return np.where(np.isin(labels, accepted), labels, 0).astype(
        np.int32,
        copy=False,
    )


def _detect(
    image: npt.NDArray[np.float64],
    work_directory: Path,
    *,
    tile_core_pixels: int,
) -> PublishedContinuumInputs:
    """Run the public detection pass over one analytic tile geometry."""
    config = SourceFinderConfig(5.0, 3.0, _MINIMUM_ISLAND_PIXELS)
    review = load_continuum_science_profile(
        (
            _ROOT / "src/hebog/resources/reviewed_continuum_profile.json"
        ).read_bytes()
    )
    return publish_continuum_inputs(
        image,
        np.ones(image.shape, dtype=np.bool_),
        np.zeros(image.shape, dtype=np.float64),
        np.ones(image.shape, dtype=np.float64),
        beam=_BEAM,
        review=configured_science_profile(review, config),
        work_directory=work_directory,
        header=_header(image.shape),
        config=config,
        tile_core_pixels=tile_core_pixels,
        support_tile_core_pixels=tile_core_pixels,
    )


@pytest.mark.parametrize("tile_core_pixels", [60, 80, 120])
def test_published_passes_are_one_tile_many_tile_equal(
    tmp_path: Path,
    tile_core_pixels: int,
) -> None:
    """Tile geometry decides which task runs, never the published science."""
    image = _image()
    one = _detect(image, tmp_path / "one", tile_core_pixels=4096)

    many = _detect(image, tmp_path / "many", tile_core_pixels=tile_core_pixels)

    np.testing.assert_array_equal(
        many.multiscale.detection_labels,
        one.multiscale.detection_labels,
    )
    np.testing.assert_array_equal(
        many.multiscale.reconstruction_mask,
        one.multiscale.reconstruction_mask,
    )
    for many_mask, one_mask in zip(
        many.multiscale.significant_scale_masks,
        one.multiscale.significant_scale_masks,
        strict=True,
    ):
        np.testing.assert_array_equal(many_mask, one_mask)
    assert (
        many.multiscale.scale_islands_by_order
        == one.multiscale.scale_islands_by_order
    )
    assert (
        many.multiscale.scale_nominal_beam_fwhms
        == one.multiscale.scale_nominal_beam_fwhms
    )
    np.testing.assert_allclose(
        many.multiscale.position_signal_jy_per_beam,
        one.multiscale.position_signal_jy_per_beam,
        rtol=_TOLERANCE,
        atol=_TOLERANCE,
    )
    np.testing.assert_array_equal(
        many.support.support_component_labels,
        one.support.support_component_labels,
    )
    np.testing.assert_array_equal(
        many.support.persistent_scale_support,
        one.support.persistent_scale_support,
    )
    for many_labels, one_labels in (
        (many.labels.component_labels, one.labels.component_labels),
        (many.labels.measurement_labels, one.labels.measurement_labels),
        (many.labels.publication_labels, one.labels.publication_labels),
        (many.labels.retained_mask, one.labels.retained_mask),
    ):
        np.testing.assert_array_equal(many_labels, one_labels)


def test_published_passes_cover_labelled_edge_and_corner_sources(
    tmp_path: Path,
) -> None:
    """The invariance above is not vacuous: the cases carry real support."""
    published = _detect(_image(), tmp_path / "one", tile_core_pixels=4096)

    labels = published.multiscale.detection_labels
    assert labels[0, 0] > 0
    assert labels[0, -1] > 0
    assert labels[-1, 0] > 0
    assert labels[-1, -1] > 0
    assert labels[60, 60] > 0
    assert labels[100, 119] == labels[100, 122]
    assert int(labels.max()) >= 8
    assert np.any(published.multiscale.reconstruction_mask)
    assert all(
        islands for islands in published.multiscale.scale_islands_by_order[:2]
    )
    components = published.support.support_component_labels
    assert int(components.max()) > 1
    np.testing.assert_array_equal(
        components > 0,
        (labels > 0) | published.multiscale.reconstruction_mask,
    )
    assert np.any(published.support.persistent_scale_support)
    publication = published.labels.publication_labels
    np.testing.assert_array_equal(
        published.labels.retained_mask,
        publication > 0,
    )
    assert int(publication.max()) > 0
    measurement = published.labels.measurement_labels
    component = published.labels.component_labels
    published_pixels = publication > 0
    owned_pixels = component > 0
    np.testing.assert_array_equal(
        measurement[published_pixels],
        publication[published_pixels],
    )
    np.testing.assert_array_equal(
        measurement[owned_pixels],
        component[owned_pixels],
    )
    assert np.count_nonzero(measurement) >= np.count_nonzero(component)


def test_published_support_matches_the_whole_plane_reduction(
    tmp_path: Path,
) -> None:
    """The tiled reductions reproduce the whole-plane kernels exactly."""
    published = _detect(_image(), tmp_path / "one", tile_core_pixels=4096)
    multiscale = published.multiscale

    expected_components, _ = cast(
        tuple[npt.NDArray[np.int32], int],
        label(
            (multiscale.detection_labels > 0) | multiscale.reconstruction_mask,
            structure=np.ones((3, 3), dtype=np.int8),
        ),
    )
    expected_persistent = persistent_adjacent_scale_support(
        tuple(
            build_scale_detection_plane_from_islands(
                scale_mask,
                islands,
                scale_order=scale_order,
                nominal_scale_beam_fwhm=nominal,
            )
            for scale_order, (scale_mask, islands, nominal) in enumerate(
                zip(
                    multiscale.significant_scale_masks,
                    multiscale.scale_islands_by_order,
                    multiscale.scale_nominal_beam_fwhms,
                    strict=True,
                ),
                start=1,
            )
        )
    )

    np.testing.assert_array_equal(
        published.support.support_component_labels,
        expected_components,
    )
    np.testing.assert_array_equal(
        published.support.persistent_scale_support,
        expected_persistent,
    )


def test_published_labels_match_the_whole_plane_support_chain(
    tmp_path: Path,
) -> None:
    """The tiled support rounds reproduce the whole-plane kernels exactly."""
    image = _image()
    published = _detect(image, tmp_path / "one", tile_core_pixels=4096)
    multiscale = published.multiscale
    valid = np.ones(image.shape, dtype=np.bool_)
    direct_snr = np.divide(image, np.ones(image.shape, dtype=np.float64))
    review = load_continuum_science_profile(
        (
            _ROOT / "src/hebog/resources/reviewed_continuum_profile.json"
        ).read_bytes()
    )
    island_sigma = configured_science_profile(
        review,
        SourceFinderConfig(5.0, 3.0, _MINIMUM_ISLAND_PIXELS),
    ).matrix.island_sigma

    measurement = assign_seeded_multiscale_support(
        multiscale.detection_labels,
        multiscale.reconstruction_mask,
        valid,
        beam_major_fwhm_pixels=_BEAM.major_fwhm_pixels,
    )
    direct_publication = refine_multiscale_segment_labels(
        multiscale.detection_labels,
        direct_snr,
        multiscale.reconstruction_mask,
        beam_major_fwhm_pixels=_BEAM.major_fwhm_pixels,
        recovered_minimum_snr=island_sigma,
    )
    publication = np.where(
        (direct_publication > 0) & (measurement > 0),
        measurement,
        0,
    ).astype(np.int32, copy=False)
    expected = refine_persistent_publication_labels(
        measurement,
        publication,
        direct_snr,
        published.support.persistent_scale_support,
    )
    accepted = np.asarray(
        [
            island.global_label
            for island in multiscale.detection_islands
            if island.pixel_count >= _MINIMUM_ISLAND_PIXELS
        ],
        dtype=np.int32,
    )

    assert accepted.size < len(multiscale.detection_islands)
    np.testing.assert_array_equal(
        published.labels.publication_labels,
        _retain(expected, accepted),
    )
    np.testing.assert_array_equal(
        published.labels.measurement_labels,
        _retain(measurement, accepted),
    )
    np.testing.assert_array_equal(
        published.labels.component_labels,
        _retain(multiscale.detection_labels, accepted),
    )
