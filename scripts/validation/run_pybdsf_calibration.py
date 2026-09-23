"""Run PyBDSF with the Rapthor profile on the calibration images.

Runs inside the reference-finder container. Each image is copied into its
own writable case directory before processing, because PyBDSF writes its
log next to the input and the repository is mounted read-only.
"""

import argparse
import importlib.metadata
import json
import shutil
import time
from pathlib import Path

import bdsf

# The pinned-master / released profile from
# config/comparisons/notebook-comparison.json (thresholds 5/3, as Hebog ran).
OPTIONS = {
    "adaptive_rms_box": True,
    "adaptive_thresh": 75.0,
    "atrous_bdsm_do": True,
    "atrous_do": True,
    "atrous_jmax": 3,
    "atrous_lpf": "b3",
    "atrous_orig_isl": False,
    "atrous_sum": True,
    "mean_map": "zero",
    "rms_box": (150, 50),
    "rms_box_bright": (35, 7),
    "rms_map": True,
    "thresh": "hard",
    "thresh_isl": 3.0,
    "thresh_pix": 5.0,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--ncores", type=int, default=4)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    version = importlib.metadata.version("bdsf")
    for image in sorted(args.input_dir.glob("calibration-*.fits")):
        case = args.output_dir / image.stem
        if (case / "run.json").exists():
            print(f"{image.name}: cached", flush=True)
            continue
        case.mkdir(exist_ok=True)
        local_image = case / image.name
        shutil.copyfile(image, local_image)
        started = time.perf_counter()
        processed = bdsf.process_image(
            str(local_image), ncores=args.ncores, quiet=True, **OPTIONS
        )
        for name, catalogue_type in (
            ("source_catalog.fits", "srl"),
            ("gaussian_catalog.fits", "gaul"),
        ):
            processed.write_catalog(
                outfile=str(case / name),
                format="fits",
                catalog_type=catalogue_type,
                clobber=True,
                force_output=True,
            )
        wall = time.perf_counter() - started
        (case / "run.json").write_text(
            json.dumps(
                {
                    "bdsf_version": version,
                    "image": image.name,
                    "options": {
                        key: list(value) if isinstance(value, tuple) else value
                        for key, value in OPTIONS.items()
                    },
                    "ncores": args.ncores,
                    "wall_seconds": wall,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        print(f"{image.name}: {wall:.1f} s ({version})", flush=True)


if __name__ == "__main__":
    main()
