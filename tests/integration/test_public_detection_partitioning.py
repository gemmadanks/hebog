# pyright: reportMissingTypeStubs=false
"""One-tile/many-tile agreement for the public tiled detection pass."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest

from hebog.algorithms.multiscale import BeamShapePixels
from hebog.config import SourceFinderConfig
from hebog.science.models import TiledMultiscaleDetection
from hebog.science.profile import (
    configured_science_profile,
    load_continuum_science_profile,
)
from hebog.validation.tiled_detection import detect_multiscale_planes

pytestmark = pytest.mark.integration

_ROOT = Path(__file__).parents[2]
_BEAM = BeamShapePixels(2.0, 1.6, 0.0)
_TOLERANCE = 2e-13


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


def _detect(
    image: npt.NDArray[np.float64],
    work_directory: Path,
    *,
    tile_core_pixels: int,
) -> TiledMultiscaleDetection:
    """Run the public detection pass over one analytic tile geometry."""
    config = SourceFinderConfig(5.0, 3.0, 7)
    review = load_continuum_science_profile(
        (
            _ROOT / "src/hebog/resources/reviewed_continuum_profile.json"
        ).read_bytes()
    )
    return detect_multiscale_planes(
        image,
        np.ones(image.shape, dtype=np.bool_),
        np.zeros(image.shape, dtype=np.float64),
        np.ones(image.shape, dtype=np.float64),
        beam=_BEAM,
        review=configured_science_profile(review, config),
        work_directory=work_directory,
        tile_core_pixels=tile_core_pixels,
    )


@pytest.mark.parametrize("tile_core_pixels", [60, 80, 120])
def test_detection_pass_is_one_tile_many_tile_equal(
    tmp_path: Path,
    tile_core_pixels: int,
) -> None:
    """Tile geometry decides which task runs, never the published science."""
    image = _image()
    one = _detect(image, tmp_path / "one", tile_core_pixels=4096)

    many = _detect(image, tmp_path / "many", tile_core_pixels=tile_core_pixels)

    np.testing.assert_array_equal(
        many.detection_labels,
        one.detection_labels,
    )
    np.testing.assert_array_equal(
        many.reconstruction_mask,
        one.reconstruction_mask,
    )
    for many_mask, one_mask in zip(
        many.significant_scale_masks,
        one.significant_scale_masks,
        strict=True,
    ):
        np.testing.assert_array_equal(many_mask, one_mask)
    assert many.scale_islands_by_order == one.scale_islands_by_order
    assert many.scale_nominal_beam_fwhms == one.scale_nominal_beam_fwhms
    np.testing.assert_allclose(
        many.combined_snr,
        one.combined_snr,
        rtol=_TOLERANCE,
        atol=_TOLERANCE,
    )
    np.testing.assert_allclose(
        many.position_signal_jy_per_beam,
        one.position_signal_jy_per_beam,
        rtol=_TOLERANCE,
        atol=_TOLERANCE,
    )


def test_detection_pass_publishes_labelled_edge_and_corner_sources(
    tmp_path: Path,
) -> None:
    """The invariance above is not vacuous: the cases carry real support."""
    detection = _detect(_image(), tmp_path / "one", tile_core_pixels=4096)

    labels = detection.detection_labels
    assert labels[0, 0] > 0
    assert labels[0, -1] > 0
    assert labels[-1, 0] > 0
    assert labels[-1, -1] > 0
    assert labels[60, 60] > 0
    assert labels[100, 119] == labels[100, 122]
    assert int(labels.max()) >= 8
    assert np.any(detection.reconstruction_mask)
    assert all(islands for islands in detection.scale_islands_by_order[:2])
