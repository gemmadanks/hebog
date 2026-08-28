#!/usr/bin/env python3
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
"""Run one qualitative public-data reference finder in its pinned image."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import runpy
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Literal, cast

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

from hebog.validation.campaign_runtime import dependency_inventory_sha256
from hebog.validation.contracts import PhaseFiveExternalComparisonProtocol
from hebog.validation.products import (
    CatalogueSource,
    load_aegean_catalogue,
    load_pybdsf_catalogue,
    write_comparison_catalogue,
)

_ROOT = Path(__file__).parents[2]
_AEGEAN_WRAPPER = """#!/usr/bin/env python3
import numpy as np

np.linalg.linalg = np.linalg

from AegeanTools.CLI.aegean import main

raise SystemExit(main())
"""


def _load_protocol(path: Path) -> PhaseFiveExternalComparisonProtocol:
    helpers = runpy.run_path(
        str(_ROOT / "scripts/validation/phase5_viewed_recovery_protocol.py")
    )
    return cast(
        PhaseFiveExternalComparisonProtocol,
        helpers["load_viewed_recovery_protocol"](path),
    )


def _install_aegean_wrapper(staging: Path) -> str:
    """Restore Aegean 2.3.5's NumPy singular-fit exception alias."""
    executable_directory = staging / "aegean-runtime"
    executable_directory.mkdir()
    executable = executable_directory / "aegean"
    executable.write_text(_AEGEAN_WRAPPER, encoding="utf-8")
    executable.chmod(0o755)
    return f"{executable_directory}:{os.environ['PATH']}"


FinderId = Literal["released-pybdsf", "aegean"]
CoreBounds = tuple[int, int, int, int]
_CORE_BOUND_COUNT = 4
_IMAGE_DIMENSIONS = 2


class _PublicInput:
    """Minimal read-only input seam used by the governed runner helpers."""

    def __init__(self, image_path: Path, shape_yx: tuple[int, int]) -> None:
        self._image_path = image_path
        self.input_bundle = SimpleNamespace(shape_yx=shape_yx)

    def artifact_path(self, role: str) -> Path:
        """Return the public image and reject unavailable analytic maps."""
        if role != "image":
            raise KeyError(f"public operational run has no {role} artifact")
        return self._image_path


def _parse_core(raw: str | None) -> CoreBounds | None:
    """Parse optional half-open y/x core bounds."""
    if raw is None:
        return None
    values = tuple(int(value) for value in raw.split(","))
    if len(values) != _CORE_BOUND_COUNT:
        raise ValueError("core must contain y_start,y_stop,x_start,x_stop")
    y_start, y_stop, x_start, x_stop = values
    if not (0 <= y_start < y_stop and 0 <= x_start < x_stop):
        raise ValueError("core bounds must be positive and non-empty")
    return cast(CoreBounds, values)


def _parse_args() -> argparse.Namespace:
    """Parse one isolated public reference-finder invocation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--case-id", required=True)
    parser.add_argument(
        "--finder-id",
        required=True,
        choices=("released-pybdsf", "aegean"),
    )
    parser.add_argument("--container-image-digest", required=True)
    parser.add_argument("--ncores", type=int, default=4)
    parser.add_argument("--core")
    return parser.parse_args()


def _sha256(path: Path) -> str:
    """Return one file's SHA-256 digest."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _shifted_header(
    header: fits.Header,
    core: CoreBounds | None,
) -> fits.Header:
    """Return WCS metadata for the selected local core."""
    shifted = header.copy()
    if core is not None:
        _y_start, _y_stop, x_start, _x_stop = core
        y_start = core[0]
        shifted["CRPIX1"] = float(shifted["CRPIX1"]) - x_start
        shifted["CRPIX2"] = float(shifted["CRPIX2"]) - y_start
    return shifted


def _crop_plane(
    source: Path,
    destination: Path,
    *,
    header: fits.Header,
    core: CoreBounds,
) -> None:
    """Write one native plane cropped to the governed comparison core."""
    values = np.asarray(fits.getdata(source)).squeeze()
    y_start, y_stop, x_start, x_stop = core
    cropped = values[y_start:y_stop, x_start:x_stop]
    fits.PrimaryHDU(
        data=cropped[np.newaxis, np.newaxis, :, :],
        header=_shifted_header(header, core),
    ).writeto(destination)


def _inside_core(
    sources: tuple[CatalogueSource, ...],
    *,
    header: fits.Header,
    core: CoreBounds | None,
) -> tuple[CatalogueSource, ...]:
    """Retain catalogue rows whose sky positions lie in the output core."""
    if core is None or not sources:
        return sources
    world = np.asarray(
        [
            (item.right_ascension_degrees, item.declination_degrees)
            for item in sources
        ],
        dtype=np.float64,
    )
    pixels = WCS(header, relax=True).celestial.all_world2pix(world, 0)
    y_start, y_stop, x_start, x_stop = core
    selected = (
        np.all(np.isfinite(pixels), axis=1)
        & (pixels[:, 0] >= x_start)
        & (pixels[:, 0] < x_stop)
        & (pixels[:, 1] >= y_start)
        & (pixels[:, 1] < y_stop)
    )
    return tuple(
        item
        for item, include in zip(sources, selected, strict=True)
        if include
    )


def _normalise_products(
    finder_id: FinderId,
    artifacts: dict[str, Path],
    *,
    staging: Path,
    header: fits.Header,
    core: CoreBounds | None,
) -> dict[str, Path]:
    """Publish core-comparable products while retaining native outputs."""
    output = dict(artifacts)
    if finder_id == "released-pybdsf":
        sources = load_pybdsf_catalogue(artifacts["source-catalogue-fits"])
        plane_roles = ("island-labels-fits", "island-mask-fits")
    else:
        sources = load_aegean_catalogue(
            artifacts["component-catalogue-fits"],
            artifacts["island-catalogue-fits"],
            exclude_invalid_islands=True,
        )
        plane_roles = ("support-proxy-labels-fits",)
    comparison_path = staging / "comparison_catalogue.json"
    write_comparison_catalogue(
        comparison_path,
        _inside_core(sources, header=header, core=core),
    )
    output["comparison-catalogue-json"] = comparison_path
    if core is None:
        return output
    for role in plane_roles:
        native_path = artifacts[role]
        core_path = staging / f"core_{native_path.name}"
        _crop_plane(native_path, core_path, header=header, core=core)
        output[f"native-{role}"] = native_path
        output[role] = core_path
    return output


def _artifact_manifest(
    artifacts: dict[str, Path],
    *,
    staging: Path,
) -> dict[str, dict[str, object]]:
    """Return deterministic metadata for every emitted product."""
    return {
        role: {
            "path": str(path.relative_to(staging)),
            "sha256": _sha256(path),
            "byte_size": path.stat().st_size,
        }
        for role, path in sorted(artifacts.items())
    }


def _write_result(path: Path, document: dict[str, object]) -> None:
    """Write one canonical result document."""
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _run_reference(  # noqa: PLR0913, PLR0915
    *,
    protocol_path: Path,
    image_path: Path,
    output: Path,
    case_id: str,
    finder_id: FinderId,
    container_image_digest: str,
    ncores: int,
    core: CoreBounds | None,
) -> None:
    """Run one reference and atomically publish qualitative products."""
    if output.exists():
        raise FileExistsError(f"refusing to overwrite public result: {output}")
    protocol = _load_protocol(protocol_path)
    reference = next(
        item for item in protocol.references if item.finder_id == finder_id
    )
    package_name = "bdsf" if finder_id == "released-pybdsf" else "AegeanTools"
    observed_version = importlib.metadata.version(package_name)
    if observed_version != reference.version:
        raise RuntimeError(
            f"{finder_id} version changed: expected {reference.version}, "
            f"observed {observed_version}"
        )
    if container_image_digest != reference.container_image_digest:
        raise ValueError(f"{finder_id} container digest changed")
    observed_inventory = dependency_inventory_sha256()
    if observed_inventory != reference.dependency_inventory_sha256:
        raise RuntimeError(f"{finder_id} dependency inventory changed")
    image = np.asarray(fits.getdata(image_path)).squeeze()
    if image.ndim != _IMAGE_DIMENSIONS:
        raise ValueError(
            "public comparison input must contain one image plane"
        )
    if core is not None:
        _y_start, y_stop, _x_start, x_stop = core
        if y_stop > image.shape[0] or x_stop > image.shape[1]:
            raise ValueError("comparison core exceeds the input image")
    header = cast(fits.Header, fits.getheader(image_path))
    adapter = _PublicInput(
        image_path,
        (int(image.shape[0]), int(image.shape[1])),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix=f".{output.name}.", dir=output.parent
    ) as raw:
        staging = Path(raw)
        started = time.perf_counter()
        if finder_id == "released-pybdsf":
            runner = runpy.run_path(
                str(Path(__file__).with_name("run_phase5_external_pybdsf.py"))
            )
            configuration = runner["_configuration"](
                protocol,
                adapter,
                mode="operational",
                ncores=ncores,
            )
            execution_configuration = dict(configuration)
            execution_configuration["outdir"] = str(staging)
            import bdsf  # type: ignore[import-not-found]  # noqa: PLC0415

            artifacts = runner["_run_pybdsf"](
                bdsf,
                adapter,
                execution_configuration,
                staging,
            )
            identity = runner["_configuration_identity"](configuration)
        else:
            runner = runpy.run_path(
                str(Path(__file__).with_name("run_phase5_external_aegean.py"))
            )
            configuration = runner["_configuration"](
                protocol,
                adapter,
                mode="operational",
                table_path=staging / "catalogue.fits",
            )
            original_path = os.environ["PATH"]
            os.environ["PATH"] = _install_aegean_wrapper(staging)
            try:
                artifacts = runner["_run_aegean"](
                    adapter,
                    configuration,
                    staging,
                )
            finally:
                os.environ["PATH"] = original_path
            identity = runner["_configuration_identity"](configuration)
        elapsed = time.perf_counter() - started
        normalised = _normalise_products(
            finder_id,
            artifacts,
            staging=staging,
            header=header,
            core=core,
        )
        result: dict[str, object] = {
            "schema_version": 1,
            "result_id": f"public-reference-{case_id}-{finder_id}",
            "case_id": case_id,
            "finder_id": finder_id,
            "mode": "operational",
            "status": "success",
            "input_sha256": _sha256(image_path),
            "container_image_digest": container_image_digest,
            "dependency_inventory_sha256": observed_inventory,
            "runtime_name": package_name,
            "runtime_version": observed_version,
            "configuration": identity,
            "core_bounds_yx_half_open": list(core) if core else None,
            "elapsed_seconds": elapsed,
            "artifacts": _artifact_manifest(normalised, staging=staging),
            "runtime_notes": (
                ["Restored Aegean 2.3.5's NumPy singular-fit alias"]
                if finder_id == "aegean"
                else []
            ),
            "scientific_claims_authorized": False,
        }
        _write_result(staging / "result.json", result)
        staging.rename(output)


def main() -> None:
    """Run one container-isolated qualitative public reference."""
    arguments = _parse_args()
    _run_reference(
        protocol_path=arguments.protocol,
        image_path=arguments.input,
        output=arguments.output,
        case_id=arguments.case_id,
        finder_id=arguments.finder_id,
        container_image_digest=arguments.container_image_digest,
        ncores=arguments.ncores,
        core=_parse_core(arguments.core),
    )


if __name__ == "__main__":
    main()
