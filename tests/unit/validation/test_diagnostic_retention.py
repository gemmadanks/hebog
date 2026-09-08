"""The final decision must not outlive its only detailed evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from hebog.validation.diagnostic_retention import (
    publish_diagnostic_packet,
    publish_retained_terminal,
    require_retained_diagnostics,
    verify_diagnostic_packet,
)
from hebog.validation.external_runners import canonical_sha256, file_sha256


def _record(finder: str = "current-hebog") -> dict[str, Any]:
    record: dict[str, Any] = {
        "input_id": "fixture",
        "finder_id": finder,
        "signed_measurement_residuals": [{"flux_fraction": -0.1}],
    }
    return {**record, "record_sha256": canonical_sha256(record)}


def _publish(root: Path) -> Path:
    record = _record()
    return publish_diagnostic_packet(
        root,
        (record,),
        (
            {
                "input_id": "fixture",
                "status": "pass",
                "serial_sha256": record["record_sha256"],
                "dask_sha256": record["record_sha256"],
            },
        ),
        expected_keys=(("fixture", "current-hebog"),),
        expected_dask_ids=("fixture",),
        provenance={"candidate": "a" * 40},
    )


def test_packet_keeps_exact_records_and_supports_verified_cleanup(
    tmp_path: Path,
) -> None:
    path = _publish(tmp_path / "diagnostics")
    digest = file_sha256(path)
    manifest = verify_diagnostic_packet(path, expected_sha256=digest)
    assert manifest["record_count"] == manifest["dask_comparison_count"] == 1
    terminal = tmp_path / "terminal.json"
    terminal.write_text(
        json.dumps(
            {
                "diagnostic_packet": {
                    "path": "diagnostics/manifest.json",
                    "sha256": digest,
                },
            }
        )
    )
    require_retained_diagnostics(
        terminal, terminal_sha256=file_sha256(terminal)
    )
    retained = path.parent / manifest["records"][0]["path"]
    assert json.loads(retained.read_bytes()) == _record()
    retained.unlink()
    with pytest.raises(ValueError, match="retained diagnostic"):
        require_retained_diagnostics(
            terminal, terminal_sha256=file_sha256(terminal)
        )


def test_packet_is_write_once_and_missing_census_cannot_publish(
    tmp_path: Path,
) -> None:
    _publish(tmp_path / "existing")
    with pytest.raises(FileExistsError):
        _publish(tmp_path / "existing")
    with pytest.raises(ValueError, match="census"):
        publish_diagnostic_packet(
            tmp_path / "incomplete",
            (),
            (),
            expected_keys=(("fixture", "current-hebog"),),
            expected_dask_ids=(),
            provenance={},
        )
    assert not (tmp_path / "incomplete").exists()


@pytest.mark.parametrize("defect", ("record", "manifest", "dask", "symlink"))
def test_cleanup_rejects_missing_or_modified_diagnostics(
    tmp_path: Path, defect: str
) -> None:
    path = _publish(tmp_path / "diagnostics")
    digest = file_sha256(path)
    manifest = json.loads(path.read_bytes())
    target = (
        path
        if defect == "manifest"
        else path.parent
        / (
            manifest["dask_comparisons"][0]["path"]
            if defect == "dask"
            else manifest["records"][0]["path"]
        )
    )
    if defect == "symlink":
        other = tmp_path / "copied.json"
        other.write_bytes(target.read_bytes())
        target.unlink()
        target.symlink_to(other)
    else:
        target.write_text("{}")
    with pytest.raises(ValueError, match="diagnostic"):
        verify_diagnostic_packet(path, expected_sha256=digest)


def test_incorrect_record_digest_fails_before_namespace_creation(
    tmp_path: Path,
) -> None:
    record = {**_record(), "record_sha256": "0" * 64}
    with pytest.raises(ValueError, match="record digest"):
        publish_diagnostic_packet(
            tmp_path / "bad",
            (record,),
            (),
            expected_keys=(("fixture", "current-hebog"),),
            expected_dask_ids=(),
            provenance={},
        )
    assert not (tmp_path / "bad").exists()


@pytest.mark.parametrize(
    "comparison",
    (
        {"input_id": "fixture"},
        {"input_id": "fixture", "status": "pass"},
        {
            "input_id": "fixture",
            "status": "pass",
            "serial_sha256": "a" * 64,
            "dask_sha256": "b" * 64,
        },
        {
            "input_id": "fixture",
            "status": "fail",
            "serial_sha256": "a" * 64,
            "dask_sha256": "a" * 64,
        },
        {
            "input_id": "fixture",
            "status": "pass",
            "serial_sha256": "not-a-digest",
            "dask_sha256": "not-a-digest",
        },
        {
            "input_id": "fixture",
            "status": "pass",
            "equal": False,
            "serial_sha256": "a" * 64,
            "dask_sha256": "a" * 64,
        },
        {
            "input_id": "fixture",
            "status": "fail",
            "equal": True,
            "serial_sha256": "a" * 64,
            "dask_sha256": "b" * 64,
        },
        {
            "input_id": "fixture",
            "status": "pass",
            "equal": 1,
            "serial_sha256": "a" * 64,
            "dask_sha256": "a" * 64,
        },
    ),
)
def test_dask_claim_requires_matching_scientific_digests_before_writing(
    tmp_path: Path, comparison: dict[str, Any]
) -> None:
    with pytest.raises(ValueError, match="Dask comparison"):
        publish_diagnostic_packet(
            tmp_path / "bad",
            (_record(),),
            (comparison,),
            expected_keys=(("fixture", "current-hebog"),),
            expected_dask_ids=("fixture",),
            provenance={},
        )
    assert not (tmp_path / "bad").exists()


def test_failed_dask_comparison_is_preserved_as_evidence(
    tmp_path: Path,
) -> None:
    comparison = {
        "input_id": "fixture",
        "status": "fail",
        "serial_sha256": "a" * 64,
        "dask_sha256": "b" * 64,
    }
    path = publish_diagnostic_packet(
        tmp_path / "failure",
        (_record(),),
        (comparison,),
        expected_keys=(("fixture", "current-hebog"),),
        expected_dask_ids=("fixture",),
        provenance={},
    )
    manifest = verify_diagnostic_packet(
        path, expected_sha256=file_sha256(path)
    )
    retained = path.parent / manifest["dask_comparisons"][0]["path"]
    assert json.loads(retained.read_bytes()) == comparison


def test_terminal_publication_requires_retained_records_first(
    tmp_path: Path,
) -> None:
    terminal = tmp_path / "decision.json"
    publish_retained_terminal(
        terminal,
        {"passed": False, "status": "scientific-failure"},
        records=(_record(),),
        dask_comparisons=(),
        expected_keys=(("fixture", "current-hebog"),),
        expected_dask_ids=(),
        provenance={"candidate": "a" * 40},
    )
    require_retained_diagnostics(
        terminal, terminal_sha256=file_sha256(terminal)
    )
    before = terminal.read_bytes()
    assert json.loads(before)["passed"] is False
    with pytest.raises(FileExistsError):
        publish_retained_terminal(
            terminal,
            {"passed": True},
            records=(),
            dask_comparisons=(),
            expected_keys=(),
            expected_dask_ids=(),
            provenance={},
        )
    assert terminal.read_bytes() == before


def test_invalid_census_cannot_publish_a_terminal(tmp_path: Path) -> None:
    terminal = tmp_path / "decision.json"
    with pytest.raises(ValueError, match="census"):
        publish_retained_terminal(
            terminal,
            {"passed": True},
            records=(),
            dask_comparisons=(),
            expected_keys=(("fixture", "current-hebog"),),
            expected_dask_ids=(),
            provenance={},
        )
    assert not terminal.exists()
    assert not (tmp_path / "decision.diagnostics").exists()


@pytest.mark.parametrize(
    "defect",
    (
        "schema",
        "escaped-path",
        "record-identity",
        "dask-identity",
        "count",
        "non-object",
    ),
)
def test_packet_semantics_are_checked_even_with_matching_file_hashes(
    tmp_path: Path, defect: str
) -> None:
    path = _publish(tmp_path / "diagnostics")
    manifest = json.loads(path.read_bytes())
    if defect == "schema":
        manifest["schema_version"] = 2
    elif defect == "escaped-path":
        manifest["records"][0]["path"] = "../outside.json"
    elif defect == "record-identity":
        manifest["records"][0]["input_id"] = "wrong"
    elif defect == "dask-identity":
        manifest["dask_comparisons"][0]["input_id"] = "wrong"
    elif defect == "count":
        manifest["record_count"] = 2
    else:
        entry = manifest["records"][0]
        record_path = path.parent / entry["path"]
        record_path.write_text("[]")
        entry["sha256"] = file_sha256(record_path)
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="diagnostic"):
        verify_diagnostic_packet(path, expected_sha256=file_sha256(path))


def test_terminal_without_packet_or_with_reserved_claim_cannot_pass(
    tmp_path: Path,
) -> None:
    terminal = tmp_path / "missing.json"
    terminal.write_text("{}")
    with pytest.raises(ValueError, match="absent from terminal"):
        require_retained_diagnostics(
            terminal, terminal_sha256=file_sha256(terminal)
        )
    with pytest.raises(ValueError, match="assigned at publication"):
        publish_retained_terminal(
            tmp_path / "reserved.json",
            {"diagnostic_packet": {}},
            records=(),
            dask_comparisons=(),
            expected_keys=(),
            expected_dask_ids=(),
            provenance={},
        )
    record = {**_record(), "input_id": ""}
    with pytest.raises(ValueError, match="identity is absent"):
        publish_diagnostic_packet(
            tmp_path / "bad-record",
            (record,),
            (),
            expected_keys=(),
            expected_dask_ids=(),
            provenance={},
        )
