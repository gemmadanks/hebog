# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownVariableType=false
"""FFT convolution that threaded executors can share safely.

SciPy's ``win_amd64`` wheels are built with MinGW-w64, and for that toolchain
SciPy compiles its FFT backend, ducc0, with ``DUCC0_NO_LOWLEVEL_THREADING``
(``scipy/fft/_duccfft/meson.build`` from SciPy 1.18). That macro also turns
the lock around ducc0's process-wide plan cache into a no-op, so two threads
transforming at once race on the cache and can corrupt the heap: a
``ThreadExecutor`` or a threaded Dask worker then crashes the process on
Windows. On Windows every transform here therefore takes a process-wide lock.
The lock orders calls and changes no value; elsewhere SciPy's own lock is
compiled in, and calls run concurrently.
"""

from __future__ import annotations

import sys
import threading
from contextlib import AbstractContextManager, nullcontext
from typing import Literal

import numpy as np
import numpy.typing as npt
from scipy.signal import fftconvolve as _scipy_fftconvolve

_TRANSFORMS_SHARE_UNLOCKED_STATE = sys.platform == "win32"
_TRANSFORM_LOCK = threading.Lock()


def _transform_guard() -> AbstractContextManager[object]:
    """Return the lock one transform holds, or no lock where none is needed."""
    if _TRANSFORMS_SHARE_UNLOCKED_STATE:
        return _TRANSFORM_LOCK
    return nullcontext()


def fftconvolve(
    in1: npt.ArrayLike,
    in2: npt.ArrayLike,
    mode: Literal["full", "valid", "same"] = "full",
    axes: int | tuple[int, ...] | None = None,
) -> npt.NDArray[np.float64]:
    """Convolve like :func:`scipy.signal.fftconvolve`, safely across threads.

    >>> fftconvolve([1.0, 2.0], [1.0, 1.0]).round(12).tolist()
    [1.0, 3.0, 2.0]
    """
    with _transform_guard():
        return np.asarray(_scipy_fftconvolve(in1, in2, mode=mode, axes=axes))
