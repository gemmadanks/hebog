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
import pytest

from hebog.validation.external_runners import canonical_sha256, file_sha256
from hebog.validation.external_successor_compiler import (
    ContinuumCatalogueObject,
    ContinuumTruthObject,
)
from hebog.validation.source_association_evaluation_repair import (
    AssociatedContinuumCatalogueObject,
)

_ROOT = Path(__file__).parents[3]
_REPAIR = (
    _ROOT
    / "scripts/validation/repair_phase5_prospective_paired_tail_diagnostics.py"
)
_EVALUATOR = (
    _ROOT / "scripts/validation/"
    "evaluate_phase5_prospective_paired_cumulative_tail_repair.py"
)
_PARENT_PREPARER = (
    _ROOT / "scripts/validation/prepare_phase5_prospective_paired_evidence.py"
)
_PREPARER = (
    _ROOT / "scripts/validation/"
    "prepare_phase5_prospective_paired_source_union_evidence.py"
)
_TOPOLOGY_EVALUATOR = (
    _ROOT / "scripts/validation/"
    "evaluate_phase5_prospective_paired_cumulative_topology_repair.py"
)
_SOURCE_UNION_TAIL = (
    _ROOT / "scripts/validation/"
    "repair_phase5_prospective_paired_source_union_tail.py"
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


def test_topology_evaluator_binds_repaired_preparer_and_parent() -> None:
    """The replacement evaluator exposes only the reviewed preparer change."""
    overlay = runpy.run_path(str(_TOPOLOGY_EVALUATOR))

    assert (
        file_sha256(overlay["_PARENT_EVALUATOR"])
        == overlay["_PARENT_EVALUATOR_SHA256"]
    )
    assert file_sha256(overlay["_PREPARER"]) == overlay["_PREPARER_SHA256"]
    assert Path(overlay["_PARENT_PREPARER"]).resolve() == (
        _PARENT_PREPARER.resolve()
    )
    assert (
        file_sha256(overlay["_SOURCE_UNION_TAIL"])
        == overlay["_SOURCE_UNION_TAIL_SHA256"]
    )
    evaluator = overlay["load_topology_repaired_evaluator"]()
    assert Path(evaluator["_PREPARER"]).resolve() == _PREPARER.resolve()
    assert (
        evaluator["_truth_linked_tail_record"]
        is not evaluator["_PREVIOUS_TRUTH_LINKED_TAIL_RECORD"]
    )
    assert (
        Path(evaluator["__file__"]).resolve() == _TOPOLOGY_EVALUATOR.resolve()
    )


def test_source_union_tail_uses_hebog_sidecar_and_preserves_reference_path(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Exact association provenance replaces only Hebog reconstruction."""
    repair = runpy.run_path(str(_SOURCE_UNION_TAIL))
    compile_tail = repair["truth_linked_tail_record"]
    globals_ = compile_tail.__globals__
    hebog_run = SimpleNamespace(result=SimpleNamespace(finder_id="hebog"))
    reference_run = SimpleNamespace(result=SimpleNamespace(finder_id="pybdsf"))
    sidecar = tmp_path / "association.json"
    association = object()
    calls: list[tuple[object, ...]] = []

    monkeypatch.setitem(
        globals_,
        "load_source_association",
        lambda path: calls.append(("load", path)) or association,
    )
    monkeypatch.setitem(
        globals_,
        "continuum_catalogue_objects_from_association",
        lambda *args, **kwargs: (
            calls.append(("associated", *args, kwargs))
            or ("associated-candidate",)
        ),
    )

    def parent_tail(
        *, compiler_globals: dict[str, Any], **_kwargs: Any
    ) -> Any:
        outputs: list[tuple[Any, ...]] = []
        for run in (hebog_run, reference_run):
            catalogue, labels = compiler_globals["_catalogue_and_labels"](run)
            outputs.append(
                compiler_globals["_candidate_objects"](
                    catalogue,
                    labels,
                    finder_id=run.result.finder_id,
                    header="header",
                )
            )
        return {"outputs": outputs}

    compiler = {
        "_catalogue_and_labels": lambda _run: (("catalogue",), "labels"),
        "_candidate_objects": lambda *_args, **kwargs: (
            "fallback",
            kwargs["finder_id"],
        ),
        "_artifact_path": lambda run, role: (
            calls.append(("artifact", run, role)) or sidecar
        ),
    }

    result = compile_tail(
        parent_tail=parent_tail,
        compiler_globals=compiler,
    )

    assert result["outputs"] == [
        ("associated-candidate",),
        ("fallback", "pybdsf"),
    ]
    assert calls[0] == ("artifact", hebog_run, "source-association-json")
    assert calls[1] == ("load", sidecar)
    associated_call = calls[2]
    assert associated_call[0] == "associated"
    assert associated_call[-1] == {"finder_id": "hebog", "header": "header"}


def test_source_union_tail_rejects_overlapping_run_context() -> None:
    """A changed caller order cannot reuse stale association provenance."""
    repair = runpy.run_path(str(_SOURCE_UNION_TAIL))
    compile_tail = repair["truth_linked_tail_record"]
    run = SimpleNamespace(result=SimpleNamespace(finder_id="hebog"))

    def parent_tail(
        *, compiler_globals: dict[str, Any], **_kwargs: Any
    ) -> Any:
        compiler_globals["_catalogue_and_labels"](run)
        compiler_globals["_catalogue_and_labels"](run)
        return {}

    with pytest.raises(ValueError, match="run context overlapped"):
        compile_tail(
            parent_tail=parent_tail,
            compiler_globals={
                "_catalogue_and_labels": lambda _run: ((), "labels"),
                "_candidate_objects": lambda *_args, **_kwargs: (),
                "_artifact_path": lambda *_args: Path("association.json"),
            },
        )


def test_source_union_tail_rejects_invalid_hebog_sidecar(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Invalid exact provenance cannot fall back to inferred membership."""
    repair = runpy.run_path(str(_SOURCE_UNION_TAIL))
    compile_tail = repair["truth_linked_tail_record"]
    globals_ = compile_tail.__globals__
    run = SimpleNamespace(result=SimpleNamespace(finder_id="hebog"))
    fallback_called = False

    def invalid_sidecar(_path: Path) -> object:
        raise ValueError("association sidecar is malformed")

    def fallback(*_args: Any, **_kwargs: Any) -> tuple[object, ...]:
        nonlocal fallback_called
        fallback_called = True
        return ()

    monkeypatch.setitem(globals_, "load_source_association", invalid_sidecar)

    def parent_tail(
        *, compiler_globals: dict[str, Any], **_kwargs: Any
    ) -> Any:
        catalogue, labels = compiler_globals["_catalogue_and_labels"](run)
        compiler_globals["_candidate_objects"](
            catalogue,
            labels,
            finder_id="hebog",
            header=object(),
        )
        return {}

    with pytest.raises(ValueError, match="association sidecar is malformed"):
        compile_tail(
            parent_tail=parent_tail,
            compiler_globals={
                "_catalogue_and_labels": lambda _run: ((), "labels"),
                "_candidate_objects": fallback,
                "_artifact_path": lambda *_args: tmp_path / "association.json",
            },
        )
    assert fallback_called is False


def test_source_union_tail_rejects_unconsumed_run_context() -> None:
    """Every captured run must be paired with one candidate conversion."""
    repair = runpy.run_path(str(_SOURCE_UNION_TAIL))
    compile_tail = repair["truth_linked_tail_record"]
    run = SimpleNamespace(result=SimpleNamespace(finder_id="hebog"))

    def parent_tail(
        *, compiler_globals: dict[str, Any], **_kwargs: Any
    ) -> Any:
        compiler_globals["_catalogue_and_labels"](run)
        return {}

    with pytest.raises(ValueError, match="run context was not consumed"):
        compile_tail(
            parent_tail=parent_tail,
            compiler_globals={
                "_catalogue_and_labels": lambda _run: ((), "labels"),
                "_candidate_objects": lambda *_args, **_kwargs: (),
                "_artifact_path": lambda *_args: Path("association.json"),
            },
        )


def test_source_union_tail_rejects_finder_context_mismatch() -> None:
    """A candidate conversion cannot consume another finder's sidecar."""
    repair = runpy.run_path(str(_SOURCE_UNION_TAIL))
    compile_tail = repair["truth_linked_tail_record"]
    run = SimpleNamespace(result=SimpleNamespace(finder_id="hebog"))

    def parent_tail(
        *, compiler_globals: dict[str, Any], **_kwargs: Any
    ) -> Any:
        catalogue, labels = compiler_globals["_catalogue_and_labels"](run)
        compiler_globals["_candidate_objects"](
            catalogue,
            labels,
            finder_id="pybdsf",
            header=object(),
        )
        return {}

    with pytest.raises(ValueError, match="run context changed"):
        compile_tail(
            parent_tail=parent_tail,
            compiler_globals={
                "_catalogue_and_labels": lambda _run: ((), "labels"),
                "_candidate_objects": lambda *_args, **_kwargs: (),
                "_artifact_path": lambda *_args: Path("association.json"),
            },
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


def test_tail_repair_exercises_real_multi_support_summary_seam(
    tmp_path: Path,
) -> None:
    """The repaired tail reaches the real source-union topology compiler."""
    repair = runpy.run_path(str(_REPAIR))
    compile_tail = repair["truth_linked_tail_record"]
    preparer = runpy.run_path(str(_PREPARER))
    dataset = SimpleNamespace(
        identifier="dataset",
        beam=SimpleNamespace(major_fwhm_pixels=2.0),
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
    publication_labels = np.asarray(((0, 9, 9),), dtype=np.int64)
    measurement_labels = np.asarray(((7, 9, 9),), dtype=np.int64)
    truth_labels = np.asarray(((1, 1, 1),), dtype=np.int64)
    truth = (
        ContinuumTruthObject(
            "truth",
            1,
            (1.0, 0.0),
            2.0,
            "astronomical-source",
            ("morphology-shell",),
        ),
    )
    source = SimpleNamespace(identifier="source", component_count=2)

    def candidate_objects(
        _catalogue: object,
        labels: np.ndarray[Any, Any],
        *,
        finder_id: str,
        **_kwargs: object,
    ) -> tuple[object, ...]:
        if finder_id == "hebog":
            assert labels is measurement_labels
            return (
                AssociatedContinuumCatalogueObject(
                    "source", (7, 9), (1.0, 0.0), 2.0
                ),
            )
        return (ContinuumCatalogueObject("source", 9, (1.0, 0.0), 2.0),)

    parent = {
        "_sentinel_memberships": lambda **_kwargs: {
            "continuum-input": [
                {
                    "sentinel_id": "morphology-shell",
                    "truth_group_ids": ["truth"],
                }
            ]
        },
        "_source_member_counts": lambda _catalogue, _candidates: {"source": 2},
        "_hierarchy_diagnostics": lambda *_args: {},
        "canonical_sha256": canonical_sha256,
    }
    compiler = {
        "_dataset_maps": lambda _path: (
            {"dataset": dataset},
            {("dataset", 1): object()},
        ),
        "load_phase_five_corrective_a_review": lambda _path: object(),
        "_input_artifact_path": lambda _bundle, _path, role: tmp_path / role,
        "load_fits_plane": lambda _path: np.zeros((1, 3)),
        "np": np,
        "_truth_objects": lambda *_args: (truth, truth_labels),
        "fits": SimpleNamespace(getheader=lambda _path: object()),
        "_catalogue_and_labels": lambda _run: (
            (source,),
            publication_labels,
        ),
        "_candidate_objects": candidate_objects,
    }

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
    assert record["finder_counts"] == {
        "current-hebog": 1,
        "incumbent-hebog": 1,
        "pinned-pybdsf-master": 1,
        "released-pybdsf": 1,
    }
    assert record["array_planes_retained"] is False
