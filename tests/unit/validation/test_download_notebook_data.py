"""Offline tests for the interactive notebook image downloader."""

from __future__ import annotations

import io
import runpy
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from astropy.io import fits  # pyright: ignore[reportMissingTypeStubs]

_ROOT = Path(__file__).parents[3]
_SCRIPT = _ROOT / "scripts/benchmark/download_notebook_data.py"


def _image_bytes() -> bytes:
    stream = io.BytesIO()
    fits.PrimaryHDU(np.ones((3, 4))).writeto(stream)  # pyright: ignore[reportUnknownMemberType]
    return stream.getvalue()


@pytest.fixture
def downloader() -> dict[str, Any]:
    return runpy.run_path(str(_SCRIPT))


class _Response(io.BytesIO):
    def __init__(self, payload: bytes, *, declared_size: int | None) -> None:
        super().__init__(payload)
        self.headers = (
            {}
            if declared_size is None
            else {"Content-Length": str(declared_size)}
        )


@pytest.mark.parametrize("declared", [True, False])
def test_download_and_reuse_valid_image(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    downloader: dict[str, Any],
    declared: bool,
) -> None:
    """A complete FITS transfer is reusable without a network request."""
    payload = _image_bytes()
    calls: list[str] = []

    def open_url(url: str, *, timeout: int) -> _Response:
        assert timeout > 0
        calls.append(url)
        return _Response(
            payload, declared_size=len(payload) if declared else None
        )

    monkeypatch.setattr("urllib.request.urlopen", open_url)
    destination = tmp_path / "images" / "field.fits"
    download = downloader["download_image"]
    download(
        "https://example.invalid/image.fits", destination, overwrite=False
    )
    download(
        "https://example.invalid/image.fits", destination, overwrite=False
    )
    assert destination.read_bytes() == payload
    assert calls == ["https://example.invalid/image.fits"]
    assert list(destination.parent.iterdir()) == [destination]


@pytest.mark.parametrize("failure", ["network", "html", "truncated"])
def test_failed_download_preserves_existing_image(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    downloader: dict[str, Any],
    failure: str,
) -> None:
    """An interrupted replacement never publishes a partial or error page."""
    destination = tmp_path / "field.fits"
    original = _image_bytes()
    destination.write_bytes(original)

    def open_url(_url: str, *, timeout: int) -> _Response:
        assert timeout > 0
        if failure == "network":
            raise OSError("connection lost")
        if failure == "html":
            return _Response(
                b"<html>service unavailable</html>", declared_size=None
            )
        return _Response(original, declared_size=len(original) + 2880)

    monkeypatch.setattr("urllib.request.urlopen", open_url)
    with pytest.raises((OSError, ValueError), match=r"lost|FITS|incomplete"):
        downloader["download_image"](
            "https://example.invalid/image.fits", destination, overwrite=True
        )
    assert destination.read_bytes() == original
    assert list(tmp_path.iterdir()) == [destination]


def test_rejects_incomplete_existing_image(
    tmp_path: Path, downloader: dict[str, Any]
) -> None:
    """A previous broken local file is not treated as a successful download."""
    destination = tmp_path / "bad.fits"
    destination.write_bytes(b"SIMPLE  =")
    with pytest.raises(ValueError, match="FITS"):
        downloader["download_image"](
            "https://example.invalid/image.fits", destination, overwrite=False
        )


def test_empty_archive_is_not_published(
    tmp_path: Path,
    downloader: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def open_url(_url: str, *, timeout: int) -> _Response:
        assert timeout > 0
        return _Response(b"", declared_size=0)

    monkeypatch.setattr("urllib.request.urlopen", open_url)
    with pytest.raises(ValueError, match="empty download"):
        downloader["download_image"](
            "https://example.invalid/archive.tgz",
            tmp_path / "archive.tgz",
            overwrite=False,
        )
    assert list(tmp_path.iterdir()) == []


def test_successful_archive_replacement(
    tmp_path: Path,
    downloader: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "archive.tgz"
    destination.write_bytes(b"previous archive")

    def open_url(_url: str, *, timeout: int) -> _Response:
        assert timeout > 0
        return _Response(b"new archive", declared_size=11)

    monkeypatch.setattr("urllib.request.urlopen", open_url)
    downloader["download_image"](
        "https://example.invalid/archive.tgz", destination, overwrite=True
    )
    assert destination.read_bytes() == b"new archive"


def test_list_never_downloads(
    downloader: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def unexpected(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("listing inputs must not download anything")

    monkeypatch.setitem(
        downloader["main"].__globals__, "download_image", unexpected
    )
    monkeypatch.setattr("sys.argv", [str(_SCRIPT), "--list"])
    downloader["main"]()
    listed = capsys.readouterr().out
    assert "sdc1-image:" in listed
    assert "hydra-archive:" in listed
    assert "lotss-m51:" in listed


@pytest.mark.parametrize("explicit", [False, True])
def test_cli_defaults_are_small_and_explicit_inputs_are_deduplicated(
    tmp_path: Path,
    downloader: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    explicit: bool,
) -> None:
    received: list[tuple[Path, bool]] = []

    def download(_url: str, destination: Path, *, overwrite: bool) -> None:
        received.append((destination, overwrite))

    monkeypatch.setitem(
        downloader["main"].__globals__, "download_image", download
    )
    args = [str(_SCRIPT), "--output-directory", str(tmp_path)]
    if explicit:
        args += [
            "--dataset",
            "sdc1-image",
            "--dataset",
            "sdc1-image",
            "--overwrite",
        ]
    monkeypatch.setattr("sys.argv", args)
    downloader["main"]()
    expected_names = (
        ["SKAMid_B2_1000h_v3.fits"]
        if explicit
        else [
            "lotss-dr2-survey-field-22arcmin.fits",
            "lotss-dr2-3c295-12arcmin.fits",
            "lotss-dr2-m51-20arcmin.fits",
        ]
    )
    assert received == [(tmp_path / name, explicit) for name in expected_names]
