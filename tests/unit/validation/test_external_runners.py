"""Tests for saved external finder results."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import pytest

from hebog.validation.external_runners import (
    ExternalRunArtifact,
    ExternalRunFailure,
    ExternalRunResult,
    ExternalRuntimeIdentity,
    file_sha256,
    load_external_run_result,
)

_SHA256 = "0" * 64
_CONTAINER_DIGEST = f"sha256:{_SHA256}"


def _runtime(name: str, version: str) -> ExternalRuntimeIdentity:
    """Build one concise isolated runtime identity."""
    return ExternalRuntimeIdentity(
        name=name,
        version=version,
        source_revision="0" * 40,
        container_image_digest=_CONTAINER_DIGEST,
        dependency_inventory_sha256=_SHA256,
    )


def _result(
    *,
    status: Literal["success", "failure"],
    artifacts: tuple[ExternalRunArtifact, ...] = (),
    failure: ExternalRunFailure | None = None,
) -> ExternalRunResult:
    """Build one saved synthetic-campaign finder result."""
    return ExternalRunResult(
        schema_version=1,
        protocol_sha256=_SHA256,
        execution_decision_sha256=_SHA256,
        input_bundle_sha256=_SHA256,
        dataset_identifier="external-unit-test",
        seed=7,
        finder_id="aegean",
        mode="operational",
        runtime=_runtime("aegeantools", "2.3.5"),
        configuration_sha256=_SHA256,
        status=status,
        wall_seconds=1.0,
        artifacts=artifacts,
        failure=failure,
    )


def test_saved_external_run_verifies_artifact_bytes(tmp_path: Path) -> None:
    """A saved successful run is readable only while its products match."""
    product = tmp_path / "artifacts/product.txt"
    product.parent.mkdir()
    product.write_text("finder output\n", encoding="utf-8")
    result = _result(
        status="success",
        artifacts=(
            ExternalRunArtifact(
                role="native-product",
                relative_path="artifacts/product.txt",
                byte_count=product.stat().st_size,
                sha256=file_sha256(product),
            ),
        ),
    )
    path = tmp_path / "result.json"
    path.write_bytes(result.canonical_json_bytes())

    assert load_external_run_result(path, verify_artifacts=True) == result

    product.write_text("changed output\n", encoding="utf-8")
    assert load_external_run_result(path, verify_artifacts=False) == result
    with pytest.raises(ValueError, match=r"byte count|checksum"):
        load_external_run_result(path, verify_artifacts=True)


def test_saved_external_run_retains_failure_and_requires_canonical_json(
    tmp_path: Path,
) -> None:
    """Failures stay explicit, and reformatted records are rejected."""
    result = _result(
        status="failure",
        failure=ExternalRunFailure(
            stage="aegean-source-finding",
            exception_type="RuntimeError",
            message="expected finder failure",
            traceback="Traceback: expected finder failure",
        ),
    )
    path = tmp_path / "result.json"
    path.write_bytes(result.canonical_json_bytes())

    loaded = load_external_run_result(path)
    assert loaded.artifacts == ()
    assert loaded.failure is not None
    assert loaded.failure.message == "expected finder failure"

    path.write_text(result.model_dump_json(), encoding="utf-8")
    with pytest.raises(ValueError, match="not canonical JSON"):
        load_external_run_result(path)


@pytest.mark.parametrize(
    ("status", "artifacts", "failure", "message"),
    (
        ("success", (), None, "requires artifacts"),
        ("failure", (), None, "requires failure details"),
    ),
)
def test_saved_external_run_rejects_ambiguous_outcomes(
    status: Literal["success", "failure"],
    artifacts: tuple[ExternalRunArtifact, ...],
    failure: ExternalRunFailure | None,
    message: str,
) -> None:
    """A result cannot claim success without products or hide a failure."""
    with pytest.raises(ValueError, match=message):
        _result(status=status, artifacts=artifacts, failure=failure)
