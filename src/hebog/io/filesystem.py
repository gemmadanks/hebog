"""Filesystem primitives for publishing a product directory exactly once."""

from __future__ import annotations

import ctypes
import errno
import os
import sys
from collections.abc import Callable
from functools import cache
from pathlib import Path

# Linux renameat2(2) and macOS renamex_np(2) refuse an existing destination.
_LINUX_RENAME_NOREPLACE = 1 << 0
_MACOS_RENAME_EXCL = 0x0004
_AT_FDCWD = -100
# The operation is missing on old kernels and unsupported on some file
# systems. Those errors select the checked fallback; any other error is real.
_UNSUPPORTED = frozenset(
    {errno.ENOSYS, errno.ENOTSUP, errno.EOPNOTSUPP, errno.EINVAL}
)


@cache
def _no_replace_renamer() -> Callable[[bytes, bytes], int] | None:
    """Return the platform's no-replace rename, or None when unavailable.

    Windows never replaces an existing destination, so it uses the fallback.
    The C library is loaded on first publication rather than at import.
    """
    if sys.platform == "win32":
        return None
    try:
        libc = ctypes.CDLL(None, use_errno=True)
    except OSError:  # pragma: no cover - libc is always loadable on POSIX
        return None
    if sys.platform == "darwin":
        entry = getattr(libc, "renamex_np", None)
        if entry is None:  # pragma: no cover - present since macOS 10.12
            return None
        entry.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
        entry.restype = ctypes.c_int

        def rename_excl(source: bytes, destination: bytes) -> int:
            return int(entry(source, destination, _MACOS_RENAME_EXCL))

        return rename_excl
    entry = getattr(libc, "renameat2", None)
    if entry is None:  # pragma: no cover - present since glibc 2.28
        return None
    entry.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    entry.restype = ctypes.c_int

    def rename_noreplace(source: bytes, destination: bytes) -> int:
        return int(
            entry(
                _AT_FDCWD,
                source,
                _AT_FDCWD,
                destination,
                _LINUX_RENAME_NOREPLACE,
            )
        )

    return rename_noreplace


def rename_without_replacement(source: Path, destination: Path) -> None:
    """Move ``source`` onto ``destination`` without replacing anything there.

    A plain POSIX rename silently replaces an existing empty directory, so a
    caller-owned destination claimed while an analysis runs could be lost.
    This uses the platform's atomic no-replace rename where it exists, which
    leaves no interval between deciding the destination is free and claiming
    it. Where the operation is unavailable, an explicit check precedes the
    rename and a destination claimed in that interval can still be replaced.

    Args:
        source: Existing staged directory or file to publish.
        destination: Path that must not already exist.

    Raises:
        FileExistsError: The destination exists, including an empty directory
            or a symbolic link with no target.
        OSError: The rename failed for any other reason.
    """
    renamer = _no_replace_renamer()
    if renamer is not None:
        if renamer(os.fsencode(source), os.fsencode(destination)) == 0:
            return
        code = ctypes.get_errno()
        if code in (errno.EEXIST, errno.ENOTEMPTY):
            raise FileExistsError(
                code, os.strerror(code), str(destination)
            ) from None
        if code not in _UNSUPPORTED:
            raise OSError(
                code, os.strerror(code), str(source), None, str(destination)
            ) from None
    if os.name != "nt" and (destination.exists() or destination.is_symlink()):
        raise FileExistsError(
            errno.EEXIST, os.strerror(errno.EEXIST), str(destination)
        )
    os.rename(source, destination)
