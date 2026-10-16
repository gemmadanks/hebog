# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""A retried request returns the products its finished run published.

A run publishes its bundle in one rename, so a bundle in place is complete.
When the same request runs again, with the same run ID, input bytes,
configuration and science, ``find_sources`` returns those products without
analysing the image again. Any other existing output is refused and kept.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TypeVar

import numpy as np
import pytest
from astropy.io import fits

import hebog
from hebog import SourceFinderConfig, SourceFinderRequest, SourceFinderResult
from hebog.executors import Executor, SerialExecutor, TaskRequirement
from hebog.pipeline import SourceFinderOutputExistsError

pytestmark = pytest.mark.integration

_Input = TypeVar("_Input")
_Output = TypeVar("_Output")
_SHAPE_YX = (64, 72)


class _CountingExecutor(SerialExecutor):
    """Serial executor that counts every map it is given."""

    def __init__(self) -> None:
        """Start with no calls."""
        super().__init__()
        self.calls = 0

    def map_batches(
        self,
        function: Callable[[_Input], _Output],
        batches: Iterable[_Input],
        *,
        requirement: TaskRequirement | None = None,
    ) -> list[_Output]:
        """Count the call, then run it in order."""
        self.calls += 1
        return super().map_batches(function, batches, requirement=requirement)


def _write(path: Path, values: np.ndarray, **cards: object) -> Path:
    """Write one valid ICRS radio continuum image."""
    height, width = values.shape
    header = fits.Header()
    header["BUNIT"] = "Jy/beam"
    header["BMAJ"] = 4.0 / 3600.0
    header["BMIN"] = 4.0 / 3600.0
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
    for keyword, value in cards.items():
        header[keyword] = value
    fits.PrimaryHDU(data=values, header=header).writeto(path, overwrite=True)
    return path


def _image(seed: int) -> np.ndarray:
    """Return two compact sources on unit noise."""
    y_pixels, x_pixels = np.mgrid[: _SHAPE_YX[0], : _SHAPE_YX[1]]
    image = np.random.default_rng(seed).normal(0.0, 1.0, _SHAPE_YX)
    for y, x, peak in ((30, 20, 40.0), (20, 50, 15.0)):
        image += peak * np.exp(
            -((x_pixels - x) ** 2 + (y_pixels - y) ** 2) / 4.0
        )
    return np.asarray(image, dtype=np.float64)


def _config(detection_threshold_sigma: float = 5.0) -> SourceFinderConfig:
    return SourceFinderConfig(detection_threshold_sigma, 3.0, 7)


def _request(
    tmp_path: Path, *, run_id: str = "sector-0", flat_noise: bool = True
) -> SourceFinderRequest:
    """Return one sector's request, writing its images if they are absent."""
    true_sky = tmp_path / "true-sky.fits"
    flat_noise_path = tmp_path / "flat-noise.fits"
    if not true_sky.exists():
        _write(true_sky, _image(3))
        _write(flat_noise_path, _image(4))
    return SourceFinderRequest(
        true_sky,
        tmp_path / "products",
        run_id,
        flat_noise_image_path=flat_noise_path if flat_noise else None,
    )


def _modification_times(directory: Path) -> dict[str, int]:
    return {path.name: path.stat().st_mtime_ns for path in directory.iterdir()}


def _without_timing(result: SourceFinderResult) -> dict[str, object]:
    return result.model_dump(exclude={"wall_seconds"})


def test_a_retried_request_returns_the_finished_products_without_analysis(
    tmp_path: Path, each_executor: Executor
) -> None:
    """Given a finished run, when it is retried, then nothing is recomputed.

    The retry returns the same product records, submits no task and
    rewrites no file, whichever executor ran the first attempt.
    """
    request = _request(tmp_path)
    first = hebog.find_sources(request, _config(), each_executor)
    published = _modification_times(request.output_directory)
    retry_executor = _CountingExecutor()

    retried = hebog.find_sources(request, _config(), retry_executor)

    assert retry_executor.calls == 0
    assert _without_timing(retried) == _without_timing(first)
    assert retried.flat_noise_rms is not None
    assert _modification_times(request.output_directory) == published


def test_a_retry_through_a_relative_output_path_reuses_the_products(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The request is bound to the working directory before it is compared."""
    monkeypatch.chdir(tmp_path)
    absolute = _request(tmp_path)
    relative = SourceFinderRequest(
        Path("true-sky.fits"),
        Path("products"),
        "sector-0",
        flat_noise_image_path=Path("flat-noise.fits"),
    )
    first = hebog.find_sources(absolute, _config(), SerialExecutor())
    retry_executor = _CountingExecutor()

    retried = hebog.find_sources(relative, _config(), retry_executor)

    assert retry_executor.calls == 0
    assert _without_timing(retried) == _without_timing(first)


@pytest.mark.parametrize(
    "difference",
    ["run-id", "threshold", "input-bytes", "flat-noise-image"],
)
def test_an_output_of_another_request_is_refused_and_kept(
    tmp_path: Path, difference: str
) -> None:
    """Given a finished run, a request that differs in any identity is refused.

    The products it would publish differ, so the existing ones are neither
    returned nor replaced.
    """
    hebog.find_sources(
        _request(tmp_path, flat_noise=difference != "flat-noise-image"),
        _config(),
        SerialExecutor(),
    )
    request = _request(
        tmp_path, run_id="sector-1" if difference == "run-id" else "sector-0"
    )
    config = _config(6.0 if difference == "threshold" else 5.0)
    if difference == "input-bytes":
        _write(request.image_path, _image(3), OBJECT="another field")
    published = _modification_times(request.output_directory)

    with pytest.raises(SourceFinderOutputExistsError, match="already exists"):
        hebog.find_sources(request, config, _CountingExecutor())

    assert _modification_times(request.output_directory) == published


@pytest.mark.parametrize(
    "damage",
    ["missing-rms", "unreadable-diagnostics", "missing-flat-noise-rms"],
)
def test_an_incomplete_output_is_refused_rather_than_reused(
    tmp_path: Path, damage: str
) -> None:
    """Only a complete bundle of this request is returned on a retry."""
    request = _request(tmp_path)
    hebog.find_sources(request, _config(), SerialExecutor())
    output = request.output_directory
    if damage == "missing-rms":
        (output / "rms.fits").unlink()
    elif damage == "missing-flat-noise-rms":
        (output / "flat-noise-rms.fits").unlink()
    else:
        (output / "diagnostics.json").write_text("{", encoding="utf-8")
    retry_executor = _CountingExecutor()

    with pytest.raises(SourceFinderOutputExistsError, match="already exists"):
        hebog.find_sources(request, _config(), retry_executor)

    assert retry_executor.calls == 0
