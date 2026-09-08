"""Fixture-only process and terminal smoke; neither finder is executed."""

from __future__ import annotations

import json
import multiprocessing
import runpy
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from hebog.validation.diagnostic_retention import (
    publish_retained_terminal,
    require_retained_diagnostics,
    verify_diagnostic_packet,
)
from hebog.validation.external_runners import file_sha256
from hebog.validation.source_measurement_evidence import (
    SourceEvidenceInput,
    compile_source_measurement_summary,
)


@pytest.mark.integration
@pytest.mark.parametrize("current_flux", (10.0, 5.0), ids=("pass", "fail"))
def test_spawned_source_summaries_publish_exact_success_or_failure(
    tmp_path: Path, current_flux: float
) -> None:
    """Preserve scientific failure and complete preterminal records."""
    source_evidence_fixture = runpy.run_path(
        str(
            Path(__file__).parents[1]
            / "unit/validation/test_source_measurement_evidence.py"
        )
    )["source_evidence_fixture"]
    batches: list[SourceEvidenceInput] = []
    for finder in ("current-hebog", "released-pybdsf"):
        for seed in range(4):
            batch = source_evidence_fixture(
                finder=finder,
                flux=current_flux if finder == "current-hebog" else 10.0,
            )
            batches.append(
                replace(
                    batch,
                    seed=seed,
                    diagnostics=replace(
                        batch.diagnostics, input_id=f"fixture-{seed}"
                    ),
                )
            )
    with ProcessPoolExecutor(
        max_workers=2, mp_context=multiprocessing.get_context("spawn")
    ) as executor:
        summaries = tuple(
            executor.map(compile_source_measurement_summary, batches)
        )
    parent = Path(__file__).parents[2] / (
        "scripts/validation/evaluate_phase5_compact_held_out_sentinel.py"
    )
    assert file_sha256(parent) == (
        "6f2a05fbc1fbe66781f72554b53b94e83d6754b0809043c214d36493f8e83bfd"
    )
    # These records are only seam fixtures. Actual Serial/Dask scientific
    # equivalence is exercised separately by the public executor tests.
    comparisons: tuple[dict[str, Any], ...] = tuple(
        {
            "input_id": f"dask-fixture-{index}",
            "equal": True,
            "status": "pass",
            "serial_sha256": "a" * 64,
            "dask_sha256": "a" * 64,
        }
        for index in range(12)
    )
    decision = runpy.run_path(str(parent))["evaluate_summaries"](
        list(summaries),
        expected_cell_ids=("thin-cell",),
        realizations_per_cell=4,
        dask_comparisons=comparisons,
    )
    assert decision["passed"] is (current_flux == 10)
    terminal = tmp_path / "terminal.json"
    publish_retained_terminal(
        terminal,
        decision,
        records=summaries,
        dask_comparisons=comparisons,
        expected_keys=tuple(
            (batch.diagnostics.input_id, batch.diagnostics.finder_id)
            for batch in batches
        ),
        expected_dask_ids=tuple(row["input_id"] for row in comparisons),
        provenance={"domain": "analytic-process-fixture"},
    )
    require_retained_diagnostics(
        terminal, terminal_sha256=file_sha256(terminal)
    )
    document = json.loads(terminal.read_bytes())
    pointer = document["diagnostic_packet"]
    manifest_path = tmp_path / pointer["path"]
    manifest = verify_diagnostic_packet(
        manifest_path, expected_sha256=pointer["sha256"]
    )
    assert manifest["record_count"] == 8
    assert manifest["dask_comparison_count"] == 12
    assert document["passed"] is (current_flux == 10)
    if current_flux != 10:
        assert (
            "thin-cell:integrated-flux-p95-pybdsf-parity"
            in (document["failure_reasons"])
        )
    retained = manifest_path.parent / manifest["records"][0]["path"]
    assert json.loads(retained.read_bytes())["diagnostics"][
        "measurement_dispositions"
    ]
