# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Public products do not change with the tile grid the passes run on.

The public passes after background and RMS run on 2,048-pixel cores, so the
10,000-pixel envelope is a five-by-five grid: interior tiles bounded on all
four sides and sixteen four-way corners, neither of which the four tiles of a
3,000-pixel image hold. These tests give a small analytic image that same grid
by shrinking the cores, put support on every interior corner, seam and image
edge, and require the complete product set to equal the one-tile run's.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterator
from functools import partial
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest
from astropy.io import fits
from distributed import Client, LocalCluster

import hebog
from hebog import SourceFinderConfig, SourceFinderRequest, public_api
from hebog.data_models import (
    PartitionManifest,
    PublicSourceFindingDiagnostics,
    WideObjectCounts,
)
from hebog.executors import DaskExecutor, Executor, SerialExecutor
from hebog.io import read_diagnostics_product
from hebog.pipeline import SourceFinderResult

pytestmark = pytest.mark.integration

_SHAPE_YX = (560, 600)
_CORE_PIXELS = 120
_GRID_TILES = 25
_BEAM_FWHM_PIXELS = 4.0
_SEAMS = tuple(_CORE_PIXELS * index - 0.5 for index in range(1, 5))
# Background and RMS keep their own fixed cells whatever the object cores are.
_BACKGROUND_CORE_YX = (128, 128)


def _beam(
    yy: npt.NDArray[np.float64],
    xx: npt.NDArray[np.float64],
    centre_yx: tuple[float, float],
    sigma_pixels: float,
) -> npt.NDArray[np.float64]:
    """Return one unit-peak circular Gaussian."""
    radius_squared = (yy - centre_yx[0]) ** 2 + (xx - centre_yx[1]) ** 2
    return np.exp(-radius_squared / (2.0 * sigma_pixels**2))


def _image() -> npt.NDArray[np.float64]:
    """Return support on every seam topology of a five-by-five grid.

    Units are the unit noise. A compact source sits on each of the sixteen
    interior four-way corners, and others on the image corners and where a
    seam meets an image edge. A four-lobe shell is centred on one interior
    corner, a diffuse Gaussian on another, a close blend straddles a seam,
    and a filament crosses four column seams and a row seam, passing a corner
    source on its way.
    """
    yy, xx = np.mgrid[: _SHAPE_YX[0], : _SHAPE_YX[1]].astype(np.float64)
    sigma = _BEAM_FWHM_PIXELS / (2.0 * np.sqrt(2.0 * np.log(2.0)))
    image = np.random.default_rng(10_000).normal(0.0, 1.0, _SHAPE_YX)
    compact = [(y, x) for y in _SEAMS for x in _SEAMS]
    compact += [(0.0, 0.0), (0.0, 599.0), (559.0, 0.0), (559.0, 599.0)]
    compact += [(0.0, _SEAMS[0]), (559.0, _SEAMS[2]), (_SEAMS[1], 0.0)]
    compact += [(_SEAMS[3], 599.0)]
    for centre in compact:
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
    start, stop = np.array([380.0, 40.0]), np.array([500.0, 560.0])
    direction = (stop - start) / np.linalg.norm(stop - start)
    along = np.clip(
        (yy - start[0]) * direction[0] + (xx - start[1]) * direction[1],
        0.0,
        np.linalg.norm(stop - start),
    )
    distance = np.hypot(
        yy - (start[0] + along * direction[0]),
        xx - (start[1] + along * direction[1]),
    )
    image += 10.0 * np.exp(-(distance**2) / (2.0 * 2.0**2))
    return image


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
    directory: Path,
    output_name: str,
    executor: Executor,
) -> SourceFinderResult:
    """Run the public finder on the shared input under one output name."""
    return hebog.find_sources(
        SourceFinderRequest(
            directory / "image.fits", directory / output_name, "tile-grid"
        ),
        SourceFinderConfig(5.0, 3.0, 7),
        executor,
    )


def _product_hashes(result: SourceFinderResult) -> tuple[str, ...]:
    """Return the content identity of every published product."""
    return (
        result.catalogue.content_sha256,
        result.rms.content_sha256,
        result.mask.content_sha256,
        result.diagnostics.content_sha256,
    )


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
        result = _find_sources(directory, "one-tile", SerialExecutor())
    assert recorder.tile_counts and set(recorder.tile_counts) == {1}
    return result


def _grid_cores(monkeypatch: pytest.MonkeyPatch) -> _PlanRecorder:
    """Run every tiled public pass on the five-by-five grid's cores."""
    passes = dict(_tiled_passes())
    # The composition's nine tiled passes; a new one must join this grid.
    assert len(passes) == 9
    for name, function in passes.items():
        monkeypatch.setattr(
            public_api, name, partial(function, tile_core_pixels=_CORE_PIXELS)
        )
    return _PlanRecorder(monkeypatch)


def test_products_on_the_ten_thousand_pixel_grid_equal_one_tile(
    monkeypatch: pytest.MonkeyPatch,
    one_tile: SourceFinderResult,
) -> None:
    """Twenty-five tiles, serial or on Dask, publish the one-tile products."""
    directory = one_tile.catalogue_path.parents[1]
    recorder = _grid_cores(monkeypatch)

    serial = _find_sources(directory, "grid-serial", SerialExecutor())
    cluster = LocalCluster(
        n_workers=2,
        threads_per_worker=1,
        processes=False,
        dashboard_address="",
    )
    with cluster, Client(cluster) as client:
        dask = _find_sources(directory, "grid-dask", DaskExecutor(client))

    assert set(recorder.tile_counts) == {_GRID_TILES}
    assert _product_hashes(serial) == _product_hashes(one_tile)
    assert _product_hashes(dask) == _product_hashes(one_tile)
    mask = np.asarray(fits.getdata(one_tile.mask_path), dtype=np.bool_)
    for seam_y in _SEAMS:
        for seam_x in _SEAMS:
            y, x = int(seam_y + 0.5), int(seam_x + 0.5)
            assert mask[y - 1 : y + 1, x - 1 : x + 1].all(), (y, x)
    assert one_tile.source_count >= len(_SEAMS) ** 2


def test_wide_objects_decided_on_the_grid_cores_publish_one_tile_products(
    monkeypatch: pytest.MonkeyPatch,
    one_tile: SourceFinderResult,
) -> None:
    """With no window admitted, every object is reduced across its cores.

    A one-pixel read budget sends every object down the wide paths, so each
    island, segment and owner crossing a seam or a four-way corner is decided
    from the cores it touches rather than from a window holding it.
    """
    directory = one_tile.catalogue_path.parents[1]
    recorder = _grid_cores(monkeypatch)
    monkeypatch.setattr(public_api, "_OWNER_BATCH_READ_PIXELS", 1)

    wide = _find_sources(directory, "grid-wide", SerialExecutor())

    assert set(recorder.tile_counts) == {_GRID_TILES}
    assert _product_hashes(wide)[:3] == _product_hashes(one_tile)[:3]
    diagnostics = read_diagnostics_product(wide.diagnostics)
    expected = read_diagnostics_product(one_tile.diagnostics)
    assert isinstance(diagnostics, PublicSourceFindingDiagnostics)
    assert isinstance(expected, PublicSourceFindingDiagnostics)
    counts = diagnostics.wide_object_counts
    assert counts.islands == diagnostics.island_count > 0
    assert counts.publication_owners > 0
    assert counts.support_components > 0
    assert counts.segments > 0
    assert expected.wide_object_counts == WideObjectCounts()
    assert (
        diagnostics.model_copy(
            update={"wide_object_counts": WideObjectCounts()}
        )
        == expected
    )
