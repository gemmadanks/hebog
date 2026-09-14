#!/usr/bin/env python3
"""Run one parent-authorized compact-sentinel PyBDSF comparison."""

# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

import numpy as np
from astropy.io import fits

from hebog.validation.campaign_runtime import dependency_inventory_sha256
from hebog.validation.external_runners import canonical_sha256, file_sha256
from hebog.validation.products import (
    load_mask_plane,
    load_pybdsf_gaussian_catalogue,
)

_IMAGE_DIMENSIONS = 2
_ROOT = Path(__file__).parents[2]
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
    """Serialize one small terminal record deterministically."""
    return (
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _json_object(path: Path) -> dict[str, object]:
    """Load one required small authority object."""
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("sentinel authority must be a JSON object")
    return cast(dict[str, object], value)


def _verify_authority(
    execution_decision: Path,
    identity_review: Path,
) -> None:
    """Require the same separate one-use authority as the parent runner."""
    identity = _json_object(identity_review)
    decision = _json_object(execution_decision)
    expected = identity.get("expected_execution")
    expected_sha256 = identity.get("expected_execution_sha256")
    if (
        identity.get("status") != "frozen-non-executable"
        or canonical_sha256(expected) != expected_sha256
        or decision.get("status")
        != "authorized-for-one-compact-held-out-sentinel"
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


def _label_plane(pyrank: object) -> np.ndarray:
    """Convert PyBDSF's x/y rank plane to positive FITS y/x labels."""
    rank = np.asarray(pyrank)
    if (
        rank.ndim != _IMAGE_DIMENSIONS
        or not np.issubdtype(rank.dtype, np.integer)
        or np.any(rank < -1)
    ):
        raise ValueError("PyBDSF rank plane is invalid")
    return np.ascontiguousarray((rank + 1).T, dtype=np.int32)


def run(
    *,
    input_path: Path,
    output: Path,
    execution_decision: Path,
    identity_review: Path,
    container_digest: str,
) -> None:
    """Publish one exact Gaussian catalogue and native label plane."""
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
        catalogue_path = staging / "gaussian-catalogue.fits"
        labels_path = staging / "island-labels.fits"
        mask_path = staging / "island-mask.fits"
        processed.write_catalog(
            outfile=str(catalogue_path),
            format="fits",
            catalog_type="gaul",
            clobber=True,
            force_output=True,
        )
        if not processed.export_image(
            outfile=str(mask_path),
            clobber=True,
            img_type="island_mask",
        ):
            raise RuntimeError("PyBDSF did not export its island mask")
        labels = _label_plane(processed.pyrank)
        header = cast(fits.Header, fits.getheader(input_path))
        fits.PrimaryHDU(
            data=labels[np.newaxis, np.newaxis, :, :],
            header=header,
        ).writeto(labels_path)
        mask = load_mask_plane(mask_path)
        if np.any(mask != (labels > 0)):
            raise ValueError("PyBDSF mask and native labels disagree")
        catalogue = load_pybdsf_gaussian_catalogue(catalogue_path)
        native_islands = {int(item) - 1 for item in np.unique(labels) if item}
        if any(item.island_identifier is None for item in catalogue):
            raise ValueError("PyBDSF Gaussian catalogue lacks ownership")
        catalogue_islands = {
            int(cast(str, item.island_identifier)) for item in catalogue
        }
        if not catalogue_islands.issubset(native_islands):
            raise ValueError("PyBDSF Gaussian catalogue ownership is invalid")
        result = {
            "artifacts": {
                path.name: {
                    "bytes": path.stat().st_size,
                    "sha256": file_sha256(path),
                }
                for path in (catalogue_path, labels_path)
            },
            "catalogue_count": len(catalogue),
            "container_digest": container_digest,
            "dependency_inventory_sha256": observed_inventory,
            "input_sha256": file_sha256(input_path),
            "schema_version": 1,
            "status": "success",
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
