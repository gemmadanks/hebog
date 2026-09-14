#!/usr/bin/env python3
"""Run one parent-authorized source-union sentinel PyBDSF comparison."""

# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import argparse
import importlib.metadata
import json
import sys
from math import cos, log, radians, sin, sqrt
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast

import numpy as np
import numpy.typing as npt
from astropy.io import fits
from astropy.wcs import WCS

from hebog.algorithms.astrometry import (
    local_tangent_plane_transform_from_wcs,
)
from hebog.validation.campaign_runtime import dependency_inventory_sha256
from hebog.validation.external_runners import canonical_sha256, file_sha256
from hebog.validation.products import load_mask_plane

_ROOT = Path(__file__).parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.validation.compact_sentinel_source_unions import (  # noqa: E402
    PyBdsfGaussianRow,
    PyBdsfSourceRow,
    SourceUnionProjection,
    derive_pybdsf_source_model_dominance,
)

_IMAGE_DIMENSIONS = 2
_FWHM_PER_SIGMA = 2.0 * sqrt(2.0 * log(2.0))
_VERSION = "1.14.1"
_INVENTORY_SHA256 = (
    "8211043e9fca55d706d1e890e2bf0b630e228a854db0949258c498506975669f"
)
_CONTAINER_DIGEST = (
    "sha256:5310afe78c8fc09ed99ddee1c6978e5e32181b69f1d22432a02ef6e3a6761198"
)
_AUTHORIZATION = {
    "another_replay": False,
    "current_hebog_execution": True,
    "cutover": False,
    "existing_dask_comparison": True,
    "held_out_execution": True,
    "optimization": False,
    "release": False,
    "released_pybdsf_execution": True,
    "rescoring": False,
    "tuning": False,
    "viewed_data_execution": False,
}
_CONFIGURATION: dict[str, object] = {
    "adaptive_rms_box": True,
    "adaptive_thresh": 75.0,
    "atrous_bdsm_do": True,
    "atrous_do": True,
    "atrous_jmax": 3,
    "atrous_lpf": "b3",
    "atrous_orig_isl": False,
    "atrous_sum": True,
    "mean_map": "zero",
    "ncores": 1,
    "quiet": True,
    "rms_box": (150, 50),
    "rms_box_bright": (35, 7),
    "rms_map": True,
    "thresh": "hard",
    "thresh_isl": 3.0,
    "thresh_pix": 5.0,
}


def _canonical_bytes(value: object) -> bytes:
    """Serialize one small record deterministically."""
    return (
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _json_object(path: Path) -> dict[str, object]:
    """Load one required authority object."""
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("sentinel authority must be a JSON object")
    return cast(dict[str, object], value)


def _verify_authority(execution_decision: Path, identity_review: Path) -> None:
    """Require the successor runner's exact separate one-use authority."""
    identity = _json_object(identity_review)
    decision = _json_object(execution_decision)
    expected = identity.get("expected_execution")
    expected_sha256 = identity.get("expected_execution_sha256")
    if (
        identity.get("status") != "frozen-non-executable"
        or canonical_sha256(expected) != expected_sha256
        or decision.get("status")
        != "authorized-for-one-compact-held-out-source-union-sentinel"
        or decision.get("authorization") != _AUTHORIZATION
        or decision.get("one_use") is not True
        or decision.get("expected_execution_sha256") != expected_sha256
        or decision.get("identity_review")
        != {
            "path": identity_review.relative_to(_ROOT).as_posix(),
            "sha256": file_sha256(identity_review),
        }
    ):
        raise PermissionError("exact execution decision is required")


def _label_plane(pyrank: object) -> npt.NDArray[np.int32]:
    """Convert PyBDSF's x/y rank plane to positive FITS y/x labels."""
    rank = np.asarray(pyrank)
    if (
        rank.ndim != _IMAGE_DIMENSIONS
        or not np.issubdtype(rank.dtype, np.integer)
        or np.any(rank < -1)
    ):
        raise ValueError("PyBDSF rank plane is invalid")
    return np.ascontiguousarray((rank + 1).T, dtype=np.int32)


def _required_columns(table: np.ndarray, names: set[str]) -> None:
    """Fail closed unless a native catalogue exposes every bound column."""
    missing = names.difference(table.dtype.names or ())
    if missing:
        raise ValueError(
            "PyBDSF source-union catalogue misses columns: "
            + ", ".join(sorted(missing))
        )


def _pixel_centre(row: np.void, celestial: WCS) -> tuple[float, float]:
    """Convert one native sky position to zero-based pixel coordinates."""
    value = celestial.all_world2pix(
        [[float(row["RA"]), float(row["DEC"])]], 0
    )[0]
    return float(value[0]), float(value[1])


def _pixel_covariance(
    row: np.void, celestial: WCS, centre_xy: tuple[float, float]
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Transform a PyBDSF east-of-north fitted ellipse into pixel space."""
    angle = radians(float(row["PA"]))
    major = np.asarray((sin(angle), cos(angle)), dtype=np.float64)
    minor = np.asarray((cos(angle), -sin(angle)), dtype=np.float64)
    major_sigma = float(row["Maj"]) / _FWHM_PER_SIGMA
    minor_sigma = float(row["Min"]) / _FWHM_PER_SIGMA
    sky = major_sigma**2 * np.outer(major, major) + minor_sigma**2 * np.outer(
        minor, minor
    )
    transform = local_tangent_plane_transform_from_wcs(celestial, centre_xy)
    inverse = np.linalg.inv(
        np.asarray(transform.jacobian_degrees_per_pixel, dtype=np.float64)
    )
    pixel = inverse @ sky @ inverse.T
    pixel = 0.5 * (pixel + pixel.T)
    return (
        (float(pixel[0, 0]), float(pixel[0, 1])),
        (float(pixel[1, 0]), float(pixel[1, 1])),
    )


def projection_from_catalogue_tables(
    *,
    source_table: np.ndarray,
    gaussian_table: np.ndarray,
    native_island_labels: npt.ArrayLike,
    header: fits.Header,
) -> SourceUnionProjection:
    """Derive exact source unions from native ``srl`` and ``gaul`` rows."""
    if source_table.size == 0 and gaussian_table.size == 0:
        return derive_pybdsf_source_model_dominance(
            source_rows=(),
            gaussian_rows=(),
            native_island_labels=native_island_labels,
        )
    _required_columns(
        source_table,
        {"Isl_id", "Source_id", "N_Gaus", "RA", "DEC", "Total_flux"},
    )
    _required_columns(
        gaussian_table,
        {
            "Gaus_id",
            "Isl_id",
            "Source_id",
            "RA",
            "DEC",
            "Total_flux",
            "Peak_flux",
            "Maj",
            "Min",
            "PA",
        },
    )
    celestial = WCS(header, relax=True).celestial
    sources = tuple(
        PyBdsfSourceRow(
            island_id=int(row["Isl_id"]),
            source_id=int(row["Source_id"]),
            centre_xy=_pixel_centre(row, celestial),
            integrated_flux_jy=float(row["Total_flux"]),
            gaussian_count=int(row["N_Gaus"]),
        )
        for row in source_table
    )
    gaussians: list[PyBdsfGaussianRow] = []
    for row in gaussian_table:
        centre = _pixel_centre(row, celestial)
        gaussians.append(
            PyBdsfGaussianRow(
                identifier=(
                    f"pybdsf-island-{int(row['Isl_id'])}-source-"
                    f"{int(row['Source_id'])}-gaussian-"
                    f"{int(row['Gaus_id'])}"
                ),
                island_id=int(row["Isl_id"]),
                source_id=int(row["Source_id"]),
                centre_xy=centre,
                integrated_flux_jy=float(row["Total_flux"]),
                peak_flux_jy_per_beam=float(row["Peak_flux"]),
                covariance_pixels_squared=_pixel_covariance(
                    row, celestial, centre
                ),
            )
        )
    return derive_pybdsf_source_model_dominance(
        source_rows=sources,
        gaussian_rows=tuple(gaussians),
        native_island_labels=native_island_labels,
    )


def _projection_document(projection: SourceUnionProjection) -> dict[str, Any]:
    """Return a finite array-free description of the child projection."""
    return {
        "components": [
            {
                "centre_xy": list(item.centre_xy),
                "identifier": item.identifier,
                "integrated_flux_jy": item.integrated_flux_jy,
                "native_support_label": item.native_support_label,
                "source_identifier": item.source_identifier,
            }
            for item in projection.components
        ],
        "finder_id": projection.finder_id,
        "native_topology_domain": projection.native_topology_domain,
        "source_union_derivation": projection.source_union_derivation,
        "sources": [
            {
                "centre_xy": list(item.centre_xy),
                "identifier": item.identifier,
                "integrated_flux_jy": item.integrated_flux_jy,
                "member_component_ids": list(item.member_component_ids),
                "native_support_labels": list(item.native_support_labels),
            }
            for item in projection.sources
        ],
        "unowned_native_support_labels": list(
            projection.unowned_native_support_labels
        ),
    }


def run(
    *,
    input_path: Path,
    output: Path,
    execution_decision: Path,
    identity_review: Path,
    container_digest: str,
) -> None:
    """Publish native catalogues, islands, and derived source ownership."""
    _verify_authority(execution_decision, identity_review)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite PyBDSF output: {output}")
    if container_digest != _CONTAINER_DIGEST:
        raise ValueError("PyBDSF container digest changed")
    observed_version = importlib.metadata.version("bdsf")
    observed_inventory = dependency_inventory_sha256()
    if observed_version != _VERSION or observed_inventory != _INVENTORY_SHA256:
        raise RuntimeError("PyBDSF runtime identity changed")
    import bdsf  # type: ignore[import-not-found]  # noqa: PLC0415

    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix=f".{output.name}.", dir=output.parent
    ) as raw:
        staging = Path(raw) / "bundle"
        staging.mkdir()
        processed = bdsf.process_image(str(input_path), **_CONFIGURATION)
        source_path = staging / "source-catalogue.fits"
        gaussian_path = staging / "gaussian-catalogue.fits"
        labels_path = staging / "island-labels.fits"
        union_path = staging / "source-union-labels.fits"
        mask_path = Path(raw) / "island-mask.fits"
        for path, catalog_type in (
            (source_path, "srl"),
            (gaussian_path, "gaul"),
        ):
            processed.write_catalog(
                outfile=str(path),
                format="fits",
                catalog_type=catalog_type,
                clobber=True,
                force_output=True,
            )
        if not processed.export_image(
            outfile=str(mask_path), clobber=True, img_type="island_mask"
        ):
            raise RuntimeError("PyBDSF did not export its island mask")
        labels = _label_plane(processed.pyrank)
        header = cast(fits.Header, fits.getheader(input_path))
        source_table = cast(np.ndarray, fits.getdata(source_path, ext=1))
        gaussian_table = cast(np.ndarray, fits.getdata(gaussian_path, ext=1))
        projection = projection_from_catalogue_tables(
            source_table=source_table,
            gaussian_table=gaussian_table,
            native_island_labels=labels,
            header=header,
        )
        if np.any(load_mask_plane(mask_path) != (labels > 0)):
            raise ValueError("PyBDSF mask and native labels disagree")
        for path, plane in (
            (labels_path, labels),
            (union_path, projection.source_union_label_plane),
        ):
            fits.PrimaryHDU(
                data=plane[np.newaxis, np.newaxis, :, :], header=header
            ).writeto(path)
        projection_path = staging / "source-union-projection.json"
        projection_path.write_bytes(
            _canonical_bytes(_projection_document(projection))
        )
        artifacts = (
            source_path,
            gaussian_path,
            labels_path,
            union_path,
            projection_path,
        )
        result = {
            "artifacts": {
                path.name: {
                    "bytes": path.stat().st_size,
                    "sha256": file_sha256(path),
                }
                for path in artifacts
            },
            "component_count": len(projection.components),
            "container_digest": container_digest,
            "dependency_inventory_sha256": observed_inventory,
            "input_sha256": file_sha256(input_path),
            "schema_version": 2,
            "source_count": len(projection.sources),
            "status": "success",
            "unowned_native_support_count": len(
                projection.unowned_native_support_labels
            ),
            "version": observed_version,
        }
        (staging / "result.json").write_bytes(_canonical_bytes(result))
        staging.replace(output)


def _parse_args() -> argparse.Namespace:
    """Parse one internal parent-authorized invocation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--execution-decision", required=True, type=Path)
    parser.add_argument("--identity-review", required=True, type=Path)
    parser.add_argument("--container-digest", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = _parse_args()
    run(
        input_path=arguments.input,
        output=arguments.output,
        execution_decision=arguments.execution_decision,
        identity_review=arguments.identity_review,
        container_digest=arguments.container_digest,
    )
