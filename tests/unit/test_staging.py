"""Staging directories record their owner, so later runs can reclaim them.

A stopped owner is built by hand here: a record and a lock file nobody
holds are exactly what a killed run leaves, because the operating system
releases the lock when the process ends. The real kill is exercised outside
the portable lane.
"""

from __future__ import annotations

import json
import os
import socket
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from hebog.io import staging
from hebog.io.staging import (
    OWNER_LOCK_NAME,
    OWNER_RECORD_NAME,
    StagingOwner,
    reclaim_abandoned_staging,
    staging_directory,
)


def _leftover(
    output: Path,
    *,
    suffix: str = "abcd1234",
    output_name: str | None = None,
    host: str | None = None,
    holds_lock: bool = True,
) -> Path:
    """Write what a run killed while staging ``output`` leaves beside it."""
    directory = output.parent / f".{output.name}.{suffix}"
    (directory / "work").mkdir(parents=True)
    (directory / "work" / "plane.zarr").write_bytes(b"chunk")
    (directory / OWNER_LOCK_NAME).touch()
    owner = StagingOwner(
        output_name=output.name if output_name is None else output_name,
        run_id="killed",
        host=socket.gethostname() if host is None else host,
        process_id=4242,
        started_utc=datetime(2026, 10, 5, 3, 0, tzinfo=UTC),
        holds_lock=holds_lock,
    )
    (directory / OWNER_RECORD_NAME).write_text(
        owner.model_dump_json(), encoding="utf-8"
    )
    return directory


def test_staging_directory_is_hidden_beside_the_output_and_names_its_owner(
    tmp_path: Path,
) -> None:
    """The record names this output, run, host and process, under a lock."""
    output = tmp_path / "products"

    with staging_directory(output, run_id="run-7") as directory:
        owner = StagingOwner.model_validate_json(
            (directory / OWNER_RECORD_NAME).read_bytes()
        )

    assert directory.parent == tmp_path
    assert directory.name.startswith(".products.")
    assert owner.output_name == "products"
    assert owner.run_id == "run-7"
    assert owner.host == socket.gethostname()
    assert owner.process_id == os.getpid()
    assert owner.started_utc.tzinfo is not None
    assert owner.holds_lock


@pytest.mark.parametrize("failed", (False, True), ids=("returned", "raised"))
def test_staging_directory_is_removed_however_the_block_ends(
    tmp_path: Path,
    failed: bool,
) -> None:
    """Nothing is left beside the output once the owner's block ends."""
    output = tmp_path / "products"

    with (
        pytest.raises(RuntimeError) if failed else nullcontext(),
        staging_directory(output, run_id="run") as directory,
    ):
        (directory / "work").mkdir()
        if failed:
            raise RuntimeError("analysis failed")

    assert list(tmp_path.iterdir()) == []


def test_a_stopped_owner_staging_is_reclaimed_and_reported(
    tmp_path: Path,
) -> None:
    """A free lock on this host proves the owner stopped; its files go."""
    output = tmp_path / "products"
    leftover = _leftover(output)

    (found,) = reclaim_abandoned_staging(output)

    assert found.path == leftover
    assert found.status == "reclaimed"
    assert found.owner is not None and found.owner.run_id == "killed"
    assert not leftover.exists()
    assert "removed staging directory" in found.notice
    assert "run 'killed' (process 4242 on host" in found.notice
    assert "which has stopped" in found.notice


def test_an_owner_finishing_its_block_is_never_taken_for_a_stopped_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The record goes before the lock, so teardown is never reclaimed.

    A run scanning while the owner removes its directory finds the lock
    released; without the record it can prove nothing, so it reclaims
    nothing and reports no stopped run.
    """
    output = tmp_path / "products"
    found: list[staging.LeftoverStaging] = []

    class ScannedAtCleanup(TemporaryDirectory[str]):
        """Scan beside the output just as the directory is removed."""

        def cleanup(self) -> None:
            found.extend(reclaim_abandoned_staging(output))
            super().cleanup()

    monkeypatch.setattr(staging, "TemporaryDirectory", ScannedAtCleanup)

    with staging_directory(output, run_id="finishing"):
        pass

    assert [(leftover.status, leftover.owner) for leftover in found] == [
        ("unproven", None)
    ]
    assert list(tmp_path.iterdir()) == []


def test_a_staging_directory_in_use_is_left_in_place(tmp_path: Path) -> None:
    """An owner holding its lock is running, so its directory stays."""
    output = tmp_path / "products"

    with staging_directory(output, run_id="live") as directory:
        (found,) = reclaim_abandoned_staging(output)

        assert found.path == directory
        assert found.status == "unproven"
        assert found.owner is not None and found.owner.run_id == "live"
        assert (directory / OWNER_RECORD_NAME).is_file()
        assert "may still be running" in found.notice


@pytest.mark.parametrize(
    ("host", "holds_lock"),
    (("another-host", True), (None, False)),
    ids=("recorded-on-another-host", "owner-could-not-lock"),
)
def test_an_owner_this_host_cannot_prove_stopped_is_left(
    tmp_path: Path,
    host: str | None,
    holds_lock: bool,
) -> None:
    """A free lock proves nothing for another host's or an unlocked owner."""
    output = tmp_path / "products"
    leftover = _leftover(output, host=host, holds_lock=holds_lock)

    (found,) = reclaim_abandoned_staging(output)

    assert found.status == "unproven"
    assert (leftover / "work" / "plane.zarr").is_file()
    assert "remove it once that run has stopped" in found.notice


@pytest.mark.parametrize(
    "damage", ("missing", "malformed", "unknown-version", "empty")
)
def test_staging_without_a_readable_owner_record_is_left(
    tmp_path: Path,
    damage: str,
) -> None:
    """Without a record nothing can be proven, so the directory stays."""
    output = tmp_path / "products"
    leftover = _leftover(output)
    record = leftover / OWNER_RECORD_NAME
    if damage == "missing":
        record.unlink()
    elif damage == "malformed":
        record.write_text("{not json", encoding="utf-8")
    elif damage == "unknown-version":
        # Complete in every other field, so only the version is refused.
        fields = json.loads(record.read_text(encoding="utf-8"))
        record.write_text(
            json.dumps(fields | {"schema_version": 2}), encoding="utf-8"
        )
    else:
        record.write_text("", encoding="utf-8")

    (found,) = reclaim_abandoned_staging(output)

    assert found.owner is None
    assert found.status == "unproven"
    assert leftover.is_dir()
    assert "holds no owner record" in found.notice


def test_a_stopped_owner_staging_that_cannot_be_removed_is_reported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A removal that fails leaves the directory and says so."""
    output = tmp_path / "products"
    leftover = _leftover(output)

    def fail_to_remove(path: Path, *, ignore_errors: bool) -> None:
        del path, ignore_errors

    monkeypatch.setattr(staging.shutil, "rmtree", fail_to_remove)

    (found,) = reclaim_abandoned_staging(output)

    assert found.status == "unremovable"
    assert leftover.is_dir()
    assert "could not remove staging directory" in found.notice


def test_only_this_output_staging_directories_are_considered(
    tmp_path: Path,
) -> None:
    """Another output's staging, files and links are not this run's."""
    output = tmp_path / "products"
    other_output = _leftover(
        output, suffix="v2.abcd1234", output_name="products.v2"
    )
    (tmp_path / ".products.note").write_text("not staging", encoding="utf-8")
    (tmp_path / ".other.abcd1234").mkdir()
    linked = _leftover(tmp_path / "elsewhere" / "products")
    (tmp_path / ".products.link").symlink_to(linked, target_is_directory=True)
    own = _leftover(output, suffix="efgh5678")

    found = reclaim_abandoned_staging(output)

    assert [leftover.path for leftover in found] == [own]
    assert other_output.is_dir()
    assert linked.is_dir()


def test_nothing_beside_the_output_reports_nothing(tmp_path: Path) -> None:
    """A parent with no staging directories gives an empty report."""
    assert reclaim_abandoned_staging(tmp_path / "products") == ()


def test_a_filesystem_that_cannot_lock_does_not_stop_the_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The owner records that it holds no lock, so no run reclaims it."""
    output = tmp_path / "products"

    def cannot_lock(handle: object) -> None:
        del handle
        raise OSError("locks are not supported on this filesystem")

    monkeypatch.setattr(staging, "_lock", cannot_lock)

    with staging_directory(output, run_id="unlocked") as directory:
        owner = StagingOwner.model_validate_json(
            (directory / OWNER_RECORD_NAME).read_bytes()
        )

    assert not owner.holds_lock
    assert list(tmp_path.iterdir()) == []
