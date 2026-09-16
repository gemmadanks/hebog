"""Filesystem primitive for publishing a product directory exactly once."""

from __future__ import annotations

import os
from contextlib import suppress
from pathlib import Path


def rename_without_replacement(source: Path, destination: Path) -> None:
    """Move ``source`` onto ``destination`` without replacing anything there.

    A plain POSIX rename silently replaces an existing empty directory, so a
    destination claimed while an analysis runs could be lost. ``mkdir`` is an
    atomic exclusive claim: once it succeeds no other writer can take the
    path, so the rename that follows can only replace this call's own empty
    directory. Windows ``rename`` refuses an existing destination by itself
    and needs no claim. A failed rename removes the claim again.

    The claim makes the destination path exist, empty, for the two system
    calls between claiming and renaming, so an observer watching the path can
    briefly see an empty directory. The contents then appear in one rename:
    no partially written bundle is ever visible. Callers treat a successful
    return, not the existence of the path, as the completion boundary.

    Args:
        source: Existing staged directory to publish.
        destination: Path that must not already exist.

    Raises:
        FileExistsError: Something already exists at the destination,
            including an empty directory or a symbolic link.
        OSError: The publication failed for any other reason.
    """
    if os.name == "nt":
        os.rename(source, destination)
        return
    os.mkdir(destination)
    try:
        os.rename(source, destination)
    except OSError:
        with suppress(OSError):
            os.rmdir(destination)
        raise
