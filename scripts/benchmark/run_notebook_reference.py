#!/usr/bin/env python3
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
"""Run one PyBDSF or Aegean notebook reference in its container.

The finder options come from ``config/comparisons/notebook-comparison.json``.
Native catalogues and support planes are retained next to normalized
comparison products. Runtime versions and dependency inventories are recorded,
not compared with historical campaign environments.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
import subprocess
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Literal, cast

import numpy as np
from astropy.io import fits
from astropy.table import Table
from astropy.wcs import WCS

from hebog.validation.campaign_runtime import dependency_inventory_sha256
from hebog.validation.products import (
    CatalogueSource,
    aegean_support_label_plane,
    load_aegean_catalogue,
    load_mask_plane,
    load_pybdsf_catalogue,
    load_pybdsf_gaussian_catalogue,
    write_comparison_catalogue,
)

_ROOT = Path(__file__).resolve().parents[2]
_CONFIGURATION = _ROOT / "config/comparisons/notebook-comparison.json"
_FINDER_IDS = ("released-pybdsf", "aegean")
_IMAGE_DIMENSIONS = 2
_AEGEAN_WRAPPER = """#!/usr/bin/env python3
import numpy as np

np.linalg.linalg = np.linalg

from AegeanTools.CLI.aegean import main

raise SystemExit(main())
"""

FinderId = Literal["released-pybdsf", "aegean"]
CoreBounds = tuple[int, int, int, int]


def reference_settings() -> dict[str, Any]:
    """Return the configured package pin and options for each finder."""
    document = json.loads(_CONFIGURATION.read_text(encoding="utf-8"))
    return cast(dict[str, Any], document["reference_finders"])


def runtime_identity(finder: str) -> dict[str, str]:
    """Check the release and record its actual dependency inventory."""
    settings = reference_settings()[finder]
    package, expected = settings["package"], settings["version"]
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


def _sha256(path: Path) -> str:
    """Return one file's SHA-256 digest."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def pybdsf_configuration(ncores: int) -> dict[str, object]:
    """Return PyBDSF ``process_image`` options for one operational run."""
    if ncores < 1:
        raise ValueError("PyBDSF ncores must be positive")
    options = dict(
        reference_settings()["released-pybdsf"]["process_image_options"]
    )
    for name in ("rms_box", "rms_box_bright"):
        options[name] = tuple(options[name])
    return dict(sorted({**options, "ncores": ncores, "quiet": True}.items()))


def aegean_configuration(
    *, table_path: Path, ncores: int
) -> dict[str, object]:
    """Return the covariance-enabled blind Aegean configuration."""
    settings = reference_settings()["aegean"]
    return {
        "background": None,
        "cores": ncores,
        "covariance": True,
        "find": True,
        "floodclip": settings["floodclip_sigma"],
        "island": True,
        "noise": None,
        "seedclip": settings["seedclip_sigma"],
        "table": str(table_path),
    }


def aegean_command(
    configuration: dict[str, object],
    *,
    image_path: Path,
) -> tuple[str, ...]:
    """Translate the configuration without relying on CLI defaults."""
    return (
        "aegean",
        "--find",
        "--cores",
        str(configuration["cores"]),
        "--seedclip",
        str(configuration["seedclip"]),
        "--floodclip",
        str(configuration["floodclip"]),
        "--island",
        "--table",
        str(configuration["table"]),
        str(image_path),
    )


def configuration_identity(
    finder: str,
    configuration: dict[str, object],
) -> dict[str, object]:
    """Remove host paths from a recorded finder configuration."""
    identity = dict(configuration)
    if finder == "aegean":
        identity["table"] = "catalogue.fits"
    return identity


def pybdsf_label_plane(pyrank: object) -> np.ndarray:
    """Transform PyBDSF's internal x/y ranks to a FITS y/x label plane."""
    rank = np.asarray(pyrank)
    if rank.ndim != _IMAGE_DIMENSIONS or not np.issubdtype(
        rank.dtype, np.integer
    ):
        raise ValueError(
            "PyBDSF pyrank must be a two-dimensional integer array"
        )
    if np.any(rank < -1):
        raise ValueError("PyBDSF pyrank contains an invalid negative rank")
    return np.ascontiguousarray((rank + 1).T, dtype=np.int32)


def validate_pybdsf_island_identities(
    catalogue: tuple[Any, ...],
    gaussian_catalogue: tuple[Any, ...],
    labels: np.ndarray,
) -> None:
    """Validate catalogue subsets while retaining fitless native islands."""
    if any(
        source.island_identifier is None
        for source in (*catalogue, *gaussian_catalogue)
    ):
        raise ValueError("PyBDSF catalogue row is missing an island identity")
    island_ids = {int(item) - 1 for item in np.unique(labels) if item > 0}
    source_ids = {int(source.island_identifier) for source in catalogue}
    if not source_ids.issubset(island_ids):
        raise ValueError("PyBDSF catalogue and island labels disagree")
    gaussian_ids = {
        int(source.island_identifier) for source in gaussian_catalogue
    }
    if not gaussian_ids.issubset(source_ids):
        raise ValueError("PyBDSF Gaussian and source catalogues disagree")


def run_pybdsf(
    bdsf_module: Any,
    image_path: Path,
    configuration: dict[str, object],
    staging: Path,
) -> dict[str, Path]:
    """Run PyBDSF and retain native catalogue, mask, and island labels."""
    catalogue_path = staging / "source_catalog.fits"
    gaussian_path = staging / "gaussian_catalog.fits"
    mask_path = staging / "island_mask.fits"
    label_path = staging / "island_labels.fits"
    processed = bdsf_module.process_image(str(image_path), **configuration)
    for path, catalogue_type in (
        (catalogue_path, "srl"),
        (gaussian_path, "gaul"),
    ):
        processed.write_catalog(
            outfile=str(path),
            format="fits",
            catalog_type=catalogue_type,
            clobber=True,
            force_output=True,
        )
    if not processed.export_image(
        outfile=str(mask_path),
        clobber=True,
        img_type="island_mask",
    ):
        raise RuntimeError("PyBDSF did not export its island mask")
    input_header = cast(fits.Header, fits.getheader(image_path))
    labels = pybdsf_label_plane(processed.pyrank)
    fits.PrimaryHDU(
        data=labels[np.newaxis, np.newaxis, :, :],
        header=input_header,
    ).writeto(label_path)
    catalogue = load_pybdsf_catalogue(catalogue_path)
    gaussian_catalogue = load_pybdsf_gaussian_catalogue(gaussian_path)
    mask = load_mask_plane(mask_path)
    if np.any(mask != (labels > 0)):
        raise ValueError("PyBDSF island mask and labels disagree")
    validate_pybdsf_island_identities(catalogue, gaussian_catalogue, labels)
    return {
        "gaussian-catalogue-fits": gaussian_path,
        "island-labels-fits": label_path,
        "island-mask-fits": mask_path,
        "source-catalogue-fits": catalogue_path,
    }


def write_empty_aegean_catalogues(
    component_path: Path,
    island_path: Path,
) -> None:
    """Represent a successful zero-source run when Aegean writes no table."""
    component_names = (
        "island",
        "source",
        "ra",
        "dec",
        "peak_flux",
        "err_peak_flux",
        "int_flux",
        "err_int_flux",
        "a",
        "err_a",
        "b",
        "err_b",
        "pa",
        "err_pa",
        "flags",
    )
    Table(
        names=component_names,
        dtype=(int, int, *([float] * 12), int),
    ).write(component_path)
    Table(
        names=(
            "island",
            "components",
            "ra",
            "dec",
            "peak_flux",
            "int_flux",
            "err_int_flux",
        ),
        dtype=(int, int, float, float, float, float, float),
    ).write(island_path)


def run_aegean(
    image_path: Path,
    configuration: dict[str, object],
    staging: Path,
) -> dict[str, Path]:
    """Run Aegean and retain native catalogues plus its declared proxy."""
    completed = subprocess.run(
        aegean_command(configuration, image_path=image_path),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Aegean failed with exit code "
            f"{completed.returncode}: {completed.stderr.strip()}"
        )
    table_path = Path(str(configuration["table"]))
    component_path = table_path.with_name(f"{table_path.stem}_comp.fits")
    island_path = table_path.with_name(f"{table_path.stem}_isle.fits")
    if not component_path.exists() and not island_path.exists():
        write_empty_aegean_catalogues(component_path, island_path)
    elif not component_path.exists() or not island_path.exists():
        raise RuntimeError("Aegean wrote only one of its paired catalogues")
    island_table = fits.getdata(island_path, ext=1)
    component_table = fits.getdata(component_path, ext=1)
    invalid_islands = tuple(
        sorted(
            int(row["island"])
            for row in island_table
            if not np.isfinite(float(row["int_flux"]))
            or float(row["int_flux"]) <= 0.0
        )
    )
    invalid_island_set = set(invalid_islands)
    excluded_component_count = sum(
        int(row["island"]) in invalid_island_set for row in component_table
    )
    sources = load_aegean_catalogue(
        component_path,
        island_path,
        exclude_invalid_islands=True,
    )
    exclusions_path = staging / "catalogue_exclusions.json"
    exclusions_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "policy": (
                    "exclude-islands-with-nonfinite-or-nonpositive-"
                    "integrated-flux"
                ),
                "excluded_island_count": len(invalid_islands),
                "excluded_component_count": excluded_component_count,
                "excluded_island_identifiers": list(invalid_islands),
                "retained_island_count": len(island_table)
                - len(invalid_islands),
                "retained_component_count": len(component_table)
                - excluded_component_count,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    input_data = np.asarray(fits.getdata(image_path)).squeeze()
    if input_data.ndim != _IMAGE_DIMENSIONS:
        raise ValueError("Aegean input must contain one image plane")
    input_header = cast(fits.Header, fits.getheader(image_path))
    labels, _ = aegean_support_label_plane(
        sources,
        input_header,
        shape_yx=(int(input_data.shape[0]), int(input_data.shape[1])),
    )
    support_path = staging / "support_proxy_labels.fits"
    fits.PrimaryHDU(
        data=labels[np.newaxis, np.newaxis, :, :],
        header=input_header,
    ).writeto(support_path)
    return {
        "catalogue-exclusions-json": exclusions_path,
        "component-catalogue-fits": component_path,
        "island-catalogue-fits": island_path,
        "support-proxy-labels-fits": support_path,
    }


def _install_aegean_wrapper(staging: Path) -> str:
    """Restore Aegean 2.3.5's NumPy singular-fit exception alias."""
    executable_directory = staging / "aegean-runtime"
    executable_directory.mkdir()
    executable = executable_directory / "aegean"
    executable.write_text(_AEGEAN_WRAPPER, encoding="utf-8")
    executable.chmod(0o755)
    return f"{executable_directory}:{os.environ['PATH']}"


def _shifted_header(
    header: fits.Header,
    core: CoreBounds | None,
) -> fits.Header:
    """Return WCS metadata for the selected local core."""
    shifted = header.copy()
    if core is not None:
        y_start, _y_stop, x_start, _x_stop = core
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
    """Write one native plane cropped to the comparison core."""
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


def normalise_products(
    finder: str,
    artifacts: dict[str, Path],
    *,
    staging: Path,
    header: fits.Header,
    core: CoreBounds | None,
) -> dict[str, Path]:
    """Publish core-comparable products while retaining native outputs."""
    output = dict(artifacts)
    if finder == "released-pybdsf":
        sources = load_pybdsf_catalogue(artifacts["source-catalogue-fits"])
        plane_roles: tuple[str, ...] = (
            "island-labels-fits",
            "island-mask-fits",
        )
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


def _execute(
    *,
    finder: str,
    image: Path,
    staging: Path,
    ncores: int,
) -> tuple[dict[str, Path], dict[str, object]]:
    """Run one native finder and return its artifacts and options."""
    shape = np.asarray(fits.getdata(image)).squeeze().shape
    if len(shape) != _IMAGE_DIMENSIONS:
        raise ValueError("notebook input must contain one 2D image plane")
    if finder == "released-pybdsf":
        configuration = pybdsf_configuration(ncores)
        artifacts = run_pybdsf(
            importlib.import_module("bdsf"),
            image,
            {**configuration, "outdir": str(staging)},
            staging,
        )
    else:
        configuration = aegean_configuration(
            table_path=staging / "catalogue.fits", ncores=ncores
        )
        previous = os.environ["PATH"]
        os.environ["PATH"] = _install_aegean_wrapper(staging)
        try:
            artifacts = run_aegean(image, configuration, staging)
        finally:
            os.environ["PATH"] = previous
    return artifacts, configuration_identity(finder, configuration)


def run_reference(  # noqa: PLR0913
    *,
    image: Path,
    output: Path,
    case_id: str,
    finder: str,
    container_image_id: str,
    ncores: int,
    core: CoreBounds | None = None,
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
    input_sha256 = _sha256(image)
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
        )
        elapsed = time.perf_counter() - started
        products = normalise_products(
            finder,
            artifacts,
            staging=staging,
            header=header,
            core=core,
        )
        if _sha256(image) != input_sha256:
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
            "artifacts": _artifact_manifest(products, staging=staging),
            "scientific_claims_authorized": False,
            "runtime_notes": (
                ["Restored Aegean 2.3.5's NumPy singular-fit alias"]
                if finder == "aegean"
                else []
            ),
        }
        (staging / "result.json").write_text(
            json.dumps(result, indent=2, sort_keys=True, allow_nan=False)
            + "\n",
            encoding="utf-8",
        )
        staging.rename(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--finder-id", choices=_FINDER_IDS, required=True)
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
