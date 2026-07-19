"""Materialise one bounded synthetic dataset as a radio-image FITS file."""

from __future__ import annotations

import argparse
from pathlib import Path

from hebog.validation.materialization import materialize_dataset


def _parse_args() -> argparse.Namespace:
    """Parse the explicit materialisation command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("dataset_id")
    parser.add_argument("output", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Materialise the selected dataset and print its immutable digest."""
    args = _parse_args()
    digest = materialize_dataset(
        args.manifest,
        args.dataset_id,
        args.output,
        overwrite=args.overwrite,
    )
    print(f"sha256:{digest}")


if __name__ == "__main__":
    main()
