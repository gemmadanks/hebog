# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false
# pyright: reportUnknownVariableType=false
"""FFT convolution shared by threaded executors."""

from __future__ import annotations

import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Literal

import numpy as np
import numpy.typing as npt
import pytest
from scipy.signal import fftconvolve as scipy_fftconvolve

from hebog.algorithms import fft


@pytest.mark.parametrize("mode", ["full", "same", "valid"])
@pytest.mark.parametrize("serialized", [False, True])
def test_convolution_is_scipy_s_to_the_bit(
    monkeypatch: pytest.MonkeyPatch,
    mode: Literal["full", "same", "valid"],
    serialized: bool,
) -> None:
    """Serializing a transform orders calls and changes no value."""
    monkeypatch.setattr(fft, "_TRANSFORMS_SHARE_UNLOCKED_STATE", serialized)
    rng = np.random.default_rng(5)
    image = rng.normal(size=(37, 41, 3))
    kernel = rng.normal(size=(7, 5, 1))

    for axes in (None, (0, 1)):
        np.testing.assert_array_equal(
            fft.fftconvolve(image, kernel, mode=mode, axes=axes),
            scipy_fftconvolve(image, kernel, mode=mode, axes=axes),
        )


class _OverlapRecorder:
    """Stand in for SciPy's transform, recording how many run at once."""

    def __init__(self) -> None:
        """Start with no transform running."""
        self._guard = threading.Lock()
        self._running = 0
        self.most_at_once = 0
        self.lock_held: list[bool] = []

    def __call__(self, *_args: Any, **_kwargs: Any) -> npt.NDArray[Any]:
        """Hold the call open long enough for another thread to enter."""
        self.lock_held.append(fft._TRANSFORM_LOCK.locked())
        with self._guard:
            self._running += 1
            self.most_at_once = max(self.most_at_once, self._running)
        time.sleep(0.01)
        with self._guard:
            self._running -= 1
        return np.zeros(1)


def _convolve_once(_index: int) -> npt.NDArray[np.float64]:
    """Run one convolution, as one executor task would."""
    return fft.fftconvolve([1.0], [1.0])


def _convolve_from_threads() -> None:
    """Convolve from four threads at once, as a threaded executor does."""
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(_convolve_once, range(16)))


def test_transforms_take_turns_where_scipy_shares_unlocked_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Where the plan cache has no lock, no two transforms overlap."""
    recorder = _OverlapRecorder()
    monkeypatch.setattr(fft, "_scipy_fftconvolve", recorder)
    monkeypatch.setattr(fft, "_TRANSFORMS_SHARE_UNLOCKED_STATE", True)

    _convolve_from_threads()

    assert recorder.most_at_once == 1
    assert all(recorder.lock_held) and len(recorder.lock_held) == 16


def test_transforms_run_concurrently_where_scipy_locks_its_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Elsewhere Hebog adds no lock, so threads keep their parallelism."""
    recorder = _OverlapRecorder()
    monkeypatch.setattr(fft, "_scipy_fftconvolve", recorder)
    monkeypatch.setattr(fft, "_TRANSFORMS_SHARE_UNLOCKED_STATE", False)

    _convolve_from_threads()

    assert not any(recorder.lock_held) and len(recorder.lock_held) == 16


def test_only_windows_serializes_transforms() -> None:
    """SciPy's MinGW-built Windows wheels are the ones without the lock."""
    assert fft._TRANSFORMS_SHARE_UNLOCKED_STATE is (sys.platform == "win32")


# Any import that reaches SciPy's or NumPy's FFT, including the convolutions
# that may choose it: scipy.signal's convolve and correlate pick FFT by size.
_DIRECT_FFT = re.compile(
    r"^\s*(?:import (?:scipy\.fft|numpy\.fft)"
    r"|from (?:scipy\.fft|numpy\.fft|scipy\.signal)\b[^\n]*"
    r"|from (?:scipy|numpy) import [^\n]*\bfft\b"
    r"|[^\n]*\bnp\.fft\.)",
    re.MULTILINE,
)


def test_every_fft_goes_through_the_guarded_wrapper() -> None:
    """A direct FFT call would bypass the Windows lock and crash again."""
    wrapper = Path(fft.__file__)
    package = wrapper.parents[1]

    offenders = sorted(
        path.relative_to(package).as_posix()
        for path in package.rglob("*.py")
        if path != wrapper
        and _DIRECT_FFT.search(path.read_text(encoding="utf-8"))
    )

    assert offenders == []
    assert _DIRECT_FFT.search(wrapper.read_text(encoding="utf-8")), (
        "the wrapper no longer imports SciPy's FFT, so this rule is stale"
    )
