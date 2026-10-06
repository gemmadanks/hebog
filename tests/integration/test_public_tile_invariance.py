# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Public products do not change with the tile grid the passes run on.

The public passes after background and RMS run on 2,048-pixel cores, so the
15,402-pixel envelope is at most an eight-by-eight grid, with interior tiles
bounded on all four sides and forty-nine four-way corners. The envelope admits
every size below its limit, so a last row or column of tiles can be any width
up to a core, including narrower than a filter halo. These tests give a small
analytic image that grid by shrinking the cores, end its last row of tiles
inside the widest filter halo and its last column exactly on a core edge, the
two extremes a last tile can take, put support on every interior corner, seam
and image edge, and require the complete product set to equal the one-tile
run's.
"""

from __future__ import annotations

import inspect
import math
from collections.abc import Callable, Iterator
from functools import partial
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest
from astropy.io import fits
from conftest import IGNORE_RMS_KERNEL_WARNINGS, product_hashes

import hebog
from hebog import SourceFinderConfig, SourceFinderRequest, public_api
from hebog.algorithms.multiscale import BeamShapePixels
from hebog.algorithms.multiscale_tiles import scale_filter_halo_pixels
from hebog.data_models import (
    PartitionManifest,
    PublicSourceFindingDiagnostics,
    WideObjectCounts,
)
from hebog.executors import Executor, SerialExecutor
from hebog.io import read_diagnostics_product
from hebog.pipeline import SourceFinderResult

pytestmark = pytest.mark.integration

_CORE_PIXELS = 120
_TILES_PER_SIDE = 8
_GRID_TILES = _TILES_PER_SIDE**2
# The last row of tiles is 20 pixels high, inside the widest filter halo,
# and the last column a whole core wide.
_SHAPE_YX = (
    (_TILES_PER_SIDE - 1) * _CORE_PIXELS + 20,
    _TILES_PER_SIDE * _CORE_PIXELS,
)
_BEAM_FWHM_PIXELS = 4.0
_SEAMS = tuple(
    _CORE_PIXELS * index - 0.5 for index in range(1, _TILES_PER_SIDE)
)
_BOTTOM, _RIGHT = _SHAPE_YX[0] - 1.0, _SHAPE_YX[1] - 1.0
_COMPACT_CENTRES = (
    *((y, x) for y in _SEAMS for x in _SEAMS),
    (0.0, 0.0),
    (0.0, _RIGHT),
    (_BOTTOM, 0.0),
    (_BOTTOM, _RIGHT),
    (0.0, _SEAMS[0]),
    (_BOTTOM, _SEAMS[2]),
    (_SEAMS[1], 0.0),
    (_SEAMS[3], _RIGHT),
    (_BOTTOM, _SEAMS[6]),
    (_SEAMS[6], _RIGHT),
)
# Through the corners (479.5, 119.5), (599.5, 359.5), (719.5, 599.5) and
# (839.5, 839.5), ending in the narrow last row.
_LONG_FILAMENT = ((439.75, 40.0), (849.75, 860.0))
# Across three column seams, with a window the compact bound admits.
_SHORT_FILAMENT = ((60.0, 250.0), (90.0, 610.0))
# Background and RMS keep their own fixed cells whatever the object cores are.
_BACKGROUND_CORE_YX = (128, 128)
_DEFERRED_FILAMENT = WideObjectCounts(deferred_fit_parents=1)


def _beam(
    yy: npt.NDArray[np.float64],
    xx: npt.NDArray[np.float64],
    centre_yx: tuple[float, float],
    sigma_pixels: float,
) -> npt.NDArray[np.float64]:
    """Return one unit-peak circular Gaussian."""
    radius_squared = (yy - centre_yx[0]) ** 2 + (xx - centre_yx[1]) ** 2
    return np.exp(-radius_squared / (2.0 * sigma_pixels**2))


def _filament(
    yy: npt.NDArray[np.float64],
    xx: npt.NDArray[np.float64],
    ends_yx: tuple[tuple[float, float], tuple[float, float]],
) -> npt.NDArray[np.float64]:
    """Return one unit-peak straight filament two pixels in sigma."""
    start, stop = np.array(ends_yx[0]), np.array(ends_yx[1])
    length = np.linalg.norm(stop - start)
    direction = (stop - start) / length
    along = np.clip(
        (yy - start[0]) * direction[0] + (xx - start[1]) * direction[1],
        0.0,
        length,
    )
    distance = np.hypot(
        yy - (start[0] + along * direction[0]),
        xx - (start[1] + along * direction[1]),
    )
    return np.exp(-(distance**2) / (2.0 * 2.0**2))


def _image() -> npt.NDArray[np.float64]:
    """Return support on every seam topology of an eight-by-eight grid.

    Units are the unit noise. A compact source sits on each of the forty-nine
    interior four-way corners, and others on the image corners and where a
    seam meets an image edge. A four-lobe shell is centred on one interior
    corner, a diffuse Gaussian on another, and a close blend straddles a
    seam. A long filament crosses every column seam and four row seams
    through four corner sources, ending in the tile where the narrow last row
    meets the last column; its fit window exceeds the reviewed compact bound,
    so its fit parent is deferred on any grid. A short filament crosses three
    column seams and is fitted from one window.
    """
    yy, xx = np.mgrid[: _SHAPE_YX[0], : _SHAPE_YX[1]].astype(np.float64)
    sigma = _BEAM_FWHM_PIXELS / (2.0 * np.sqrt(2.0 * np.log(2.0)))
    image = np.random.default_rng(15_402).normal(0.0, 1.0, _SHAPE_YX)
    for centre in _COMPACT_CENTRES:
        image += 30.0 * _beam(yy, xx, centre, sigma)
    image += 25.0 * _beam(yy, xx, (300.0, 117.0), sigma)
    image += 20.0 * _beam(yy, xx, (300.0, 123.0), sigma)
    image += 5.0 * _beam(yy, xx, (_SEAMS[2], _SEAMS[0]), 10.0)
    shell_y, shell_x = yy - _SEAMS[1], xx - _SEAMS[2]
    radius = np.hypot(shell_y, shell_x)
    lobes = 1.0 + 8.0 * np.clip(
        np.cos(4.0 * np.arctan2(shell_y, shell_x)), 0, None
    )
    image += 2.0 * lobes * np.exp(-((radius - 25.0) ** 2) / 8.0)
    image += 10.0 * _filament(yy, xx, _LONG_FILAMENT)
    image += 10.0 * _filament(yy, xx, _SHORT_FILAMENT)
    return image


def _masked_around(
    mask: npt.NDArray[np.bool_], centre_yx: tuple[float, float]
) -> bool:
    """Return whether the pixels nearest one centre are all retained."""
    y, x = (int(value + 0.5) for value in centre_yx)
    block = mask[max(y - 1, 0) : y + 1, max(x - 1, 0) : x + 1]
    return block.size > 0 and bool(block.all())


def _header(shape_yx: tuple[int, int]) -> fits.Header:
    """Return one valid ICRS header with a four-pixel beam."""
    height, width = shape_yx
    header = fits.Header()
    header["BUNIT"] = "Jy/beam"
    header["BMAJ"] = _BEAM_FWHM_PIXELS / 3600.0
    header["BMIN"] = _BEAM_FWHM_PIXELS / 3600.0
    header["BPA"] = 0.0
    header["RADESYS"] = "ICRS"
    header["CTYPE1"] = "RA---TAN"
    header["CTYPE2"] = "DEC--TAN"
    header["CRPIX1"] = width / 2 + 1
    header["CRPIX2"] = height / 2 + 1
    header["CRVAL1"] = 180.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0
    header["CUNIT1"] = "deg"
    header["CUNIT2"] = "deg"
    header["RESTFRQ"] = 150_000_000.0
    return header


def _tiled_passes() -> Iterator[tuple[str, Callable[..., Any]]]:
    """Yield every public pass whose output cores a caller can choose."""
    for name, function in vars(public_api).items():
        if (
            inspect.isfunction(function)
            and function.__module__ == public_api.__name__
            and "tile_core_pixels" in inspect.signature(function).parameters
        ):
            yield name, function


class _PlanRecorder:
    """Record the tile count of every partition the public path plans."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Wrap the planner the public module calls."""
        self.tile_counts: list[int] = []
        self._plan = public_api.plan_image_partitions
        monkeypatch.setattr(public_api, "plan_image_partitions", self)

    def __call__(self, **arguments: Any) -> PartitionManifest:
        """Plan as the public path asked, keeping the object-pass counts."""
        manifest = self._plan(**arguments)
        if manifest.tile_core_shape_yx != _BACKGROUND_CORE_YX:
            self.tile_counts.append(len(manifest.tiles))
        return manifest


def _find_sources(
    image_path: Path,
    output_directory: Path,
    executor: Executor,
) -> SourceFinderResult:
    """Run the public finder on the shared input into one directory."""
    return hebog.find_sources(
        SourceFinderRequest(image_path, output_directory, "tile-grid"),
        SourceFinderConfig(5.0, 3.0, 7),
        executor,
    )


def _shared_input(one_tile: SourceFinderResult) -> Path:
    """Return the input the one-tile products were published from."""
    return one_tile.catalogue_path.parents[1] / "image.fits"


@pytest.fixture(scope="module")
def one_tile(tmp_path_factory: pytest.TempPathFactory) -> SourceFinderResult:
    """Write the shared input and publish its products from one tile."""
    directory = tmp_path_factory.mktemp("tile-grid")
    image = _image()
    fits.PrimaryHDU(data=image, header=_header(image.shape)).writeto(
        directory / "image.fits"
    )
    with pytest.MonkeyPatch.context() as monkeypatch:
        recorder = _PlanRecorder(monkeypatch)
        result = _find_sources(
            directory / "image.fits", directory / "one-tile", SerialExecutor()
        )
    assert recorder.tile_counts and set(recorder.tile_counts) == {1}
    return result


def _grid_cores(monkeypatch: pytest.MonkeyPatch) -> _PlanRecorder:
    """Run every tiled public pass on the eight-by-eight grid's cores."""
    passes = dict(_tiled_passes())
    # The composition's nine tiled passes; a new one must join this grid.
    assert len(passes) == 9
    for name, function in passes.items():
        monkeypatch.setattr(
            public_api, name, partial(function, tile_core_pixels=_CORE_PIXELS)
        )
    return _PlanRecorder(monkeypatch)


def test_the_grid_is_the_largest_the_envelope_admits() -> None:
    """A raise that adds tiles per side must widen this grid with it."""
    envelope = public_api._MAXIMUM_PREVIEW_DIMENSION  # pyright: ignore[reportPrivateUsage]

    tiles_per_side = math.ceil(envelope / public_api.ADMITTED_TILE_CORE_PIXELS)

    assert tiles_per_side == _TILES_PER_SIDE
    for side in _SHAPE_YX:
        assert math.ceil(side / _CORE_PIXELS) == _TILES_PER_SIDE


def test_the_last_row_of_tiles_ends_inside_the_widest_filter_halo() -> None:
    """The halo of the row above spans the narrow row to the image edge."""
    beam = BeamShapePixels(
        major_fwhm_pixels=_BEAM_FWHM_PIXELS,
        minor_fwhm_pixels=_BEAM_FWHM_PIXELS,
        position_angle_degrees=0.0,
    )
    halo = scale_filter_halo_pixels(beam)

    last_row_height = _SHAPE_YX[0] - (_TILES_PER_SIDE - 1) * _CORE_PIXELS

    assert 0 < last_row_height < halo


@IGNORE_RMS_KERNEL_WARNINGS
def test_products_on_the_envelope_grid_equal_one_tile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    one_tile: SourceFinderResult,
    each_executor: Executor,
) -> None:
    """Sixty-four tiles publish the one-tile products under every executor."""
    recorder = _grid_cores(monkeypatch)

    grid = _find_sources(
        _shared_input(one_tile), tmp_path / "products", each_executor
    )

    assert set(recorder.tile_counts) == {_GRID_TILES}
    assert product_hashes(grid) == product_hashes(one_tile)


def test_one_tile_publishes_support_on_every_seam_topology(
    one_tile: SourceFinderResult,
) -> None:
    """The reference the grid runs match holds every object it was given."""
    diagnostics = read_diagnostics_product(one_tile.diagnostics)
    assert isinstance(diagnostics, PublicSourceFindingDiagnostics)
    # The filament's fit parent is deferred, so its components are described
    # from the cores it crosses rather than from a window.
    assert diagnostics.wide_object_counts == _DEFERRED_FILAMENT
    mask = np.asarray(fits.getdata(one_tile.mask_path), dtype=np.bool_)
    for centre in (*_COMPACT_CENTRES, _LONG_FILAMENT[1], *_SHORT_FILAMENT):
        assert _masked_around(mask, centre), centre
    # Four compact sources lie on the long filament and may join its source.
    assert one_tile.source_count >= len(_COMPACT_CENTRES) - 4


def test_wide_objects_decided_on_the_grid_cores_publish_one_tile_products(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    one_tile: SourceFinderResult,
) -> None:
    """With no window admitted, every object is reduced across its cores.

    A one-pixel read budget sends every object down the wide paths, so each
    island, segment and owner crossing a seam or a four-way corner is decided
    from the cores it touches rather than from a window holding it. It runs
    under the serial reference only, which keeps the portable suite's cost
    down (``LOG.md``, task 49).
    """
    recorder = _grid_cores(monkeypatch)
    monkeypatch.setattr(public_api, "_OWNER_BATCH_READ_PIXELS", 1)

    wide = _find_sources(
        _shared_input(one_tile), tmp_path / "products", SerialExecutor()
    )

    assert set(recorder.tile_counts) == {_GRID_TILES}
    assert product_hashes(wide)[:3] == product_hashes(one_tile)[:3]
    diagnostics = read_diagnostics_product(wide.diagnostics)
    expected = read_diagnostics_product(one_tile.diagnostics)
    assert isinstance(diagnostics, PublicSourceFindingDiagnostics)
    assert isinstance(expected, PublicSourceFindingDiagnostics)
    counts = diagnostics.wide_object_counts
    assert counts.islands == diagnostics.island_count > 0
    assert counts.publication_owners > 0
    assert counts.support_components > 0
    assert counts.segments > 0
    assert counts.deferred_fit_parents == 1
    assert expected.wide_object_counts == _DEFERRED_FILAMENT
    assert (
        diagnostics.model_copy(
            update={"wide_object_counts": _DEFERRED_FILAMENT}
        )
        == expected
    )
