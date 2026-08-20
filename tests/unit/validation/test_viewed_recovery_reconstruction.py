"""Contracts for rebuilding the viewed Phase 5 reference evidence."""

from __future__ import annotations

import runpy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from hebog.validation.external_runners import source_tree_sha256

_ROOT = Path(__file__).parents[3]
_REFERENCE_DIGESTS = {
    "released-pybdsf": (
        "sha256:5310afe78c8fc09ed99ddee1c6978e5e32181b69f1d22432a02ef6e3a6761198"
    ),
    "pinned-pybdsf-master": (
        "sha256:0e6d932416479bb7d7763fe2e025ea9fbbd0d0548a6f156b2cdd881766690c75"
    ),
    "aegean": (
        "sha256:dcac8e646ff5ea6d11d314c5c7a51fb0c3ca710165934ad2ddf0ac3f999131b0"
    ),
}


def _script(relative_path: str) -> dict[str, Any]:
    return runpy.run_path(str(_ROOT / relative_path))


def test_viewed_recovery_reuses_population_but_rebinds_reference_images() -> (
    None
):
    """The development replay keeps all viewed seeds and current references."""
    module = _script("scripts/validation/phase5_viewed_recovery_protocol.py")

    protocol = module["load_viewed_recovery_protocol"](
        _ROOT
        / "config/contracts/phase-5-external-post-failure-comparison.json"
    )
    decision = module["load_viewed_recovery_execution_decision"](
        _ROOT
        / "config/contracts/phase-5-viewed-recovery-execution-decision.json"
    )

    assert [
        (item.lane, item.image_count) for item in protocol.populations
    ] == [
        ("continuum", 1600),
        ("compact-blend", 800),
    ]
    assert {
        item.finder_id: item.container_image_digest
        for item in protocol.references
    } == _REFERENCE_DIGESTS
    assert decision.execution_authorized is True
    assert decision.fresh_campaign_execution_authorized is False
    assert decision.source_tree_sha256 == source_tree_sha256(_ROOT)


def test_viewed_recovery_filters_only_reference_legs() -> None:
    """Reconstruction runs no obsolete Hebog candidate implementation."""
    module = _script(
        "scripts/validation/reconstruct_phase5_viewed_references.py"
    )
    runs = tuple(
        SimpleNamespace(finder_id=finder)
        for finder in (
            "hebog",
            "released-pybdsf",
            "pinned-pybdsf-master",
            "aegean",
            "released-pybdsf",
        )
    )

    selected = module["_reference_runs"](runs)

    assert tuple(item.finder_id for item in selected) == (
        "released-pybdsf",
        "pinned-pybdsf-master",
        "aegean",
        "released-pybdsf",
    )


def test_prospective_campaign_can_fill_an_absent_historical_candidate(
    tmp_path: Path,
) -> None:
    """A reconstructed reference view receives only current Hebog products."""
    module = _script(
        "scripts/validation/review_phase5_cumulative_regressions.py"
    )
    product = tmp_path / "products" / "input-one"
    product.mkdir(parents=True)
    artifact = product / "compact_catalogue.json"
    artifact.write_text("[]\n", encoding="utf-8")
    marker = {
        "schema_version": 1,
        "input_id": "input-one",
        "configuration_sha256": "c" * 64,
        "source_tree_sha256": "s" * 64,
        "artifacts": [
            {
                "role": "compact-catalogue-json",
                "relative_path": artifact.name,
                "byte_count": artifact.stat().st_size,
                "sha256": module["file_sha256"](artifact),
            }
        ],
    }
    (product / "complete.json").write_bytes(
        module["_canonical_json_bytes"](marker)
    )
    run_request = SimpleNamespace(
        input_id="input-one",
        finder_id="hebog",
        mode="candidate",
    )
    verified = SimpleNamespace(
        request=SimpleNamespace(
            inputs=(SimpleNamespace(input_id="input-one", seed=1),),
            runs=(run_request,),
        ),
        runs={},
    )

    prospective = module["_prospective_campaign"](
        verified,
        tmp_path,
        configuration_sha256="c" * 64,
        revision="a" * 40,
        compiler_globals={"VerifiedRun": SimpleNamespace},
    )

    run = prospective.runs[("input-one", "hebog", "candidate")]
    assert run.request is run_request
    assert run.result.status == "success"
    assert run.result.configuration_sha256 == "c" * 64
    assert run.result.runtime.source_revision == "a" * 40
