"""Run pinned LSMTool's filter_sources on one sector, inside its container.

Runs in ``localhost/hebog-lsmtool:9bac2f7``
(``scripts/validation/containers/lsmtool``), which holds LSMTool and not
Hebog, so this script imports neither Hebog nor everybeam. It filters the
true-sky and apparent-sky models by the island mask, as Rapthor's step does
with ``filter_by_mask`` and ``keep_mask`` set and no beam Measurement Set,
clipping the mask in place, and writes each survivor's name, patch and flux
to ``summary.json`` in the output directory::

    python lsmtool_filter_worker.py MASK VERTICES TRUE_MODEL APPARENT_MODEL \
        OUTPUT_DIRECTORY
"""

from __future__ import annotations

import argparse
import json
from importlib.metadata import version
from pathlib import Path

import lsmtool
from lsmtool.filter_skymodel.bdsf import filter_sources


def _survivors(path: Path) -> list[list[object]]:
    model = lsmtool.load(str(path))
    return [
        [str(name), str(patch), float(flux)]
        for name, patch, flux in zip(
            model.getColValues("Name"),
            model.getColValues("Patch"),
            model.getColValues("I"),
            strict=True,
        )
    ]


def main() -> None:
    """Filter one sector's sky models and summarise the survivors."""
    parser = argparse.ArgumentParser(
        description=(__doc__ or "").splitlines()[0]
    )
    for name in ("mask", "vertices", "true_model", "apparent_model"):
        parser.add_argument(name, type=Path)
    parser.add_argument("output_directory", type=Path)
    arguments = parser.parse_args()
    arguments.output_directory.mkdir(parents=True, exist_ok=True)
    true_sky = arguments.output_directory / "true_sky.txt"
    apparent_sky = arguments.output_directory / "apparent_sky.txt"
    filter_sources(
        str(arguments.mask),
        str(arguments.vertices),
        str(arguments.true_model),
        str(arguments.apparent_model),
        None,
        None,
        True,
        True,
        str(true_sky),
        str(apparent_sky),
    )
    (arguments.output_directory / "summary.json").write_text(
        json.dumps(
            {
                "lsmtool": version("lsmtool"),
                "true_sky": _survivors(true_sky),
                "apparent_sky": _survivors(apparent_sky),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
