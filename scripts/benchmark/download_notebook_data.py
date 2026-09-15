#!/usr/bin/env python3
"""Download public notebook inputs, without freezing individual experiments.

Defaults to three small LoTSS workbench fields. Use --list to see optional
SDC1/Hydra inputs and archives before requesting multi-gigabyte downloads.
"""

from __future__ import annotations

import argparse
import json
import shutil
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
COMPARISON_CONFIGURATION = Path("config/comparisons/notebook-comparison.json")
_LOTSS_CUTOUT_ENDPOINT = "https://lofar-surveys.org/dr2-cutout.fits"
_FITS_BLOCK_BYTES = 2880
_WORKBENCH_IMAGES = ("lotss-survey", "lotss-3c295", "lotss-m51")


@dataclass(frozen=True)
class NotebookDownload:
    """A public image or supporting archive, with an advisory size."""

    name: str
    filename: str
    url: str
    size: str


def _download(item: dict[str, Any]) -> NotebookDownload:
    """Translate one configured LoTSS cutout or fixed public artifact."""
    cutout = item.get("lotss_cutout")
    if cutout is not None:
        query = urllib.parse.urlencode(
            {"pos": cutout["position"], "size": cutout["size_arcminutes"]}
        )
        return NotebookDownload(
            name=item["name"],
            filename=item["filename"],
            url=f"{_LOTSS_CUTOUT_ENDPOINT}?{query}",
            size="cutout service determines size",
        )
    return NotebookDownload(
        name=item["name"],
        filename=item["filename"],
        url=item["url"],
        size=f"about {item['expected_bytes'] / 1024**3:.3f} GiB",
    )


def available_downloads(repository_root: Path) -> tuple[NotebookDownload, ...]:
    """Return the configured public inputs in their listed order."""
    configuration = json.loads(
        (repository_root / COMPARISON_CONFIGURATION).read_text(
            encoding="utf-8"
        )
    )
    return tuple(_download(item) for item in configuration["downloads"])


def _check_download(path: Path, *, fits_image: bool) -> None:
    """Reject empty files and obvious FITS error pages or partial blocks."""
    size = path.stat().st_size
    if not size:
        raise ValueError(f"empty download: {path.name}")
    if fits_image:
        with path.open("rb") as handle:
            signature = handle.read(9)
        if signature != b"SIMPLE  =" or size % _FITS_BLOCK_BYTES:
            raise ValueError(
                f"not a complete FITS file: {path.name}; use --overwrite "
                "to retry an existing download"
            )


def download_image(url: str, destination: Path, *, overwrite: bool) -> None:
    """Stream one input; publish only after basic transfer checks succeed."""
    fits_image = destination.suffix.lower() == ".fits"
    if destination.exists() and not overwrite:
        _check_download(destination, fits_image=fits_image)
        print(f"Using existing {destination}", flush=True)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {destination.name} from {url}", flush=True)
    with TemporaryDirectory(
        prefix=".download-", dir=destination.parent
    ) as tmp:
        partial = Path(tmp) / destination.name
        with urllib.request.urlopen(url, timeout=120) as response:
            length = response.headers.get("Content-Length")
            with partial.open("wb") as output:
                shutil.copyfileobj(response, output, length=1024 * 1024)
        if length is not None and partial.stat().st_size != int(length):
            raise ValueError(f"incomplete download: {destination.name}")
        _check_download(partial, fits_image=fits_image)
        partial.replace(destination)
    print(
        f"Saved {destination} ({destination.stat().st_size:,} bytes)",
        flush=True,
    )


def main() -> None:
    """Download explicitly selected inputs; leave comparison results alone."""
    downloads = {item.name: item for item in available_downloads(_ROOT)}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list", action="store_true", help="List inputs and sizes"
    )
    parser.add_argument(
        "--dataset",
        action="append",
        choices=tuple(downloads),
        help="Repeat to select inputs; defaults to the three workbench fields",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=_ROOT / "benchmark-results/notebook-data",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace successfully downloaded files",
    )
    args = parser.parse_args()
    if args.list:
        for item in downloads.values():
            print(f"{item.name}: {item.filename} ({item.size})")
        return
    for name in dict.fromkeys(args.dataset or _WORKBENCH_IMAGES):
        item = downloads[name]
        download_image(
            item.url,
            args.output_directory.expanduser() / item.filename,
            overwrite=args.overwrite,
        )


if __name__ == "__main__":
    main()
