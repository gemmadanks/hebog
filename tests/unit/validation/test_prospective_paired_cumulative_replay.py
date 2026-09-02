"""Prospective paired cumulative replay and evaluator contracts."""

# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownLambdaType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import argparse
import json
import runpy
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest

from hebog.validation.prospective_science_contract import (
    load_prospective_endpoint_registry,
)

_ROOT = Path(__file__).parents[3]
_WRAPPER = (
    _ROOT / "scripts/validation/"
    "review_phase5_prospective_paired_cumulative_replay.py"
)
_EVALUATOR = (
    _ROOT / "scripts/validation/"
    "evaluate_phase5_prospective_paired_cumulative.py"
)
_REGISTRY = (
    _ROOT
    / "config/contracts/phase-5-prospective-science-endpoint-registry.json"
)
_TERMINAL = (
    _ROOT / "benchmark-results/phase-5/cumulative-regression-ledger-"
    "public-finder-publication-scale-persistence.json"
)
_MATERIALIZER = (
    _ROOT
    / "scripts/validation/materialize_phase5_prospective_paired_products.py"
)


def _namespace(value: object) -> object:
    """Convert decoded fixture records to attribute-bearing objects."""
    if isinstance(value, dict):
        return SimpleNamespace(
            **{key: _namespace(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_namespace(item) for item in value)
    return value


def _arguments(wrapper: dict[str, Any]) -> argparse.Namespace:
    """Return the exact future no-write invocation."""
    return argparse.Namespace(
        current_root=wrapper["_CURRENT_ROOT"],
        incumbent_root=wrapper["_INCUMBENT_ROOT"],
        reference_reconstruction=wrapper["_REFERENCE_RECONSTRUCTION"],
        current_scratch=wrapper["_CURRENT_SCRATCH"],
        incumbent_scratch=wrapper["_INCUMBENT_SCRATCH"],
        output=wrapper["_OUTPUT"],
        workers=2,
        verify_only=True,
    )


def test_complete_evaluator_emits_every_frozen_decision_section() -> None:
    """All 1,187 co-primary comparisons remain visible and binding."""
    evaluator = runpy.run_path(str(_EVALUATOR))
    terminal = json.loads(_TERMINAL.read_text(encoding="utf-8"))
    continuum = cast(
        tuple[Any, ...],
        _namespace(terminal["prospective_continuum_analysis"]),
    )
    incumbent = tuple(
        SimpleNamespace(
            **{
                **vars(endpoint),
                "comparisons": (
                    endpoint.comparisons
                    if endpoint.comparisons
                    else (
                        SimpleNamespace(
                            reference_id="pinned-pybdsf-master",
                            status="success",
                            observed_paired_standard_deviation=0.0,
                            positive_regression=0.0,
                            upper_confidence_limit=0.0,
                        ),
                    )
                ),
            }
        )
        for endpoint in continuum
    )
    decision = evaluator["compile_prospective_decision"](
        registry=load_prospective_endpoint_registry(_REGISTRY),
        current_continuum=continuum,
        incumbent_paired_continuum=incumbent,
        continuum_objectives=(),
        compact=terminal["prospective_compact"],
        compact_product_identity_equal=True,
        planning_deviation_by_family={},
        safety_results={
            "finite-measurements": True,
            "product-validity": True,
            "schema-and-provenance-integrity": True,
            "serial-and-existing-dask-determinism": True,
            "write-once-publication": True,
        },
    )

    assert decision["status"] == "pass"
    assert decision["section_counts"] == {
        "aegean_parity": 143,
        "binding_safety": 5,
        "incumbent_retention": 368,
        "longer_term_absolute_objectives": 15,
        "pybdsf_parity": 676,
    }
    assert sum(decision["comparison_status_counts"].values()) == 1187
    assert all(
        value["promotion_effect"] == "none-report-only"
        for value in decision["longer_term_absolute_objectives"]
    )


def test_wrapper_no_write_path_exercises_both_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The preflight verifies both 2,400-product task sets without writes."""
    wrapper = runpy.run_path(str(_WRAPPER))
    arguments = _arguments(wrapper)
    verify = wrapper["verify_replay"]
    globals_ = verify.__globals__
    modes: list[str] = []
    monkeypatch.setitem(globals_, "_require_invocation", lambda _args: None)
    monkeypatch.setitem(
        globals_, "_require_candidate_root", lambda *_args, **_kwargs: None
    )
    monkeypatch.setitem(
        globals_, "_verify_static_contracts", lambda: {"static": "pass"}
    )
    monkeypatch.setitem(
        globals_,
        "_verify_population_and_power",
        lambda: {
            "comparison_count": 1187,
            "input_count": 2400,
            "sentinel_membership_count": 160,
            "sentinel_unique_input_count": 155,
        },
    )

    def tasks(_arguments: object, *, mode: str, **_identity: object) -> int:
        modes.append(mode)
        return 2400

    monkeypatch.setitem(globals_, "_verify_candidate_tasks", tasks)
    monkeypatch.setitem(
        globals_,
        "file_sha256",
        lambda _path: wrapper["_REFERENCE_RECONSTRUCTION_SHA256"],
    )
    monkeypatch.setitem(
        globals_,
        "runpy",
        SimpleNamespace(
            run_path=lambda path: (
                {"compile_prospective_decision": lambda: None}
                if Path(path) == wrapper["_EVALUATOR"]
                else {
                    "build_truth_linked_continuum_summary": lambda: None,
                    "evaluate_prospective_cumulative_evidence": lambda: None,
                    "select_result_neutral_tail_sentinels": lambda: None,
                }
            )
        ),
    )
    reference = arguments.reference_reconstruction / "recovery.json"
    monkeypatch.setattr(Path, "is_file", lambda self: self == reference)

    record = verify(arguments)

    assert modes == ["current", "incumbent"]
    assert record["current_task_count"] == 2400
    assert record["incumbent_task_count"] == 2400
    assert record["reference_run_count"] == 9600
    assert record["candidate_execution_started"] is False


def test_wrapper_requires_a_separate_future_execution_decision() -> None:
    """The approved implementation decision cannot start the replay."""
    wrapper = runpy.run_path(str(_WRAPPER))

    with pytest.raises(ValueError, match="execution decision is absent"):
        wrapper["_require_execution_authority"](_arguments(wrapper))


def test_future_commands_keep_current_incumbent_and_evaluation_separate() -> (
    None
):
    """Each product set is materialized once before one atomic evaluation."""
    wrapper = runpy.run_path(str(_WRAPPER))
    commands = wrapper["_future_commands"](_arguments(wrapper))

    assert len(commands) == 3
    assert commands[0][commands[0].index("--candidate-mode") + 1] == "current"
    assert (
        commands[0][commands[0].index("--candidate-revision") + 1]
        == (wrapper["_CURRENT_REVISION"])
    )
    assert commands[1][-1] == "incumbent"
    assert "--output" in commands[2]
    assert "--verify-only" not in {
        item for command in commands for item in command
    }


def test_specialized_materializer_exposes_generalized_replay_helpers() -> None:
    """The final science override composes onto the complete producer CLI."""
    wrapper = runpy.run_path(str(_WRAPPER))

    materializer = wrapper["_load_materializer"]()

    assert callable(materializer["_selected_inputs"])
    assert callable(materializer["_candidate_tasks"])
    assert (
        materializer["_current_configuration"](_ROOT)
        == wrapper["_CURRENT_CONFIGURATION_SHA256"]
    )


def test_observation_recorder_binds_each_finder_and_rejects_duplicates() -> (
    None
):
    """A full replay cannot lose or overwrite realization statistics."""
    evaluator = runpy.run_path(str(_EVALUATOR))
    records: dict[tuple[str, str], dict[str, object]] = {}
    preparer = {
        "build_array_free_endpoint_summary": lambda **values: {
            "input_id": values["input_id"],
            "finder_id": values["finder_id"],
        }
    }
    callback = evaluator["_observation_callback"](
        records=records,
        preparer=preparer,
        hebog_finder_by_configuration={"current-config": "current-hebog"},
        allowed_finders=frozenset({"current-hebog"}),
    )
    run = SimpleNamespace(
        result=SimpleNamespace(
            finder_id="hebog", configuration_sha256="current-config"
        )
    )
    observations = {"endpoint": SimpleNamespace(image_key="continuum-input")}

    callback(run, observations)

    assert records == {
        ("current-hebog", "continuum-input"): {
            "input_id": "continuum-input",
            "finder_id": "current-hebog",
        }
    }
    with pytest.raises(ValueError, match="summary is duplicated"):
        callback(run, observations)


def test_endpoint_retention_requires_every_finder_realization() -> None:
    """Incomplete diagnostic retention fails before publication."""
    evaluator = runpy.run_path(str(_EVALUATOR))
    complete = {
        (finder, "input-1"): {
            "finder_id": finder,
            "input_id": "input-1",
        }
        for finder in (
            "current-hebog",
            "incumbent-hebog",
            "pinned-pybdsf-master",
            "released-pybdsf",
        )
    }

    record = evaluator["_endpoint_summary_record"](complete, expected_inputs=1)

    assert record["summary_count"] == 4
    assert record["finder_counts"] == dict.fromkeys(
        (
            "current-hebog",
            "incumbent-hebog",
            "pinned-pybdsf-master",
            "released-pybdsf",
        ),
        1,
    )
    complete.pop(("incumbent-hebog", "input-1"))
    with pytest.raises(ValueError, match="retention is incomplete"):
        evaluator["_endpoint_summary_record"](complete, expected_inputs=1)


@dataclass(frozen=True)
class _EndpointSpec:
    paired: bool = False


def test_incumbent_compiler_pairs_all_endpoints_and_records_observations(
    tmp_path: Path,
) -> None:
    """Incumbent retention includes signed axes without editing old smoke."""
    evaluator = runpy.run_path(str(_EVALUATOR))
    compiler_globals: dict[str, Any] = {}
    installed: list[tuple[object, str]] = []
    observed: list[tuple[object, object]] = []
    paired = object()
    run = object()
    historical = {
        "_install_prospective_compiler": (
            lambda _globals, campaign, configuration: installed.append(
                (campaign, configuration)
            )
        )
    }

    def install_parent_seams(value: dict[str, Any]) -> None:
        value["installed"] = True

    parent = {
        "_load_source_association_composition": lambda: ({}, {}, historical),
        "_install_terminal_parent_static_seams": install_parent_seams,
    }

    def observations(*_args: object) -> dict[str, object]:
        return {"endpoint": SimpleNamespace(image_key="input")}

    def compile_continuum(
        _campaign: object, _registry: object, _root: Path
    ) -> tuple[tuple[str, ...], tuple[()]]:
        assert compiler_globals["expand_continuum_endpoint_specs"](None)[
            0
        ].paired
        compiler_globals["_continuum_image_observations"](None, None, run)
        return ("compiled",), ()

    compiler_globals.update(
        {
            "expand_continuum_endpoint_specs": lambda _value: (
                _EndpointSpec(),
            ),
            "_continuum_image_observations": observations,
            "compile_continuum_campaign": compile_continuum,
        }
    )
    smoke = {
        "_compiler": lambda _value: (compiler_globals, object()),
        "_paired_incumbent_view": lambda *_args: paired,
        "_install_mask_separated_compiler": lambda *_args, **_kwargs: None,
    }

    result = evaluator["_compile_incumbent_pair"](
        parent=parent,
        current=object(),
        incumbent=object(),
        repository_root=tmp_path,
        current_configuration="current-configuration",
        smoke=smoke,
        observation_callback=lambda candidate_run, values: observed.append(
            (candidate_run, values)
        ),
    )

    assert result == ("compiled",)
    assert installed == [(paired, "current-configuration")]
    assert observed == [
        (run, {"endpoint": SimpleNamespace(image_key="input")})
    ]


@pytest.mark.parametrize("invalid", (0, True, "2400", None))
def test_paired_materializer_requires_positive_population_count(
    invalid: object,
) -> None:
    """The new full producer cannot inherit the old smoke cardinality."""
    materializer = runpy.run_path(str(_MATERIALIZER))
    population: dict[str, object] = {
        "selection": {"selected_input_count": invalid}
    }

    with pytest.raises(ValueError, match="selected input count"):
        materializer["_expected_selected_input_count_record"](population)


def test_paired_materializer_accepts_frozen_full_population_count() -> None:
    """The full producer reads the exact 2,400-input population contract."""
    materializer = runpy.run_path(str(_MATERIALIZER))

    assert (
        materializer["_expected_selected_input_count_record"](
            {"selection": {"selected_input_count": 2400}}
        )
        == 2400
    )


def test_tail_diagnostics_retain_each_finder_without_planes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Frozen sentinel inputs retain four truth-linked array-free summaries."""
    evaluator = runpy.run_path(str(_EVALUATOR))
    compile_tail = evaluator["_truth_linked_tail_record"]
    globals_ = compile_tail.__globals__
    monkeypatch.setitem(
        globals_,
        "_sentinel_memberships",
        lambda **_kwargs: {
            "continuum-input": [
                {
                    "sentinel_id": "morphology-shell",
                    "truth_group_ids": ["shell"],
                }
            ]
        },
    )
    monkeypatch.setitem(
        globals_, "_hierarchy_diagnostics", lambda *_args: {"count": 1}
    )
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
    labels = np.asarray(((0, 1), (0, 0)), dtype=np.int64)
    source = SimpleNamespace(identifier="source", component_count=2)
    candidate = SimpleNamespace(identifier="source")
    compiler = {
        "_dataset_maps": lambda _path: (
            {"dataset": dataset},
            {("dataset", 1): object()},
        ),
        "load_phase_five_corrective_a_review": lambda _path: object(),
        "_input_artifact_path": lambda _bundle, _path, role: tmp_path / role,
        "load_fits_plane": lambda _path: np.zeros((2, 2)),
        "np": np,
        "_truth_objects": lambda *_args: ((object(),), labels),
        "fits": SimpleNamespace(getheader=lambda _path: object()),
        "_catalogue_and_labels": lambda _run: ((source,), labels),
        "_candidate_objects": lambda *_args, **_kwargs: (candidate,),
    }
    preparer = {
        "build_truth_linked_continuum_summary": lambda **values: {
            "input_id": values["input_id"],
            "finder_id": values["finder_id"],
            "array_planes_retained": False,
            "record_sha256": "old",
        }
    }

    record = compile_tail(
        current=current,
        incumbent=incumbent,
        compiler_globals=compiler,
        historical_registry={
            "continuum_manifest_path": "manifest.json",
            "phase_five_review_path": "review.json",
        },
        repository_root=tmp_path,
        source_request=tmp_path / "request.json",
        smoke={"_measurement_label_plane": lambda _run: labels},
        preparer=preparer,
    )

    assert record["summary_count"] == 4
    assert record["finder_counts"] == dict.fromkeys(
        (
            "current-hebog",
            "incumbent-hebog",
            "pinned-pybdsf-master",
            "released-pybdsf",
        ),
        1,
    )
    assert record["array_planes_retained"] is False
    assert record["promotion_effect"] == "none-diagnostic-only"
