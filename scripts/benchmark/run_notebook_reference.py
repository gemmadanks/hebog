#!/usr/bin/env python3
"""Run one exploratory reference in a caller-selected container.

Uses existing scientific settings and native product adapters. Runtime hashes
are recorded, not compared with historical campaign environments.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import os
import runpy
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any

import numpy as np
from astropy.io import fits

from hebog.validation.campaign_runtime import dependency_inventory_sha256
from hebog.validation.contracts import (
    PhaseFiveExternalAegeanConfiguration,
    PhaseFiveExternalPybdsfConfiguration,
)

_ROOT = Path(__file__).resolve().parents[2]
_SETTINGS = _ROOT / "config/contracts/phase-5-external-comparison.json"
_PACKAGES = {
    "released-pybdsf": ("bdsf", "1.14.1"),
    "aegean": ("AegeanTools", "2.3.5"),
}


def runtime_identity(finder: str) -> dict[str, str]:
    """Check the release and record its actual dependency inventory."""
    package, expected = _PACKAGES[finder]
    version = importlib.metadata.version(package)
    if version != expected:
        raise ValueError(
            f"{finder} needs {package} {expected}; found {version}"
        )
    return {
        "runtime_name": package,
        "runtime_version": version,
        "dependency_inventory_sha256": dependency_inventory_sha256(),
    }


def _helpers(name: str) -> dict[str, Any]:
    return runpy.run_path(str(Path(__file__).with_name(name)))


def _settings() -> SimpleNamespace:
    """Read native options without loading campaign execution authority."""
    document = json.loads(_SETTINGS.read_text())
    return SimpleNamespace(
        pybdsf_configuration=PhaseFiveExternalPybdsfConfiguration.model_validate(
            document["pybdsf_configuration"]
        ),
        aegean_configuration=PhaseFiveExternalAegeanConfiguration.model_validate(
            document["aegean_configuration"]
        ),
    )


def _execute(
    *,
    finder: str,
    image: Path,
    staging: Path,
    ncores: int,
    public: dict[str, Any],
) -> tuple[dict[str, Path], dict[str, object]]:
    """Reuse established option translation, native readers and masks."""
    shape = np.asarray(fits.getdata(image)).squeeze().shape
    if len(shape) != 2:  # noqa: PLR2004
        raise ValueError("notebook input must contain one 2D image plane")
    adapter = public["_PublicInput"](image, shape)
    protocol = _settings()
    if finder == "released-pybdsf":
        runner = _helpers("run_phase5_external_pybdsf.py")
        configuration = runner["_configuration"](
            protocol,
            adapter,
            mode="operational",
            ncores=ncores,
        )
        artifacts = runner["_run_pybdsf"](
            importlib.import_module("bdsf"),
            adapter,
            {**configuration, "outdir": str(staging)},
            staging,
        )
    else:
        runner = _helpers("run_phase5_external_aegean.py")
        configuration = runner["_configuration"](
            protocol,
            adapter,
            mode="operational",
            table_path=staging / "catalogue.fits",
        )
        configuration["cores"] = ncores
        previous = os.environ["PATH"]
        os.environ["PATH"] = public["_install_aegean_wrapper"](staging)
        try:
            artifacts = runner["_run_aegean"](adapter, configuration, staging)
        finally:
            os.environ["PATH"] = previous
    return artifacts, runner["_configuration_identity"](configuration)


def run_reference(  # noqa: PLR0913
    *,
    image: Path,
    output: Path,
    case_id: str,
    finder: str,
    container_image_id: str,
    ncores: int,
    core: tuple[int, int, int, int] | None = None,
) -> None:
    """Publish native products and a notebook-compatible result atomically."""
    if ncores < 1:
        raise ValueError("ncores must be positive")
    if output.exists():
        raise FileExistsError(
            f"refusing to replace reference result: {output}"
        )
    header = fits.getheader(image)
    height, width = int(header["NAXIS2"]), int(header["NAXIS1"])
    if core is not None and not (
        0 <= core[0] < core[1] <= height and 0 <= core[2] < core[3] <= width
    ):
        raise ValueError("comparison core exceeds the input image")
    runtime = runtime_identity(finder)
    public = _helpers("run_phase5_public_reference_finder.py")
    input_sha256 = public["_sha256"](image)
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix=f".{output.name}.", dir=output.parent
    ) as raw:
        staging = Path(raw)
        started = time.perf_counter()
        artifacts, configuration = _execute(
            finder=finder,
            image=image,
            staging=staging,
            ncores=ncores,
            public=public,
        )
        elapsed = time.perf_counter() - started
        products = public["_normalise_products"](
            finder,
            artifacts,
            staging=staging,
            header=header,
            core=core,
        )
        if public["_sha256"](image) != input_sha256:
            raise ValueError("input image changed during reference run")
        result = {
            "schema_version": 1,
            "result_id": f"notebook-{case_id}-{finder}",
            "case_id": case_id,
            "finder_id": finder,
            "mode": "operational",
            "status": "success",
            "input_sha256": input_sha256,
            "container_image_id": container_image_id,
            **runtime,
            "configuration": configuration,
            "core_bounds_yx_half_open": list(core)
            if core is not None
            else [0, height, 0, width],
            "elapsed_seconds": elapsed,
            "artifacts": public["_artifact_manifest"](
                products, staging=staging
            ),
            "scientific_claims_authorized": False,
            "runtime_notes": (
                ["Restored Aegean 2.3.5's NumPy singular-fit alias"]
                if finder == "aegean"
                else []
            ),
        }
        public["_write_result"](staging / "result.json", result)
        staging.rename(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--finder-id", choices=tuple(_PACKAGES), required=True)
    parser.add_argument("--container-image-id", required=True)
    parser.add_argument("--ncores", type=int, default=2)
    parser.add_argument("--core", nargs=4, type=int)
    args = parser.parse_args()
    run_reference(
        image=args.input,
        output=args.output,
        case_id=args.case_id,
        finder=args.finder_id,
        container_image_id=args.container_image_id,
        ncores=args.ncores,
        core=tuple(args.core) if args.core is not None else None,
    )


if __name__ == "__main__":
    main()
