#!/usr/bin/env python3
"""Execute the two offline notebooks; check success, not identical results."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

_ROOT = Path(__file__).resolve().parents[1]
_NOTEBOOKS = ("source_finder_demo", "source_finder_internals")


def export_notebooks(output_directory: Path) -> None:
    """Run bounded synthetic demonstrations and retain their HTML exports."""
    output_directory.mkdir(parents=True, exist_ok=True)
    for name in _NOTEBOOKS:
        print(f"Executing {name}", flush=True)
        subprocess.run(
            [
                sys.executable,
                "-m",
                "marimo",
                "export",
                "html",
                str(_ROOT / "notebooks" / f"{name}.py"),
                "--output",
                str(output_directory / f"{name}.html"),
                "--force",
            ],
            cwd=_ROOT,
            env={**os.environ, "MPLBACKEND": "Agg"},
            check=True,
            timeout=180,
        )


def main() -> None:
    """Optionally preserve exports for visual inspection."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path)
    args = parser.parse_args()
    if args.output_directory is not None:
        export_notebooks(args.output_directory.resolve())
    else:
        with TemporaryDirectory(prefix="hebog-notebooks-") as directory:
            export_notebooks(Path(directory))


if __name__ == "__main__":
    main()
