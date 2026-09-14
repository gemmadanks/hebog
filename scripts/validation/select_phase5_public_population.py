#!/usr/bin/env python3
# pyright: reportArgumentType=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Create the one approved write-once Phase 5 public population."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from scipy.ndimage import map_coordinates

from hebog.validation.external_runners import file_sha256
from hebog.validation.public_comparison import (
    PublicTileAttributes,
    PublicTileTruth,
    apparent_peak_snr,
    build_public_tile_attributes,
    gaussian_fwhm_arcsec,
    select_public_tiles,
)

_ROOT = Path(__file__).parents[2]
_ACQUISITION_PATH = (
    _ROOT / "benchmark-results/phase-5/public-comparison-acquisition/"
    "acquisition.json"
)
_ACQUISITION_SHA256 = (
    "a74e60de95debcc53bdf43d4f6046a6f74befe8a85e849a5b0105f2ecb0bd0ce"
)
_SCHEMA_REVIEW_PATH = (
    _ROOT / "config/contracts/phase-5-public-comparison-schema-review.json"
)
_SCHEMA_REVIEW_SHA256 = (
    "409318f58cafe259b4347953051ef8dddcf2308f041e8145e4199f7ad281eed8"
)
_SELECTION_DECISION_PATH = (
    _ROOT
    / "config/contracts/phase-5-public-comparison-selection-decision.json"
)
_SELECTION_DECISION_SHA256 = (
    "d60fb6454ffc93c240d06e2e40888e1a4d378bc242057276f63a6d82238f565b"
)
_ADAPTER_PATH = _ROOT / "src/hebog/validation/public_comparison.py"
_DEFAULT_OUTPUT = (
    _ROOT / "benchmark-results/phase-5/public-comparison-selection"
)
_SDC1_COLUMNS = (
    "id",
    "ra_core",
    "dec_core",
    "ra_cent",
    "dec_cent",
    "flux",
    "core_frac",
    "b_maj",
    "b_min",
    "pa",
    "size",
    "class",
)
_IMAGE_SIDE = 32_768
_TILE_SIDE = 2_048
_GRID_SIDE = _IMAGE_SIDE // _TILE_SIDE
_BEAM_FWHM_ARCSEC = 0.6
_PRIMARY_BEAM_MINIMUM = 0.5
_WCS_ROW_BATCH = 256
_EXPECTED_ARTIFACT_COUNT = 7
_EXPECTED_TOTAL_BYTES = 15_053_995_875
_TABLE_DIMENSIONS = 2
_NONFINITE_CENTROID_TRUTH_IDS = (32_397_377,)


@dataclass(frozen=True, slots=True)
class _BeamContext:
    """Primary-beam array and the two coordinate transformations."""

    image_wcs: WCS
    primary_beam: np.ndarray[Any, np.dtype[np.float64]]
    primary_beam_wcs: WCS


@dataclass(frozen=True, slots=True)
class _TruthDerived:
    """Vectorized SDC1 values reused by every candidate tile."""

    in_image: np.ndarray[Any, np.dtype[np.bool_]]
    tile_x: np.ndarray[Any, np.dtype[np.int64]]
    tile_y: np.ndarray[Any, np.dtype[np.int64]]
    major_fwhm: np.ndarray[Any, np.dtype[np.float64]]
    apparent_flux: np.ndarray[Any, np.dtype[np.float64]]
    source_snr: np.ndarray[Any, np.dtype[np.float64]]
    source_beam: np.ndarray[Any, np.dtype[np.float64]]


@dataclass(frozen=True, slots=True)
class _CutoutContext:
    """Shared immutable inputs for writing selected SDC1 products."""

    source_hdu: fits.PrimaryHDU
    truth: np.ndarray[Any, np.dtype[np.float64]]
    output_directory: Path


def _json_object(path: Path) -> dict[str, Any]:
    """Load a strict JSON object."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return cast(dict[str, Any], value)


def load_selection_authorization(repository_root: Path) -> dict[str, Any]:
    """Validate the named review that permits selection but no finder run."""
    decision_path = repository_root / _SELECTION_DECISION_PATH.relative_to(
        _ROOT
    )
    if file_sha256(decision_path) != _SELECTION_DECISION_SHA256:
        raise ValueError("public selection authorization changed")
    decision = _json_object(decision_path)
    named_review = cast(dict[str, Any], decision.get("named_review"))
    if (
        decision.get("schema_version") != 1
        or decision.get("decision_id")
        != "phase-5-public-comparison-selection-decision"
        or decision.get("status") != "reviewed-before-public-selection"
        or decision.get("schema_review_sha256") != _SCHEMA_REVIEW_SHA256
        or decision.get("adapter_implementation_authorized") is not True
        or decision.get("cutout_selection_authorized") is not True
        or decision.get("finder_execution_authorized") is not False
        or decision.get("qualification_opened") is not False
        or decision.get("scientific_products_opened") is not False
        or decision.get("cutover_authorized") is not False
        or named_review
        != {
            "approved_on": "2026-08-25",
            "reviewer": "Gemma Danks",
            "scope": (
                "approved-sdc1-hydra-schema-adapters-and-one-write-once-"
                "selected-population-no-finder-execution"
            ),
        }
    ):
        raise ValueError("public selection authorization is invalid")
    schema_path = repository_root / _SCHEMA_REVIEW_PATH.relative_to(_ROOT)
    if file_sha256(schema_path) != _SCHEMA_REVIEW_SHA256:
        raise ValueError("approved public schema review changed")
    return decision


def load_acquisition(
    repository_root: Path,
    acquisition_path: Path,
) -> tuple[dict[str, Any], dict[str, Path]]:
    """Validate the terminal acquisition and every downloaded source hash."""
    if file_sha256(acquisition_path) != _ACQUISITION_SHA256:
        raise ValueError("public acquisition record changed")
    acquisition = _json_object(acquisition_path)
    if (
        acquisition.get("schema_version") != 1
        or acquisition.get("acquisition_id")
        != "phase-5-public-comparison-acquisition"
        or acquisition.get("status")
        != "complete-and-checksummed-before-science-inspection"
        or acquisition.get("artifact_count") != _EXPECTED_ARTIFACT_COUNT
        or acquisition.get("total_bytes") != _EXPECTED_TOTAL_BYTES
        or acquisition.get("finder_execution_authorized") is not False
        or acquisition.get("qualification_opened") is not False
    ):
        raise ValueError("public acquisition state is invalid")
    paths: dict[str, Path] = {}
    raw_directory = acquisition_path.parent / "raw"
    for artifact in cast(list[dict[str, Any]], acquisition["artifacts"]):
        path = raw_directory / cast(str, artifact["filename"])
        if (
            not path.is_file()
            or path.stat().st_size != artifact["byte_size"]
            or file_sha256(path) != artifact["sha256"]
        ):
            raise ValueError(f"public source identity changed: {path}")
        paths[cast(str, artifact["identifier"])] = path
    if set(paths) != {
        "deep-image",
        "hydra-archive",
        "shallow-image",
        "image",
        "official-submissions",
        "primary-beam",
        "truth-catalogue",
    }:
        raise ValueError("public source set changed")
    if repository_root != _ROOT:
        raise ValueError("public population must use the repository root")
    return acquisition, paths


def _resample_primary_beam(
    *,
    x_start: int,
    y_start: int,
    side: int,
    context: _BeamContext,
) -> tuple[float, bool]:
    """Return the exact all-pixel mean and admission validity for one tile."""
    total = 0.0
    count = 0
    height, width = context.primary_beam.shape
    x_coordinates = np.arange(x_start, x_start + side, dtype=np.float64)
    for y_batch_start in range(y_start, y_start + side, _WCS_ROW_BATCH):
        batch_height = min(
            _WCS_ROW_BATCH,
            y_start + side - y_batch_start,
        )
        x_pixels = np.broadcast_to(
            x_coordinates,
            (batch_height, side),
        )
        y_pixels = np.broadcast_to(
            np.arange(
                y_batch_start,
                y_batch_start + batch_height,
                dtype=np.float64,
            )[:, None],
            (batch_height, side),
        )
        ra_deg, dec_deg = context.image_wcs.all_pix2world(
            x_pixels,
            y_pixels,
            0,
        )
        beam_x, beam_y = context.primary_beam_wcs.all_world2pix(
            ra_deg,
            dec_deg,
            0,
        )
        in_domain = (
            (beam_x >= 0.0)
            & (beam_x <= width - 1)
            & (beam_y >= 0.0)
            & (beam_y <= height - 1)
        )
        values = map_coordinates(
            context.primary_beam,
            (beam_y, beam_x),
            order=1,
            mode="constant",
            cval=np.nan,
            prefilter=False,
        )
        if not np.all(in_domain & np.isfinite(values)):
            return float("nan"), False
        total += float(np.sum(values, dtype=np.float64))
        count += values.size
    return total / count, True


def _source_primary_beam(
    *,
    ra_deg: np.ndarray[Any, np.dtype[np.float64]],
    dec_deg: np.ndarray[Any, np.dtype[np.float64]],
    primary_beam: np.ndarray[Any, np.dtype[np.float64]],
    primary_beam_wcs: WCS,
) -> np.ndarray[Any, np.dtype[np.float64]]:
    """Bilinearly interpolate the beam at official truth centroids."""
    beam_x, beam_y = primary_beam_wcs.all_world2pix(ra_deg, dec_deg, 0)
    height, width = primary_beam.shape
    in_domain = (
        (beam_x >= 0.0)
        & (beam_x <= width - 1)
        & (beam_y >= 0.0)
        & (beam_y <= height - 1)
    )
    response = np.asarray(
        map_coordinates(
            primary_beam,
            (beam_y, beam_x),
            order=1,
            mode="constant",
            cval=np.nan,
            prefilter=False,
        ),
        dtype=np.float64,
    )
    response[~in_domain] = np.nan
    return response


def _load_truth(path: Path) -> np.ndarray[Any, np.dtype[np.float64]]:
    """Load the exact 12-column official SDC1 truth table once."""
    truth = np.loadtxt(path, dtype=np.float64)
    if truth.ndim != _TABLE_DIMENSIONS or truth.shape[1] != len(_SDC1_COLUMNS):
        raise ValueError("SDC1 truth table shape changed")
    centroid_is_finite = np.isfinite(truth[:, 3]) & np.isfinite(truth[:, 4])
    excluded_ids = tuple(
        int(identifier) for identifier in truth[~centroid_is_finite, 0]
    )
    if excluded_ids != _NONFINITE_CENTROID_TRUTH_IDS:
        raise ValueError("SDC1 non-finite centroid population changed")
    values_outside_centroids = np.concatenate(
        (truth[:, :3], truth[:, 5:]),
        axis=1,
    )
    if not np.all(np.isfinite(values_outside_centroids)):
        raise ValueError("SDC1 truth contains an unsupported non-finite value")
    if len(np.unique(truth[:, 0])) != len(truth):
        raise ValueError("SDC1 truth identifiers are not unique")
    return truth


def _tile_attribute_record(tile: PublicTileAttributes) -> dict[str, object]:
    """Serialize a tile without non-standard JSON infinity values."""
    record = asdict(tile)
    if np.isinf(tile.closest_pair_beams):
        record["closest_pair_beams"] = "infinity"
    return record


def _wcs_record(header: fits.Header) -> dict[str, object]:
    """Record the stable two-dimensional celestial WCS and beam."""
    keys = (
        "CTYPE1",
        "CTYPE2",
        "CUNIT1",
        "CUNIT2",
        "CRPIX1",
        "CRPIX2",
        "CRVAL1",
        "CRVAL2",
        "CDELT1",
        "CDELT2",
        "BMAJ",
        "BMIN",
        "BPA",
        "BUNIT",
    )
    return {key.lower(): header.get(key) for key in keys}


def _write_cutout(
    *,
    context: _CutoutContext,
    truth_indices: np.ndarray[Any, np.dtype[np.int64]],
    tile: PublicTileAttributes,
    stratum: str,
    ordinal: int,
) -> dict[str, object]:
    """Write one selected FITS core and its exact truth subset."""
    stem = f"{ordinal:02d}-{stratum}-{tile.tile_id}"
    image_path = context.output_directory / f"{stem}.fits"
    truth_path = context.output_directory / f"{stem}-truth.txt"
    source_data = context.source_hdu.data
    if source_data is None:
        raise ValueError("SDC1 image has no primary data")
    cutout = np.asarray(
        source_data[
            ...,
            tile.y_start : tile.y_start + _TILE_SIDE,
            tile.x_start : tile.x_start + _TILE_SIDE,
        ]
    )
    header = context.source_hdu.header.copy()
    header["CRPIX1"] = float(header["CRPIX1"]) - tile.x_start
    header["CRPIX2"] = float(header["CRPIX2"]) - tile.y_start
    for stale_key in ("CHECKSUM", "DATASUM", "BLANK"):
        header.remove(stale_key, ignore_missing=True)
    fits.PrimaryHDU(data=cutout, header=header).writeto(
        image_path,
        checksum=True,
        output_verify="exception",
    )
    selected_truth = context.truth[truth_indices]
    np.savetxt(
        truth_path,
        selected_truth,
        fmt=(
            "%d",
            "%.17g",
            "%.17g",
            "%.17g",
            "%.17g",
            "%.17g",
            "%.17g",
            "%.17g",
            "%.17g",
            "%.17g",
            "%d",
            "%d",
        ),
        header=" ".join(_SDC1_COLUMNS),
    )
    return {
        "ordinal": ordinal,
        "stratum": stratum,
        "tile": _tile_attribute_record(tile),
        "bounds_xy_half_open": [
            tile.x_start,
            tile.x_start + _TILE_SIDE,
            tile.y_start,
            tile.y_start + _TILE_SIDE,
        ],
        "image": {
            "path": image_path.name,
            "byte_size": image_path.stat().st_size,
            "sha256": file_sha256(image_path),
            "shape": list(cutout.shape),
            "wcs_and_beam": _wcs_record(header),
        },
        "truth": {
            "path": truth_path.name,
            "byte_size": truth_path.stat().st_size,
            "sha256": file_sha256(truth_path),
            "row_count": len(selected_truth),
            "membership_ids": list(tile.truth_ids),
        },
    }


def _artifact_bindings(acquisition: dict[str, Any]) -> dict[str, object]:
    """Retain exact source identities without copying raw public products."""
    return {
        cast(str, artifact["identifier"]): {
            "filename": artifact["filename"],
            "byte_size": artifact["byte_size"],
            "sha256": artifact["sha256"],
        }
        for artifact in cast(list[dict[str, Any]], acquisition["artifacts"])
    }


def _derive_truth(
    truth: np.ndarray[Any, np.dtype[np.float64]],
    beam_context: _BeamContext,
) -> _TruthDerived:
    """Transform official truth once for all aligned SDC1 tiles."""
    x_pixels, y_pixels = beam_context.image_wcs.all_world2pix(
        truth[:, 3],
        truth[:, 4],
        0,
    )
    in_image = (
        np.isfinite(x_pixels)
        & np.isfinite(y_pixels)
        & (x_pixels >= 0.0)
        & (x_pixels < _IMAGE_SIDE)
        & (y_pixels >= 0.0)
        & (y_pixels < _IMAGE_SIDE)
    )
    tile_x = np.full(len(truth), -1, dtype=np.int64)
    tile_y = np.full(len(truth), -1, dtype=np.int64)
    tile_x[in_image] = np.floor_divide(
        x_pixels[in_image],
        _TILE_SIDE,
    ).astype(np.int64)
    tile_y[in_image] = np.floor_divide(
        y_pixels[in_image],
        _TILE_SIDE,
    ).astype(np.int64)
    major_fwhm, minor_fwhm = gaussian_fwhm_arcsec(
        truth[:, 10],
        truth[:, 7],
        truth[:, 8],
    )
    source_beam = _source_primary_beam(
        ra_deg=np.asarray(truth[:, 3]),
        dec_deg=np.asarray(truth[:, 4]),
        primary_beam=beam_context.primary_beam,
        primary_beam_wcs=beam_context.primary_beam_wcs,
    )
    source_snr = apparent_peak_snr(
        integrated_flux_jy=truth[:, 5],
        primary_beam_response=np.nan_to_num(source_beam, nan=0.0),
        major_fwhm_arcsec=major_fwhm,
        minor_fwhm_arcsec=minor_fwhm,
    )
    return _TruthDerived(
        in_image=in_image,
        tile_x=tile_x,
        tile_y=tile_y,
        major_fwhm=major_fwhm,
        apparent_flux=truth[:, 5] * source_beam,
        source_snr=source_snr,
        source_beam=source_beam,
    )


def _admitted_tiles(
    *,
    truth: np.ndarray[Any, np.dtype[np.float64]],
    derived: _TruthDerived,
    beam_context: _BeamContext,
    progress_path: Path,
) -> tuple[
    list[PublicTileAttributes],
    dict[str, np.ndarray[Any, np.dtype[np.int64]]],
]:
    """Evaluate all 256 candidates without using finder output."""
    admitted: list[PublicTileAttributes] = []
    indices_by_tile: dict[
        str,
        np.ndarray[Any, np.dtype[np.int64]],
    ] = {}
    for y_index in range(_GRID_SIDE):
        for x_index in range(_GRID_SIDE):
            x_start = x_index * _TILE_SIDE
            y_start = y_index * _TILE_SIDE
            mean_beam, valid = _resample_primary_beam(
                x_start=x_start,
                y_start=y_start,
                side=_TILE_SIDE,
                context=beam_context,
            )
            tile_id = f"y{y_index:02d}-x{x_index:02d}"
            is_admitted = valid and mean_beam >= _PRIMARY_BEAM_MINIMUM
            if is_admitted:
                indices = np.flatnonzero(
                    derived.in_image
                    & (derived.tile_x == x_index)
                    & (derived.tile_y == y_index)
                )
                if not np.all(np.isfinite(derived.source_beam[indices])):
                    raise ValueError(
                        "admitted tile contains out-of-domain truth"
                    )
                identifiers = truth[indices, 0].astype(np.int64)
                admitted.append(
                    build_public_tile_attributes(
                        tile_id=tile_id,
                        x_start=x_start,
                        y_start=y_start,
                        truth=PublicTileTruth(
                            identifiers=identifiers,
                            ra_deg=truth[indices, 3],
                            dec_deg=truth[indices, 4],
                            major_fwhm_arcsec=derived.major_fwhm[indices],
                            apparent_flux_jy=derived.apparent_flux[indices],
                            peak_snr=derived.source_snr[indices],
                        ),
                        mean_primary_beam=mean_beam,
                    )
                )
                indices_by_tile[tile_id] = indices
            with progress_path.open("a", encoding="utf-8") as log:
                log.write(
                    f"tile={tile_id} valid={valid} "
                    f"mean_primary_beam={mean_beam:.17g} "
                    f"admitted={is_admitted}\n"
                )
    return admitted, indices_by_tile


def _materialize_sdc1(
    *,
    paths: dict[str, Path],
    truth: np.ndarray[Any, np.dtype[np.float64]],
    staging: Path,
) -> tuple[
    list[PublicTileAttributes],
    list[dict[str, object]],
    dict[str, object],
]:
    """Derive and materialize the selected SDC1 population."""
    with fits.open(paths["primary-beam"], memmap=True) as beam_hdus:
        beam_hdu = cast(fits.PrimaryHDU, beam_hdus[0])
        if beam_hdu.data is None:
            raise ValueError("primary-beam image has no data")
        primary_beam = np.asarray(
            np.squeeze(beam_hdu.data),
            dtype=np.float64,
        )
        if primary_beam.ndim != _TABLE_DIMENSIONS:
            raise ValueError("primary-beam image is not two-dimensional")
        primary_beam_wcs = WCS(beam_hdu.header).celestial
        with fits.open(paths["image"], memmap=True) as image_hdus:
            source_hdu = cast(fits.PrimaryHDU, image_hdus[0])
            if source_hdu.data is None or source_hdu.data.shape[-2:] != (
                _IMAGE_SIDE,
                _IMAGE_SIDE,
            ):
                raise ValueError("SDC1 image shape changed")
            beam_context = _BeamContext(
                image_wcs=WCS(source_hdu.header).celestial,
                primary_beam=primary_beam,
                primary_beam_wcs=primary_beam_wcs,
            )
            admitted, indices_by_tile = _admitted_tiles(
                truth=truth,
                derived=_derive_truth(truth, beam_context),
                beam_context=beam_context,
                progress_path=staging / "progress.log",
            )
            cutout_context = _CutoutContext(
                source_hdu=source_hdu,
                truth=truth,
                output_directory=staging,
            )
            selected = select_public_tiles(admitted)
            cutout_records = [
                _write_cutout(
                    context=cutout_context,
                    truth_indices=indices_by_tile[item.tile.tile_id],
                    tile=item.tile,
                    stratum=item.stratum,
                    ordinal=ordinal,
                )
                for ordinal, item in enumerate(selected, start=1)
            ]
            return admitted, cutout_records, _wcs_record(source_hdu.header)


def select_population(
    *,
    repository_root: Path,
    acquisition_path: Path,
    output_directory: Path,
) -> dict[str, object]:
    """Select, materialize, and atomically seal the approved population."""
    if output_directory.exists():
        raise FileExistsError(
            f"refusing to replace public population: {output_directory}"
        )
    staging = output_directory.with_name(f".{output_directory.name}.staging")
    if staging.exists():
        raise FileExistsError(f"public population staging exists: {staging}")
    load_selection_authorization(repository_root)
    acquisition, paths = load_acquisition(repository_root, acquisition_path)
    staging.mkdir(parents=True)
    truth = _load_truth(paths["truth-catalogue"])
    admitted, cutout_records, image_record = _materialize_sdc1(
        paths=paths,
        truth=truth,
        staging=staging,
    )

    record: dict[str, object] = {
        "schema_version": 1,
        "population_id": "phase-5-public-comparison-selected-population",
        "status": "sealed-before-finder-execution",
        "selection_authorization": {
            "path": _SELECTION_DECISION_PATH.relative_to(_ROOT).as_posix(),
            "sha256": _SELECTION_DECISION_SHA256,
        },
        "schema_review": {
            "path": _SCHEMA_REVIEW_PATH.relative_to(_ROOT).as_posix(),
            "sha256": _SCHEMA_REVIEW_SHA256,
        },
        "acquisition": {
            "path": acquisition_path.relative_to(repository_root).as_posix(),
            "sha256": _ACQUISITION_SHA256,
            "artifacts": _artifact_bindings(acquisition),
        },
        "implementation": {
            "selector_path": Path(__file__).relative_to(_ROOT).as_posix(),
            "selector_sha256": file_sha256(Path(__file__)),
            "adapter_path": _ADAPTER_PATH.relative_to(_ROOT).as_posix(),
            "adapter_sha256": file_sha256(_ADAPTER_PATH),
        },
        "sdc1": {
            "candidate_grid": [_GRID_SIDE, _GRID_SIDE],
            "tile_shape_yx": [_TILE_SIDE, _TILE_SIDE],
            "candidate_tile_count": _GRID_SIDE**2,
            "admitted_tile_count": len(admitted),
            "admission_mean_primary_beam_minimum": _PRIMARY_BEAM_MINIMUM,
            "beam_fwhm_arcsec": _BEAM_FWHM_ARCSEC,
            "source_wcs_and_beam": image_record,
            "truth_column_order": list(_SDC1_COLUMNS),
            "excluded_nonfinite_centroid_truth_ids": list(
                _NONFINITE_CENTROID_TRUTH_IDS
            ),
            "selected_tiles": cutout_records,
            "candidate_output_used": False,
        },
        "hydra": {
            "complete_images_no_crop": True,
            "depths": ["deep", "shallow"],
            "published_finders": [
                "aegean",
                "caesar",
                "profound",
                "pybdsf",
                "selavy",
            ],
            "published_catalogue_products_opened": False,
        },
        "finder_execution_authorized": False,
        "finder_outputs_created": False,
        "qualification_opened": False,
        "cutover_authorized": False,
        "release_authorized": False,
        "next_action": (
            "review-selected-public-population-and-freeze-a-separate-"
            "finder-execution-protocol"
        ),
    }
    population_path = staging / "population.json"
    with population_path.open("xb") as output:
        output.write(
            (
                json.dumps(record, allow_nan=False, indent=2, sort_keys=True)
                + "\n"
            ).encode()
        )
    os.replace(staging, output_directory)
    return record


def _parse_args() -> argparse.Namespace:
    """Parse exact acquisition and terminal population locations."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquisition", type=Path, default=_ACQUISITION_PATH)
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=_DEFAULT_OUTPUT,
    )
    return parser.parse_args()


def main() -> None:
    """Create the one authorized population without invoking any finder."""
    arguments = _parse_args()
    record = select_population(
        repository_root=_ROOT,
        acquisition_path=arguments.acquisition,
        output_directory=arguments.output_directory,
    )
    sdc1 = cast(dict[str, Any], record["sdc1"])
    print(
        "public population sealed: "
        f"admitted={sdc1['admitted_tile_count']} "
        f"selected={len(sdc1['selected_tiles'])}"
    )


if __name__ == "__main__":
    main()
