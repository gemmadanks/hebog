#!/usr/bin/env python3
# pyright: reportArgumentType=false
# pyright: reportMissingTypeStubs=false
# pyright: reportOptionalIterable=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Inspect approved public artifact schemas without opening science outputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tarfile
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO, cast

from astropy.io import fits

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[2]
_ACQUISITION_PATH = (
    _ROOT / "benchmark-results/phase-5/public-comparison-acquisition/"
    "acquisition.json"
)
_ACQUISITION_SHA256 = (
    "a74e60de95debcc53bdf43d4f6046a6f74befe8a85e849a5b0105f2ecb0bd0ce"
)
_ACQUISITION_SCRIPT_SHA256 = (
    "dc467167e322cc71abd74af3a975aafd52dd9c2a6c012e314b378f2ae200a29d"
)
_SCIENTIFIC_DECISION_SHA256 = (
    "7bfd3866240d4300bf53758ef5b8cc1342620fa63447862feb2e112a109f2b45"
)
_CANONICAL_SCIENTIFIC_DECISION_SHA256 = (
    "d5762063e438bf30bf15206e86e4602fdf52ba4b12ba9b88af6a8be853431138"
)
_SERIALIZATION_AMENDMENT_PATH = (
    "config/contracts/"
    "phase-5-public-comparison-decision-serialization-amendment.json"
)
_SERIALIZATION_AMENDMENT_SHA256 = (
    "243d1680f451d1facd22e4594ef9061d40d197fdf71579c54e83a3113284a4b4"
)
_SERIALIZATION_AMENDMENT_COMMIT = "bb824c10b9c55710ac1a8edebefcfa0503bb8027"
_FORMATTER_CONFIGURATION_SHA256 = (
    "8c6c490241f53711a8e4be0f4c2a3e32322e0243c0d67b94acec5fc9f6f5bdc1"
)
_INSPECTOR_PATH = "scripts/validation/inspect_phase5_public_schemas.py"
_EXPECTED_TOTAL_BYTES = 15_053_995_875
_EXPECTED_ARTIFACT_COUNT = 7
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
_HYDRA_FINDERS = ("aegean", "caesar", "profound", "pybdsf", "selavy")
_SDC1_TARGET_SUBMISSION_COUNT = 9
_HYDRA_AGGREGATE_CATALOGUE_COUNT = 3
_HYDRA_DEPTH_COUNT = 2
_SELECTION_STRATA = (
    "sparse",
    "ordinary",
    "crowded",
    "resolved",
    "close-pair",
    "high-dynamic-range",
    "low-apparent-SNR",
    "primary-beam-boundary",
)


def _json_bytes(document: object) -> bytes:
    """Serialize one finite governed record deterministically."""
    return (
        json.dumps(document, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _json_object(path: Path) -> dict[str, Any]:
    """Load one strict JSON object."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return cast(dict[str, Any], value)


def _committed_file_sha256(
    repository_root: Path,
    revision: str,
    path: str,
) -> str:
    """Hash one file from an immutable repository revision."""
    try:
        content = subprocess.run(
            ("git", "show", f"{revision}:{path}"),
            cwd=repository_root,
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError(
            f"cannot read frozen repository file: {path}"
        ) from error
    return hashlib.sha256(content).hexdigest()


def _validate_serialization_amendment(
    repository_root: Path,
    decision_path: Path,
    acquisition: dict[str, Any],
) -> dict[str, Any]:
    """Bridge canonical JSON bytes to the sealed acquisition semantics."""
    amendment_path = repository_root / _SERIALIZATION_AMENDMENT_PATH
    if file_sha256(amendment_path) != _SERIALIZATION_AMENDMENT_SHA256:
        raise ValueError("public decision serialization amendment changed")
    amendment = _json_object(amendment_path)
    canonicalization = cast(dict[str, Any], amendment.get("canonicalization"))
    authorization = cast(dict[str, Any], amendment.get("authorization"))
    named_review = cast(dict[str, Any], amendment.get("named_review"))
    acquisition_identity = cast(dict[str, Any], amendment.get("acquisition"))
    acquisition_implementation = cast(
        dict[str, Any], amendment.get("acquisition_implementation")
    )
    formatter = cast(dict[str, Any], amendment.get("formatter_configuration"))
    if (
        amendment.get("schema_version") != 1
        or amendment.get("amendment_id")
        != "phase-5-public-comparison-decision-serialization-amendment"
        or amendment.get("status") != "serialization-only-no-semantic-change"
        or amendment.get("decision_path")
        != decision_path.relative_to(repository_root).as_posix()
        or amendment.get("historical_approved_decision_sha256")
        != _SCIENTIFIC_DECISION_SHA256
        or amendment.get("canonical_decision_sha256")
        != _CANONICAL_SCIENTIFIC_DECISION_SHA256
        or canonicalization.get("changed_fields") != []
        or canonicalization.get("semantic_json_object_changed") is not False
        or named_review
        != {
            "approved_on": "2026-08-25",
            "reviewer": "Gemma Danks",
            "scope": (
                "serialization-only-provenance-repair-no-scientific-"
                "scope-change"
            ),
        }
        or acquisition_identity.get("path")
        != _ACQUISITION_PATH.relative_to(repository_root).as_posix()
        or acquisition_identity.get("sha256") != _ACQUISITION_SHA256
        or acquisition_implementation.get("path")
        != "scripts/validation/acquire_phase5_public_artifacts.py"
        or acquisition_implementation.get("sha256")
        != _ACQUISITION_SCRIPT_SHA256
        or formatter.get("path") != ".pre-commit-config.yaml"
        or formatter.get("sha256") != _FORMATTER_CONFIGURATION_SHA256
        or _committed_file_sha256(
            repository_root,
            _SERIALIZATION_AMENDMENT_COMMIT,
            cast(str, formatter["path"]),
        )
        != _FORMATTER_CONFIGURATION_SHA256
        or authorization
        != {
            "acquisition_authorized": True,
            "cutout_selection_authorized": False,
            "cutover_authorized": False,
            "execution_authorized": False,
            "qualification_opened": False,
            "scientific_products_opened": False,
        }
    ):
        raise ValueError("public decision serialization amendment is invalid")
    if file_sha256(decision_path) != _CANONICAL_SCIENTIFIC_DECISION_SHA256:
        raise ValueError("canonical public scientific decision changed")
    decision = _json_object(decision_path)
    decision_review = cast(dict[str, Any], decision.get("named_review"))
    if (
        decision.get("schema_version") != 1
        or decision.get("decision_id")
        != "phase-5-public-comparison-scientific-decision"
        or decision.get("status")
        != "scientifically-approved-for-acquisition-before-output"
        or decision.get("acquisition_authorized") is not True
        or decision.get("artifact_checksums_frozen") is not False
        or decision.get("cutout_selection_authorized") is not False
        or decision.get("execution_authorized") is not False
        or decision.get("qualification_opened") is not False
        or decision.get("scientific_products_opened") is not False
        or decision.get("cutover_authorized") is not False
        or decision_review.get("reviewer") != "Gemma Danks"
        or decision_review.get("approved_on") != "2026-08-25"
        or decision_review.get("scope")
        != (
            "sdc1-hydra-acquisition-and-post-acquisition-freeze-"
            "preparation-only-no-scientific-execution"
        )
    ):
        raise ValueError("canonical public scientific decision is invalid")
    requests = cast(list[dict[str, Any]], decision.get("artifact_requests"))
    artifacts = cast(list[dict[str, Any]], acquisition.get("artifacts"))
    request_identities = tuple(
        (
            item.get("dataset_id"),
            item.get("identifier"),
            item.get("filename"),
            item.get("expected_bytes"),
            item.get("source_url"),
        )
        for item in requests
    )
    acquisition_identities = tuple(
        (
            item.get("dataset_id"),
            item.get("identifier"),
            item.get("filename"),
            item.get("byte_size"),
            item.get("source_url"),
        )
        for item in artifacts
    )
    if (
        request_identities != acquisition_identities
        or len(requests) != _EXPECTED_ARTIFACT_COUNT
        or sum(cast(int, item[3]) for item in request_identities)
        != _EXPECTED_TOTAL_BYTES
    ):
        raise ValueError("canonical public artifact requests changed")
    return amendment


def load_acquisition_record(
    repository_root: Path,
    acquisition_path: Path,
) -> dict[str, Any]:
    """Validate the terminal acquisition boundary before schema access."""
    if file_sha256(acquisition_path) != _ACQUISITION_SHA256:
        raise ValueError("public acquisition checksum changed")
    acquisition = _json_object(acquisition_path)
    if (
        acquisition.get("schema_version") != 1
        or acquisition.get("acquisition_id")
        != "phase-5-public-comparison-acquisition"
        or acquisition.get("status")
        != "complete-and-checksummed-before-science-inspection"
        or acquisition.get("artifact_count") != _EXPECTED_ARTIFACT_COUNT
        or acquisition.get("total_bytes") != _EXPECTED_TOTAL_BYTES
        or acquisition.get("scientific_decision_sha256")
        != _SCIENTIFIC_DECISION_SHA256
        or acquisition.get("schema_inspection_authorized") is not True
        or acquisition.get("cutout_selection_authorized") is not False
        or acquisition.get("finder_execution_authorized") is not False
        or acquisition.get("qualification_opened") is not False
        or acquisition.get("scientific_products_opened") is not False
    ):
        raise ValueError("public acquisition state is invalid")
    decision_path = repository_root / cast(
        str, acquisition["scientific_decision_path"]
    )
    _validate_serialization_amendment(
        repository_root,
        decision_path,
        acquisition,
    )
    artifacts = cast(list[dict[str, Any]], acquisition.get("artifacts"))
    identities = tuple(
        (item.get("dataset_id"), item.get("identifier")) for item in artifacts
    )
    if len(artifacts) != _EXPECTED_ARTIFACT_COUNT or len(
        set(identities)
    ) != len(artifacts):
        raise ValueError("public acquisition artifact identities changed")
    return acquisition


def _artifact_paths(
    acquisition_path: Path,
    acquisition: dict[str, Any],
) -> dict[str, Path]:
    """Verify every raw artifact against the terminal record."""
    raw_directory = acquisition_path.parent / "raw"
    paths: dict[str, Path] = {}
    for artifact in cast(list[dict[str, Any]], acquisition["artifacts"]):
        filename = cast(str, artifact["filename"])
        path = raw_directory / filename
        if (
            not path.is_file()
            or path.stat().st_size != artifact["byte_size"]
            or file_sha256(path) != artifact["sha256"]
        ):
            raise ValueError(f"acquired public artifact changed: {filename}")
        paths[cast(str, artifact["identifier"])] = path
    return paths


def inspect_fits_metadata(path: Path) -> dict[str, object]:
    """Read only primary FITS header structure, WCS, units, and beam."""
    header = fits.getheader(path, ext=0)
    axis_count = int(header["NAXIS"])
    shape = [int(header[f"NAXIS{axis}"]) for axis in range(axis_count, 0, -1)]
    wcs = {
        key.lower(): header.get(key)
        for key in (
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
        )
    }
    return {
        "shape": shape,
        "bitpix": int(header["BITPIX"]),
        "bunit": header.get("BUNIT"),
        "beam_degrees": {
            "major": header.get("BMAJ"),
            "minor": header.get("BMIN"),
            "position_angle": header.get("BPA"),
        },
        "wcs": wcs,
        "pixel_values_inspected": False,
    }


def _numeric_boundary(
    lines: Any,
    *,
    expected_columns: int,
) -> dict[str, object]:
    """Locate the first whitespace-delimited all-numeric catalogue row."""
    for index, line in enumerate(lines):
        fields = line.strip().split()
        if len(fields) != expected_columns:
            continue
        try:
            tuple(float(field) for field in fields)
        except ValueError:
            continue
        return {
            "column_count": expected_columns,
            "delimiter": "whitespace",
            "first_numeric_row_index": index,
            "header_row_count": index,
        }
    raise ValueError("numeric schema was not found")


def inspect_numeric_text_schema(
    path: Path,
    *,
    expected_columns: int,
) -> dict[str, object]:
    """Inspect only the header boundary and numeric width of a text table."""
    with path.open(encoding="utf-8") as lines:
        return _numeric_boundary(lines, expected_columns=expected_columns)


def _fits_table_schema(payload: bytes) -> dict[str, object]:
    """Read FITS table names, units, formats, and row counts from bytes."""
    with fits.open(
        BytesIO(payload), memmap=False, lazy_load_hdus=True
    ) as hdus:
        tables: list[dict[str, object]] = []
        for hdu in hdus:
            if not isinstance(hdu, fits.BinTableHDU):
                continue
            tables.append(
                {
                    "extension": hdu.name,
                    "row_count": int(hdu.header["NAXIS2"]),
                    "columns": [
                        {
                            "name": column.name,
                            "unit": column.unit,
                            "format": column.format,
                        }
                        for column in hdu.columns
                    ],
                }
            )
    if len(tables) != 1:
        raise ValueError("expected exactly one Hydra FITS table")
    return tables[0]


def _read_member(member_file: BinaryIO | None, *, name: str) -> bytes:
    """Require a regular archive member stream."""
    if member_file is None:
        raise ValueError(f"archive member is unreadable: {name}")
    return member_file.read()


def inspect_sdc1_submissions(path: Path) -> dict[str, object]:
    """Inspect only target-frequency/depth member names and header widths."""
    with tarfile.open(path, "r:gz") as archive:
        members = tuple(
            member for member in archive.getmembers() if member.isfile()
        )
        targets = tuple(
            member
            for member in members
            if "1400MHz_1000h" in member.name and member.name.endswith(".txt")
        )
        records = []
        for member in targets:
            payload = _read_member(
                archive.extractfile(member),
                name=member.name,
            ).decode("utf-8", errors="strict")
            schema = _numeric_boundary(
                payload.splitlines(),
                expected_columns=len(_SDC1_COLUMNS),
            )
            records.append(
                {
                    "member": member.name,
                    "byte_size": member.size,
                    **schema,
                }
            )
    if len(records) != _SDC1_TARGET_SUBMISSION_COUNT:
        raise ValueError("expected nine SDC1 1400-MHz 1000-hour submissions")
    return {
        "archive_member_count": len(members),
        "target_submission_count": len(records),
        "target_submissions": records,
        "catalogue_values_inspected": False,
    }


def inspect_hydra_archive(path: Path) -> dict[str, object]:
    """Inspect Hydra member layout and published catalogue table schemas."""
    with tarfile.open(path, "r:gz") as archive:
        members = tuple(
            member for member in archive.getmembers() if member.isfile()
        )
        catalogues = tuple(
            member
            for member in members
            if (
                "/catalogues/deep/" in member.name
                or "/catalogues/shallow/" in member.name
            )
            and member.name.endswith(".fits")
        )
        records = []
        for member in catalogues:
            payload = _read_member(
                archive.extractfile(member),
                name=member.name,
            )
            records.append(
                {
                    "member": member.name,
                    "byte_size": member.size,
                    "table": _fits_table_schema(payload),
                }
            )
        cluster_members = tuple(
            member
            for member in members
            if member.name.endswith("hydra.cluster_catalogue.fits")
            or member.name.endswith("hydra.clump_catalogue.fits")
            or member.name.endswith("hydra.global_metrics.fits")
        )
    if (
        len(catalogues) != _HYDRA_DEPTH_COUNT * len(_HYDRA_FINDERS)
        or len(cluster_members) != _HYDRA_AGGREGATE_CATALOGUE_COUNT
    ):
        raise ValueError("Hydra published catalogue layout changed")
    observed_finders = {
        finder
        for finder in _HYDRA_FINDERS
        if sum(f".hydra.{finder}." in item["member"] for item in records)
        == _HYDRA_DEPTH_COUNT
    }
    if observed_finders != set(_HYDRA_FINDERS):
        raise ValueError("Hydra finder catalogue set changed")
    return {
        "archive_member_count": len(members),
        "finder_catalogue_count": len(records),
        "finders": list(_HYDRA_FINDERS),
        "finder_catalogues": records,
        "aggregate_catalogues": [
            {"member": member.name, "byte_size": member.size}
            for member in cluster_members
        ],
        "catalogue_values_inspected": False,
        "residual_pixel_values_inspected": False,
    }


def _proposed_selection() -> dict[str, object]:
    """Return the exact pending truth-only SDC1 selection proposal."""
    return {
        "status": "pending-named-scientific-review",
        "tile_shape_yx": [2048, 2048],
        "candidate_grid": (
            "nonoverlapping half-open tiles aligned at x,y multiples of 2048 "
            "over the complete 32768-square image"
        ),
        "primary_beam_resampling": (
            "bilinear interpolation of PrimaryBeam_B2.fits at every SDC1 "
            "image-pixel centre through the two recorded celestial WCSs"
        ),
        "admission": (
            "arithmetic mean of finite resampled primary-beam values is at "
            "least 0.5; any non-finite or out-of-domain sample rejects tile"
        ),
        "truth_membership": (
            "official ra_cent,dec_cent transformed with the image WCS lies "
            "inside the tile half-open pixel bounds"
        ),
        "size_conversion_to_gaussian_fwhm": {
            "size=1-largest-angular-size": "multiply b_maj,b_min by 2.355/5",
            "size=2-gaussian-fwhm": "identity",
            "size=3-exponential-scale": "multiply b_maj,b_min by sqrt(2)",
        },
        "apparent_flux": (
            "truth integrated flux in Jy multiplied by bilinearly "
            "interpolated primary-beam response at the truth centroid"
        ),
        "apparent_peak_snr": (
            "apparent integrated flux times 0.6*0.6 divided by "
            "sqrt(converted_b_maj**2+0.6**2)*"
            "sqrt(converted_b_min**2+0.6**2), then divided by "
            "73e-9 Jy/beam"
        ),
        "noise_reference": (
            "Bonaldi et al. 2021 MNRAS 500 3821 Table 1, 1400-MHz "
            "1000-hour 73-nJy/beam nominal thermal noise"
        ),
        "tile_attributes": {
            "source_count": "number of truth centroids in tile",
            "resolved_fraction": (
                "fraction with converted Gaussian major FWHM greater than "
                "the recorded 0.6-arcsec synthesized beam; 0 for an empty "
                "tile"
            ),
            "closest_pair_beams": (
                "minimum truth-centroid great-circle separation divided by "
                "0.6 arcsec; infinity for fewer than two sources"
            ),
            "dynamic_range": (
                "maximum apparent integrated flux divided by median positive "
                "apparent integrated flux; 0 when there is no positive "
                "apparent flux"
            ),
            "low_snr_fraction": (
                "fraction with apparent peak SNR in the closed interval "
                "[5,8]; 0 for an empty tile"
            ),
            "mean_primary_beam": "the admission mean",
        },
        "strata": list(_SELECTION_STRATA),
        "ranking": [
            "sparse: source_count ascending",
            (
                "ordinary: abs(source_count - median admitted source_count) "
                "ascending"
            ),
            "crowded: source_count descending",
            "resolved: resolved_fraction descending",
            "close-pair: closest_pair_beams ascending",
            "high-dynamic-range: dynamic_range descending",
            "low-apparent-SNR: low_snr_fraction descending",
            "primary-beam-boundary: mean_primary_beam ascending",
        ],
        "tie_break": (
            "increasing global tile-core (y_start,x_start); select in stratum "
            "order and take the first not already selected"
        ),
        "candidate_output_used": False,
    }


def build_schema_review(
    *,
    repository_root: Path,
    acquisition_path: Path,
) -> dict[str, object]:
    """Build the checksum and schema freeze pending scientific review."""
    acquisition = load_acquisition_record(repository_root, acquisition_path)
    paths = _artifact_paths(acquisition_path, acquisition)
    artifacts = cast(list[dict[str, Any]], acquisition["artifacts"])
    artifact_checksums = [
        {
            "dataset_id": item["dataset_id"],
            "identifier": item["identifier"],
            "filename": item["filename"],
            "byte_size": item["byte_size"],
            "sha256": item["sha256"],
        }
        for item in artifacts
    ]
    truth_schema = inspect_numeric_text_schema(
        paths["truth-catalogue"],
        expected_columns=len(_SDC1_COLUMNS),
    )
    return {
        "schema_version": 1,
        "review_id": "phase-5-public-comparison-schema-review",
        "status": "pending-named-scientific-review-before-selection",
        "acquisition": {
            "path": acquisition_path.relative_to(repository_root).as_posix(),
            "sha256": _ACQUISITION_SHA256,
            "implementation_sha256": _ACQUISITION_SCRIPT_SHA256,
            "artifact_count": _EXPECTED_ARTIFACT_COUNT,
            "total_bytes": _EXPECTED_TOTAL_BYTES,
        },
        "decision_serialization_amendment": {
            "path": _SERIALIZATION_AMENDMENT_PATH,
            "sha256": _SERIALIZATION_AMENDMENT_SHA256,
            "historical_approved_decision_sha256": (
                _SCIENTIFIC_DECISION_SHA256
            ),
            "canonical_decision_sha256": (
                _CANONICAL_SCIENTIFIC_DECISION_SHA256
            ),
            "semantic_json_object_changed": False,
        },
        "artifacts": artifact_checksums,
        "sdc1": {
            "image": inspect_fits_metadata(paths["image"]),
            "primary_beam": inspect_fits_metadata(paths["primary-beam"]),
            "truth_catalogue": {
                **truth_schema,
                "columns": list(_SDC1_COLUMNS),
                "units": {
                    "ra_core,dec_core,ra_cent,dec_cent": "degree",
                    "flux": "Jy intrinsic integrated flux density",
                    "core_frac": "dimensionless",
                    "b_maj,b_min": (
                        "arcsecond in size convention named by size"
                    ),
                    "pa": "degree clockwise from due west",
                    "size": (
                        "1=largest-angular-size,2=Gaussian-FWHM,"
                        "3=exponential-scale"
                    ),
                    "class": (
                        "integer source-population label interpreted only by "
                        "the official SDC1 response/scoring definition; "
                        "report-only for Hebog"
                    ),
                },
            },
            "official_scoring_reference": {
                "repository": "https://gitlab.com/ska-telescope/sdc/ska-sdc",
                "commit": "d54a968293363ad130586c8a88161dc5c89506ee",
                "catalogue_definition_sha256": (
                    "feefc3b716779edf4aac4aa643d5aeda5237393793ff9b81856dc1abee750c9b"
                ),
                "preparation_sha256": (
                    "ec3646dd0cacdfa31fed8f043eabca4e2926bb1a3b5e5d43fb11a8ef203f3621"
                ),
                "size_constants_sha256": (
                    "0ceed55c5e796153216616c73ef6feb3b56651cac818bdd3727438cd91347b13"
                ),
                "official_score_role": "report-only",
            },
            "submitted_catalogues": inspect_sdc1_submissions(
                paths["official-submissions"]
            ),
        },
        "hydra": {
            "deep_image": inspect_fits_metadata(paths["deep-image"]),
            "shallow_image": inspect_fits_metadata(paths["shallow-image"]),
            "archive": inspect_hydra_archive(paths["hydra-archive"]),
            "truth_role": "real-survey-diagnostic-with-no-astronomical-truth",
        },
        "pre_terminal_observation": {
            "status": "procedural-deviation-recorded",
            "observation": (
                "while the final Hydra archive was still downloading, FITS "
                "headers and the first five SDC1 truth rows of already "
                "complete exact-sized files were inspected before the "
                "aggregate acquisition record sealed"
            ),
            "image_pixel_arrays_inspected": False,
            "finder_products_inspected": False,
            "catalogue_distributions_inspected": False,
            "selection_formula_informed_by_observed_values": False,
            "consequence": (
                "record the deviation transparently; keep cutout selection "
                "and all finder execution closed pending named review"
            ),
        },
        "proposed_sdc1_selection": _proposed_selection(),
        "inspector": {
            "path": _INSPECTOR_PATH,
            "sha256": file_sha256(Path(__file__)),
        },
        "artifact_checksums_frozen": True,
        "scientific_review_complete": False,
        "cutout_selection_authorized": False,
        "finder_execution_authorized": False,
        "qualification_opened": False,
        "cutover_authorized": False,
        "next_action": (
            "obtain-named-review-of-exact-schema-adapters-and-selection-"
            "formulas-before-generating-any-cutout-or-finder-output"
        ),
    }


def load_checked_schema_review(path: Path) -> dict[str, Any]:
    """Validate the checked pending review and its immutable dependencies."""
    review = _json_object(path)
    acquisition = cast(dict[str, Any], review.get("acquisition"))
    amendment = cast(
        dict[str, Any], review.get("decision_serialization_amendment")
    )
    inspector = cast(dict[str, Any], review.get("inspector"))
    if (
        review.get("schema_version") != 1
        or review.get("review_id") != "phase-5-public-comparison-schema-review"
        or review.get("status")
        != "pending-named-scientific-review-before-selection"
        or acquisition.get("sha256") != _ACQUISITION_SHA256
        or acquisition.get("artifact_count") != _EXPECTED_ARTIFACT_COUNT
        or acquisition.get("total_bytes") != _EXPECTED_TOTAL_BYTES
        or amendment.get("path") != _SERIALIZATION_AMENDMENT_PATH
        or amendment.get("sha256") != _SERIALIZATION_AMENDMENT_SHA256
        or amendment.get("historical_approved_decision_sha256")
        != _SCIENTIFIC_DECISION_SHA256
        or amendment.get("canonical_decision_sha256")
        != _CANONICAL_SCIENTIFIC_DECISION_SHA256
        or amendment.get("semantic_json_object_changed") is not False
        or inspector.get("path") != _INSPECTOR_PATH
        or inspector.get("sha256")
        != _committed_file_sha256(
            path.resolve().parents[2],
            _SERIALIZATION_AMENDMENT_COMMIT,
            _INSPECTOR_PATH,
        )
        or review.get("artifact_checksums_frozen") is not True
        or review.get("scientific_review_complete") is not False
        or review.get("cutout_selection_authorized") is not False
        or review.get("finder_execution_authorized") is not False
        or review.get("qualification_opened") is not False
        or review.get("cutover_authorized") is not False
    ):
        raise ValueError("public schema review state is invalid")
    selection = cast(dict[str, Any], review.get("proposed_sdc1_selection"))
    if selection.get("strata") != list(_SELECTION_STRATA):
        raise ValueError("public schema selection strata changed")
    return review


def _parse_args() -> argparse.Namespace:
    """Parse exact acquisition and write-once review paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--acquisition",
        type=Path,
        default=_ACQUISITION_PATH,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            _ROOT
            / "config/contracts/phase-5-public-comparison-schema-review.json"
        ),
    )
    return parser.parse_args()


def main() -> None:
    """Write the pending schema review exactly once."""
    arguments = _parse_args()
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to replace public schema review: {arguments.output}"
        )
    review = build_schema_review(
        repository_root=_ROOT,
        acquisition_path=arguments.acquisition,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open("xb") as output:
        output.write(_json_bytes(review))


if __name__ == "__main__":
    main()
