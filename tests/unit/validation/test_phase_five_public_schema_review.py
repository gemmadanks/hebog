# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Post-acquisition schema boundary for Phase 5 public evidence."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from astropy.io import fits

_ROOT = Path(__file__).parents[3]
_SCRIPT = _ROOT / "scripts/validation/inspect_phase5_public_schemas.py"


def _script() -> dict[str, Any]:
    """Load the inspection command without opening public evidence."""
    return runpy.run_path(str(_SCRIPT))


def test_public_schema_inspection_requires_exact_acquisition() -> None:
    """Schema inspection is downstream of the terminal checksum record."""
    acquisition = _script()["load_acquisition_record"](
        _ROOT,
        _ROOT / "benchmark-results/phase-5/public-comparison-acquisition/"
        "acquisition.json",
    )

    assert acquisition["artifact_count"] == 7
    assert acquisition["total_bytes"] == 15_053_995_875
    assert acquisition["schema_inspection_authorized"] is True
    assert acquisition["finder_execution_authorized"] is False


def test_public_schema_inspection_binds_serialization_amendment() -> None:
    """Canonical JSON bytes retain the sealed acquisition semantics."""
    namespace = _script()
    acquisition = namespace["load_acquisition_record"](
        _ROOT,
        _ROOT / "benchmark-results/phase-5/public-comparison-acquisition/"
        "acquisition.json",
    )
    amendment = namespace["_validate_serialization_amendment"](
        _ROOT,
        _ROOT / "config/contracts/"
        "phase-5-public-comparison-scientific-decision.json",
        acquisition,
    )

    assert amendment["status"] == "serialization-only-no-semantic-change"
    assert amendment["historical_approved_decision_sha256"].startswith(
        "7bfd3866"
    )
    assert amendment["canonical_decision_sha256"].startswith("d5762063")
    assert amendment["canonicalization"]["changed_fields"] == []
    assert amendment["authorization"]["cutout_selection_authorized"] is False


def test_public_schema_inspection_reads_only_fits_metadata(
    tmp_path: Path,
) -> None:
    """FITS inspection records axes, WCS, units, and beam without pixels."""
    path = tmp_path / "image.fits"
    header = fits.Header()
    header["BUNIT"] = "Jy/beam"
    header["BMAJ"] = 0.001
    header["BMIN"] = 0.0005
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    fits.PrimaryHDU(np.zeros((1, 1, 4, 6), dtype=np.float32), header).writeto(
        path
    )

    schema = _script()["inspect_fits_metadata"](path)

    assert schema["shape"] == [1, 1, 4, 6]
    assert schema["bitpix"] == -32
    assert schema["bunit"] == "Jy/beam"
    assert schema["beam_degrees"] == {
        "major": 0.001,
        "minor": 0.0005,
        "position_angle": None,
    }
    assert schema["pixel_values_inspected"] is False


def test_public_schema_inspection_finds_numeric_table_boundary(
    tmp_path: Path,
) -> None:
    """Text schemas bind header rows and exact numeric column width."""
    path = tmp_path / "catalogue.txt"
    path.write_text(
        "column description\nanother header\n1 2 3 4\n5 6 7 8\n",
        encoding="utf-8",
    )

    schema = _script()["inspect_numeric_text_schema"](
        path,
        expected_columns=4,
    )

    assert schema == {
        "column_count": 4,
        "delimiter": "whitespace",
        "first_numeric_row_index": 2,
        "header_row_count": 2,
    }

    with pytest.raises(ValueError, match="numeric schema"):
        _script()["inspect_numeric_text_schema"](
            path,
            expected_columns=5,
        )


def test_public_schema_review_keeps_selection_and_execution_closed() -> None:
    """The checked proposal defines formulas but authorizes no science."""
    review = _script()["load_checked_schema_review"](
        _ROOT / "config/contracts/phase-5-public-comparison-schema-review.json"
    )

    selection = review["proposed_sdc1_selection"]
    assert selection["tile_shape_yx"] == [2048, 2048]
    assert selection["strata"] == [
        "sparse",
        "ordinary",
        "crowded",
        "resolved",
        "close-pair",
        "high-dynamic-range",
        "low-apparent-SNR",
        "primary-beam-boundary",
    ]
    attributes = selection["tile_attributes"]
    assert "0 for an empty tile" in attributes["resolved_fraction"]
    assert "0 when there is no positive" in attributes["dynamic_range"]
    assert "0 for an empty tile" in attributes["low_snr_fraction"]
    assert review["sdc1"]["truth_catalogue"]["units"]["class"].endswith(
        "report-only for Hebog"
    )
    deviation = review["pre_terminal_observation"]
    assert deviation["status"] == "procedural-deviation-recorded"
    assert deviation["selection_formula_informed_by_observed_values"] is False
    assert deviation["image_pixel_arrays_inspected"] is False
    assert review["artifact_checksums_frozen"] is True
    amendment = review["decision_serialization_amendment"]
    assert amendment["semantic_json_object_changed"] is False
    assert amendment["historical_approved_decision_sha256"].startswith(
        "7bfd3866"
    )
    assert amendment["canonical_decision_sha256"].startswith("d5762063")
    assert review["scientific_review_complete"] is False
    assert review["cutout_selection_authorized"] is False
    assert review["finder_execution_authorized"] is False
    assert review["qualification_opened"] is False
