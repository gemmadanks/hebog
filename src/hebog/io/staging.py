"""Hidden staging directories that record their owner.

``find_sources`` builds a run's work planes and product bundle in a hidden
directory beside the output, ``.<output name>.<random>``, and removes it when
the run returns. A process that is killed cannot remove it, so the directory
records who owns it: ``owner.json`` names the output, run, host, process and
start time, and the owner holds an exclusive lock on ``owner.lock`` for as
long as that record exists. The operating system releases the lock when the
process ends, however it ends, so on the owner's host a record whose lock
another process can take proves that the owner has stopped, even after its
process identifier is reused or from another process namespace. A filesystem
shared between hosts may keep its locks per host, so a directory recorded on
another host is never reclaimed, and neither is one whose owner could not
lock.

The lock proves only that the owning process stopped. Tasks it submitted to
a cluster that outlives it run to completion and may write into the
directory after it has been reclaimed; what they recreate holds no record,
so it is reported and never removed.
"""

from __future__ import annotations

import os
import shutil
import socket
import sys
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import BinaryIO, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

OWNER_RECORD_NAME = "owner.json"
OWNER_LOCK_NAME = "owner.lock"

if sys.platform == "win32":
    import msvcrt

    def _lock(handle: BinaryIO) -> None:
        """Lock an open file's first byte now, or raise ``OSError``."""
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(handle: BinaryIO) -> None:
        """Release the lock ``_lock`` took, before the file is closed."""
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock(handle: BinaryIO) -> None:
        """Lock an open file exclusively now, or raise ``OSError``."""
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(handle: BinaryIO) -> None:
        """Release the lock ``_lock`` took, before the file is closed."""
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class StagingOwner(BaseModel):
    """The run that created one staging directory, recorded inside it."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    output_name: str
    run_id: str
    host: str
    process_id: int
    started_utc: datetime
    holds_lock: bool
    schema_version: Literal[1] = 1


LeftoverStatus = Literal["reclaimed", "unremovable", "unproven"]


@dataclass(frozen=True, slots=True)
class LeftoverStaging:
    """One staging directory an earlier run left beside the same output.

    ``owner`` is ``None`` when the directory holds no owner record this
    version reads. ``status`` is ``reclaimed`` when the owner had provably
    stopped and the directory was removed, ``unremovable`` when it had
    stopped but the directory could not be removed, and ``unproven`` when
    the owner may still be running, so the directory was left in place.
    """

    path: Path
    owner: StagingOwner | None
    status: LeftoverStatus

    @property
    def notice(self) -> str:
        """Say what was found and what was done, for the operator."""
        if self.owner is None:
            return (
                f"left staging directory {self.path} in place: it holds no "
                "owner record this version of Hebog reads; remove it once "
                "no run uses it"
            )
        started = self.owner.started_utc.isoformat(timespec="seconds")
        run = (
            f"run {self.owner.run_id!r} (process {self.owner.process_id} "
            f"on host {self.owner.host}, started {started})"
        )
        if self.status == "reclaimed":
            return (
                f"removed staging directory {self.path} left by {run}, "
                "which has stopped"
            )
        if self.status == "unremovable":
            return (
                f"could not remove staging directory {self.path} left by "
                f"{run}, which has stopped; remove it by hand"
            )
        return (
            f"left staging directory {self.path} in place: {run} may still "
            "be running; remove it once that run has stopped"
        )


@contextmanager
def staging_directory(output: Path, *, run_id: str) -> Generator[Path]:
    """Create a hidden staging directory beside ``output`` and own it.

    The directory is removed when the block ends, however it ends. The
    record is written only once the lock is held and removed before it is
    released, so a later run never takes a starting or finishing owner for
    a stopped one, and never tests a lock no record names. A filesystem that
    cannot lock does not stop the run; its record says so, and no later run
    reclaims it.
    """
    with TemporaryDirectory(
        prefix=f".{output.name}.", dir=output.parent
    ) as name:
        directory = Path(name)
        record = directory / OWNER_RECORD_NAME
        # The lock file is closed before the directory is removed, which
        # Windows requires.
        with (directory / OWNER_LOCK_NAME).open("xb") as lock:
            try:
                _lock(lock)
            except OSError:
                holds_lock = False
            else:
                holds_lock = True
            owner = StagingOwner(
                output_name=output.name,
                run_id=run_id,
                host=socket.gethostname(),
                process_id=os.getpid(),
                started_utc=datetime.now(UTC),
                holds_lock=holds_lock,
            )
            record.write_text(owner.model_dump_json(), encoding="utf-8")
            try:
                yield directory
            finally:
                record.unlink(missing_ok=True)
                if holds_lock:
                    # Closing releases it too, but Windows may release a
                    # closed file's lock only some time later.
                    _unlock(lock)


def _recorded_owner(directory: Path) -> StagingOwner | None:
    """Return a staging directory's owner record, if it holds one."""
    try:
        return StagingOwner.model_validate_json(
            (directory / OWNER_RECORD_NAME).read_bytes()
        )
    except (OSError, ValidationError):
        return None


def _lock_is_free(directory: Path) -> bool:
    """Return whether this process can take the directory's owner lock.

    The lock is released again at once. A lock that is held, a file that
    cannot be opened for writing, and a filesystem that cannot lock all
    leave the owner unproven.
    """
    try:
        with (directory / OWNER_LOCK_NAME).open("r+b") as lock:
            _lock(lock)
            _unlock(lock)
    except OSError:
        return False
    return True


def _has_stopped(owner: StagingOwner, directory: Path) -> bool:
    """Return whether the directory's owner has provably stopped."""
    return (
        owner.holds_lock
        and owner.host == socket.gethostname()
        and _lock_is_free(directory)
    )


def reclaim_abandoned_staging(output: Path) -> tuple[LeftoverStaging, ...]:
    """Remove staging directories stopped runs left beside ``output``.

    Every staging directory found for ``output`` is returned in name order:
    those whose owner has provably stopped are removed, and every other one
    is left in place for the caller to report. A directory whose record
    names another output, one whose name extends this output's, is skipped.

    Args:
        output: The output directory a new run is about to write.

    Returns:
        One record for each staging directory left beside ``output``.
    """
    prefix = f".{output.name}."
    leftovers: list[LeftoverStaging] = []
    for directory in sorted(output.parent.iterdir()):
        if (
            not directory.name.startswith(prefix)
            or directory.is_symlink()
            or not directory.is_dir()
        ):
            continue
        owner = _recorded_owner(directory)
        if owner is not None and owner.output_name != output.name:
            continue
        status: LeftoverStatus = "unproven"
        if owner is not None and _has_stopped(owner, directory):
            # Another run may be removing the same directory at once, so a
            # missing entry is not an error; what remains is checked after.
            shutil.rmtree(directory, ignore_errors=True)
            status = "unremovable" if directory.exists() else "reclaimed"
        leftovers.append(LeftoverStaging(directory, owner, status))
    return tuple(leftovers)
