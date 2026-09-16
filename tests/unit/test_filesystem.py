"""Contracts for publishing a directory without replacing a destination."""

from __future__ import annotations

import ctypes
import errno
import os
from pathlib import Path

import pytest

from hebog.io.filesystem import rename_without_replacement


def _staged(root: Path) -> Path:
    """Return one staged bundle directory holding a product file."""
    staged = root / "staged"
    staged.mkdir()
    (staged / "catalogue.fits").write_text("product", encoding="utf-8")
    return staged


def test_rename_publishes_an_unclaimed_destination(tmp_path: Path) -> None:
    """The staged directory moves to its destination in one operation."""
    staged = _staged(tmp_path)
    destination = tmp_path / "products"

    rename_without_replacement(staged, destination)

    assert not staged.exists()
    assert (destination / "catalogue.fits").read_text(
        encoding="utf-8"
    ) == "product"


@pytest.mark.parametrize(
    "occupant",
    ("empty-directory", "populated-directory", "file", "dangling-symlink"),
)
def test_rename_never_replaces_an_existing_destination(
    tmp_path: Path,
    occupant: str,
) -> None:
    """An empty destination directory is as protected as a populated one."""
    staged = _staged(tmp_path)
    destination = tmp_path / "products"
    if occupant == "file":
        destination.write_text("owned", encoding="utf-8")
    elif occupant == "dangling-symlink":
        destination.symlink_to(tmp_path / "absent")
    else:
        destination.mkdir()
        if occupant == "populated-directory":
            (destination / "owned.txt").write_text("owned", encoding="utf-8")

    with pytest.raises(FileExistsError):
        rename_without_replacement(staged, destination)

    assert (staged / "catalogue.fits").is_file()
    if occupant == "file":
        assert destination.read_text(encoding="utf-8") == "owned"
    elif occupant == "dangling-symlink":
        assert destination.is_symlink()
    else:
        expected = ["owned.txt"] if occupant == "populated-directory" else []
        assert sorted(path.name for path in destination.iterdir()) == expected


def test_rename_reports_a_missing_source(tmp_path: Path) -> None:
    """A missing staged bundle keeps its own filesystem error."""
    with pytest.raises(FileNotFoundError):
        rename_without_replacement(tmp_path / "absent", tmp_path / "products")


@pytest.mark.parametrize("code", (errno.ENOSYS, errno.ENOTSUP, errno.EINVAL))
def test_rename_falls_back_when_the_platform_lacks_the_operation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    code: int,
) -> None:
    """Without an atomic operation the destination is still not replaced."""

    def unsupported(_source: bytes, _destination: bytes) -> int:
        ctypes.set_errno(code)
        return -1

    monkeypatch.setattr(
        "hebog.io.filesystem._no_replace_renamer",
        lambda: unsupported,
    )
    staged = _staged(tmp_path)
    destination = tmp_path / "products"
    destination.mkdir()

    with pytest.raises(FileExistsError):
        rename_without_replacement(staged, destination)

    destination.rmdir()
    rename_without_replacement(staged, destination)

    assert (destination / "catalogue.fits").is_file()


def test_rename_propagates_an_unrelated_filesystem_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real failure is never mistaken for an unsupported operation."""

    def denied(_source: bytes, _destination: bytes) -> int:
        ctypes.set_errno(errno.EACCES)
        return -1

    monkeypatch.setattr(
        "hebog.io.filesystem._no_replace_renamer", lambda: denied
    )

    with pytest.raises(PermissionError):
        rename_without_replacement(_staged(tmp_path), tmp_path / "products")


@pytest.mark.skipif(
    os.name == "nt", reason="POSIX rename replaces an empty directory"
)
def test_plain_rename_would_replace_an_empty_destination(
    tmp_path: Path,
) -> None:
    """Record the behaviour this boundary exists to prevent."""
    staged = _staged(tmp_path)
    destination = tmp_path / "products"
    destination.mkdir()

    os.rename(staged, destination)

    assert (destination / "catalogue.fits").is_file()
