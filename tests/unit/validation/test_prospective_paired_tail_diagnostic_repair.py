"""Prospective paired tail-diagnostic repair contracts."""

# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownLambdaType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import runpy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[3]
_REPAIR = (
    _ROOT
    / "scripts/validation/repair_phase5_prospective_paired_tail_diagnostics.py"
)
_EVALUATOR = (
    _ROOT / "scripts/validation/"
    "evaluate_phase5_prospective_paired_cumulative_tail_repair.py"
)


def test_repaired_evaluator_preserves_parent_and_installs_tail_overlay() -> (
    None
):
    """The repair changes only the tail seam on the frozen parent evaluator."""
    overlay = runpy.run_path(str(_EVALUATOR))

    assert (
        file_sha256(overlay["_PARENT_EVALUATOR"])
        == overlay["_PARENT_EVALUATOR_SHA256"]
    )
    assert (
        file_sha256(overlay["_TAIL_REPAIR"]) == overlay["_TAIL_REPAIR_SHA256"]
    )
    evaluator = overlay["load_repaired_evaluator"]()
    evaluator_globals = evaluator["main"].__globals__
    assert (
        evaluator_globals["_truth_linked_tail_record"]
        is not evaluator["_ORIGINAL_TRUTH_LINKED_TAIL_RECORD"]
    )
    assert (
        Path(evaluator_globals["__file__"]).resolve() == _EVALUATOR.resolve()
    )


def test_tail_repair_keeps_association_and_publication_planes_distinct(
    tmp_path: Path,
) -> None:
    """Hebog source composition follows measurement labels."""
    repair = runpy.run_path(str(_REPAIR))
    compile_tail = repair["truth_linked_tail_record"]
    dataset = SimpleNamespace(
        identifier="dataset",
        beam=SimpleNamespace(major_fwhm_pixels=4.0),
    )
    campaign_input = SimpleNamespace(
        input_id="continuum-input", dataset_identifier="dataset", seed=1
    )
    hebog_run = SimpleNamespace(
        result=SimpleNamespace(
            finder_id="hebog",
            artifacts=(SimpleNamespace(role="measurement-labels-fits"),),
        )
    )
    reference_run = SimpleNamespace(
        result=SimpleNamespace(finder_id="pybdsf", artifacts=())
    )
    current = SimpleNamespace(
        request=SimpleNamespace(inputs=(campaign_input,)),
        inputs={"continuum-input": (object(), tmp_path / "input.json")},
        runs={
            ("continuum-input", "hebog", "candidate"): hebog_run,
            (
                "continuum-input",
                "pinned-pybdsf-master",
                "operational",
            ): reference_run,
            (
                "continuum-input",
                "released-pybdsf",
                "operational",
            ): reference_run,
        },
    )
    incumbent = SimpleNamespace(
        runs={("continuum-input", "hebog", "candidate"): hebog_run}
    )
    publication_labels = np.asarray(((0, 7), (0, 0)), dtype=np.int64)
    measurement_labels = np.asarray(((7, 8), (0, 0)), dtype=np.int64)
    truth_labels = np.asarray(((1, 1), (0, 0)), dtype=np.int64)
    source = SimpleNamespace(identifier="source", component_count=2)
    candidate = SimpleNamespace(identifier="source")
    reconstruction_planes: list[np.ndarray[Any, Any]] = []
    summary_planes: list[
        tuple[str, np.ndarray[Any, Any], np.ndarray[Any, Any]]
    ] = []

    def candidate_objects(
        _catalogue: object,
        labels: np.ndarray[Any, Any],
        **_kwargs: object,
    ) -> tuple[object, ...]:
        reconstruction_planes.append(labels)
        return (candidate,)

    def build_summary(**values: Any) -> dict[str, object]:
        summary_planes.append(
            (
                values["finder_id"],
                values["candidate_label_plane"],
                values["association_label_plane"],
            )
        )
        return {
            "input_id": values["input_id"],
            "finder_id": values["finder_id"],
            "array_planes_retained": False,
            "record_sha256": "old",
        }

    parent = {
        "_sentinel_memberships": lambda **_kwargs: {
            "continuum-input": [
                {
                    "sentinel_id": "morphology-shell",
                    "truth_group_ids": ["shell"],
                }
            ]
        },
        "_source_member_counts": lambda _catalogue, _candidates: {"source": 2},
        "_hierarchy_diagnostics": lambda *_args: {"count": 1},
        "canonical_sha256": lambda value: f"digest-{len(str(value))}",
    }
    compiler = {
        "_dataset_maps": lambda _path: (
            {"dataset": dataset},
            {("dataset", 1): object()},
        ),
        "load_phase_five_corrective_a_review": lambda _path: object(),
        "_input_artifact_path": lambda _bundle, _path, role: tmp_path / role,
        "load_fits_plane": lambda _path: np.zeros((2, 2)),
        "np": np,
        "_truth_objects": lambda *_args: ((object(),), truth_labels),
        "fits": SimpleNamespace(getheader=lambda _path: object()),
        "_catalogue_and_labels": lambda _run: (
            (source,),
            publication_labels,
        ),
        "_candidate_objects": candidate_objects,
    }
    preparer = {"build_truth_linked_continuum_summary": build_summary}

    record = compile_tail(
        parent=parent,
        current=current,
        incumbent=incumbent,
        compiler_globals=compiler,
        historical_registry={
            "continuum_manifest_path": "manifest.json",
            "phase_five_review_path": "review.json",
        },
        repository_root=tmp_path,
        source_request=tmp_path / "request.json",
        smoke={"_measurement_label_plane": lambda _run: measurement_labels},
        preparer=preparer,
    )

    assert record["summary_count"] == 4
    assert reconstruction_planes == [
        measurement_labels,
        measurement_labels,
        publication_labels,
        publication_labels,
    ]
    for finder_id, publication_plane, association_plane in summary_planes:
        assert publication_plane is publication_labels
        if finder_id.endswith("hebog"):
            assert association_plane is measurement_labels
        else:
            assert association_plane is publication_labels
