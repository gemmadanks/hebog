"""The R6 plan is testable without a local campaign output directory."""

# pyright: reportPrivateUsage=false
# pyright: reportUnknownLambdaType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false

from __future__ import annotations

import hashlib
import importlib
import json
import runpy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from hebog.validation.external_runners import canonical_sha256, file_sha256

_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(_ROOT))
planning: Any = importlib.import_module(
    "scripts.validation.source_catalogue_replay_plan"
)


def test_frozen_r6_review_uses_committed_bytes_not_campaign_outputs() -> None:
    review_path = _ROOT / (
        "config/contracts/"
        "phase-5-source-catalogue-repair-cumulative-identity-review.json"
    )
    review = json.loads(review_path.read_bytes())
    authority = json.loads(
        (
            _ROOT / "config/contracts/"
            "phase-5-source-catalogue-repair-cumulative-execution-decision.json"
        ).read_bytes()
    )
    assert review["status"] == "frozen-non-executable"
    assert not any(review["authorizations"].values())
    assert authority["identity_review_sha256"] == file_sha256(review_path)
    assert authority["plan_sha256"] == review["plan_sha256"]
    assert authority["execution_count"] == 1
    assert (
        authority["expected_execution_sha256"]
        == (canonical_sha256(review["execution"]))
        == review["expected_execution_sha256"]
    )
    assert review["scientific_policy"]["binding_comparisons"] == 1187
    assert review["scientific_policy"]["bootstrap_resamples"] == 50000
    assert review["execution"]["pybdsf_executions"] == 0
    revision = review["execution"]["execution_revision"]
    for relative, expected in review["program_sha256"].items():
        contents = subprocess.run(
            ("git", "show", f"{revision}:{relative}"),
            cwd=_ROOT,
            check=True,
            capture_output=True,
        ).stdout
        assert hashlib.sha256(contents).hexdigest() == expected


def _census() -> dict[str, Any]:
    tasks = [
        {
            "input_id": f"fixture-{index}",
            "lane": "compact-blend" if index < 800 else "continuum",
            "dataset_identifier": f"group-{index // 400}",
        }
        for index in range(2400)
    ]
    return {
        "tasks": tasks,
        "workers": 2,
        "candidate_serial_executions": 2400,
        "incumbent_executions": 2400,
        "pybdsf_executions": 0,
        "existing_dask_comparisons": 12,
        "reference_run_count": 9600,
        "bootstrap_resamples": 50000,
        "bootstrap_seed": 20260810,
        "retained_references": {
            f"reference-{index}": {} for index in range(9600)
        },
        "dask_input_ids": planning.select_dask_inputs(tasks),
    }


def test_selection_matches_frozen_population_without_outputs() -> None:
    context = planning.evaluation_context(_ROOT)
    request = {
        "inputs": [
            {
                "input_id": f"{identifier}-seed-{seed}",
                "dataset_identifier": identifier,
                "lane": "compact-blend"
                if "compact-blend" in identifier
                else "continuum",
            }
            for identifier, seed in context["recipes"]
        ]
    }
    population = json.loads((_ROOT / planning.POPULATION).read_bytes())
    selected = planning.selected_inputs(request, population)
    assert len(selected) == 2400
    request["inputs"].pop()
    with pytest.raises(ValueError, match="population changed"):
        planning.selected_inputs(request, population)


@pytest.mark.parametrize(
    "defect", (None, "task", "count", "reference", "dask", "selection")
)
def test_frozen_census_and_dask_coverage_cannot_shrink(
    defect: str | None,
) -> None:
    plan = _census()
    if defect == "task":
        plan["tasks"].pop()
    elif defect == "count":
        plan["bootstrap_resamples"] = 1000
    elif defect == "reference":
        plan["retained_references"].pop("reference-0")
    elif defect == "dask":
        plan["dask_input_ids"][0] = "not-in-population"
    elif defect == "selection":
        plan["dask_input_ids"].reverse()
    if defect is None:
        planning.verify_census(plan)
        selected = [
            row
            for row in plan["tasks"]
            if row["input_id"] in plan["dask_input_ids"]
        ]
        assert len(selected) == 12
        assert {row["dataset_identifier"] for row in selected} == {
            row["dataset_identifier"] for row in plan["tasks"]
        }
    else:
        with pytest.raises(ValueError, match=r"census|shape|selection"):
            planning.verify_census(plan)


def test_document_bindings_reject_substitution_and_symlinks(
    tmp_path: Path,
) -> None:
    path = tmp_path / "record.json"
    path.write_text('{"original": true}\n')
    value = planning.binding(path)
    assert planning.read_bound(value) == {"original": True}
    path.write_text("{}\n")
    with pytest.raises(ValueError, match="changed"):
        planning.read_bound(value)
    link = tmp_path / "link.json"
    link.symlink_to(path)
    with pytest.raises(ValueError, match="regular file"):
        planning.binding(link)


@pytest.mark.parametrize(
    "defect",
    (
        None,
        "status",
        "started",
        "root",
        "revision",
        "origin",
        "source",
        "configuration",
        "runtime",
        "python",
    ),
)
def test_live_code_and_runtime_must_match_the_frozen_identity(  # noqa: C901
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    defect: str | None,
) -> None:
    plan: dict[str, Any] = {
        "status": "frozen-non-executable",
        "finder_execution_started": False,
        "execution_root": str(tmp_path),
        "execution_revision": "a" * 40,
        "candidate": {
            "source_tree_sha256": "b" * 64,
            "configuration_sha256": canonical_sha256({}),
        },
        "configuration": {},
        "runtime": {
            "dependency_inventory_sha256": "c" * 64,
            "python": "3.14.2",
        },
    }
    monkeypatch.setattr(
        planning, "repository_revision", lambda _root: "a" * 40
    )
    monkeypatch.setattr(planning, "source_tree_sha256", lambda _root: "b" * 64)
    monkeypatch.setattr(
        planning, "dependency_inventory_sha256", lambda: "c" * 64
    )
    monkeypatch.setattr(planning.platform, "python_version", lambda: "3.14.2")
    monkeypatch.setattr(
        planning,
        "hebog",
        SimpleNamespace(__file__=str(tmp_path / "src/hebog/__init__.py")),
    )
    if defect == "status":
        plan["status"] = "consumed"
    elif defect == "started":
        plan["finder_execution_started"] = True
    elif defect == "root":
        plan["execution_root"] = str(tmp_path / "other")
    elif defect == "revision":
        plan["execution_revision"] = "d" * 40
    elif defect == "origin":
        monkeypatch.setattr(
            planning,
            "hebog",
            SimpleNamespace(__file__=str(tmp_path / "other/hebog.py")),
        )
    elif defect == "source":
        plan["candidate"]["source_tree_sha256"] = "d" * 64
    elif defect == "configuration":
        plan["configuration"] = {"changed": True}
    elif defect == "runtime":
        plan["runtime"]["dependency_inventory_sha256"] = "d" * 64
    elif defect == "python":
        plan["runtime"]["python"] = "3.12.0"
    if defect is None:
        planning.verify_code_identity(plan, tmp_path)
    else:
        with pytest.raises(ValueError, match="R6"):
            planning.verify_code_identity(plan, tmp_path)


@pytest.mark.parametrize("defect", (None, "metadata", "scratch", "disk"))
def test_preflight_reads_all_native_files_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    defect: str | None,
) -> None:
    path = tmp_path / "metadata.json"
    path.write_text("{}\n")
    plan = _census()
    plan.update(
        {
            "scratch": str(tmp_path / "scratch"),
            "output": str(tmp_path / "terminal.json"),
            "metadata": {"fixture": planning.binding(path)},
            "admission": {"required_free_bytes": 100},
        }
    )
    for task in plan["tasks"]:
        task["input_manifest"] = planning.binding(path)
    for key in plan["retained_references"]:
        plan["retained_references"][key] = planning.binding(path)
    monkeypatch.setattr(planning, "verify_code_identity", lambda *_args: None)
    monkeypatch.setattr(planning, "verify_task_metadata", lambda *_args: None)
    monkeypatch.setattr(
        planning, "verify_historical_producer", lambda *_args: None
    )
    calls: list[Path] = []
    monkeypatch.setattr(
        planning, "native_artifacts", lambda path, _sha: calls.append(path)
    )
    monkeypatch.setattr(
        planning.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=99 if defect == "disk" else 1000),
    )
    if defect == "metadata":
        path.write_text('{"changed": true}\n')
    if defect == "scratch":
        Path(plan["scratch"]).mkdir()
    if defect is not None:
        with pytest.raises((ValueError, FileExistsError)):
            planning.verify_replay_plan(plan, tmp_path)
    else:
        planning.verify_replay_plan(plan, tmp_path)
        assert len(calls) == 12000
    assert not Path(plan["output"]).exists()
    assert Path(plan["scratch"]).exists() is (defect == "scratch")


@pytest.mark.parametrize("changed", (False, True))
def test_historical_probe_never_executes_a_finder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changed: bool,
) -> None:
    monkeypatch.setattr(
        planning,
        "repository_revision",
        lambda _root: (
            "wrong" if changed else planning.INCUMBENT["execution_revision"]
        ),
    )
    monkeypatch.setattr(
        planning,
        "source_tree_sha256",
        lambda _root: planning.INCUMBENT["source_tree_sha256"],
    )
    calls: list[Any] = []

    def run(command: tuple[str, ...], **kwargs: Any) -> None:
        assert "_historical_wrapper" in command[2]
        assert "_generate_product" not in command[2]
        assert kwargs["env"]["PYTHONPATH"] == str(tmp_path / "src")
        calls.append(command)

    monkeypatch.setattr(planning.subprocess, "run", run)
    if changed:
        with pytest.raises(ValueError, match="historical"):
            planning.verify_historical_producer(
                {"historical_root": str(tmp_path)}, _ROOT
            )
        assert not calls
    else:
        planning.verify_historical_producer(
            {"historical_root": str(tmp_path)}, _ROOT
        )
        assert len(calls) == 1


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.mark.parametrize(
    "defect", (None, "request", "source", "incumbent", "recipe")
)
def test_plan_builder_freezes_raw_reuse_without_any_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    defect: str | None,
) -> None:
    root = tmp_path / "repo"
    historical = tmp_path / "historical"
    historical.mkdir()
    candidate = {
        "revision": "a" * 40,
        "source_tree_sha256": "a" * 64,
        "configuration_sha256": canonical_sha256({}),
    }
    _write(
        root / planning.REVIEW,
        {"algorithm_candidate": candidate, "configuration": {}},
    )
    inputs: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    for lane in ("compact-blend", "continuum"):
        identifier = f"fixture-{lane}"
        relative = f"inputs/{identifier}"
        inputs.append(
            {
                "input_id": identifier,
                "lane": lane,
                "dataset_identifier": identifier,
                "seed": 1,
                "recipe_sha256": "b" * 64,
                "relative_directory": relative,
            }
        )
        _write(
            root / planning.REFERENCE / relative / "input.json",
            {
                "artifacts": [
                    {"role": role, "relative_path": f"{role}.fits"}
                    for role in ("image", "mean", "rms")
                ]
            },
        )
        for finder in (
            "hebog",
            "released-pybdsf",
            "pinned-pybdsf-master",
            "aegean",
        ):
            run = {
                "finder_id": finder,
                "mode": "candidate" if finder == "hebog" else "operational",
                "run_id": f"{identifier}-{finder}",
                "input_id": identifier,
                "relative_directory": f"results/{identifier}/{finder}",
            }
            runs.append(run)
            _write(
                root
                / planning.REFERENCE
                / run["relative_directory"]
                / "result.json",
                {
                    "configuration_sha256": "c" * 64,
                    "runtime": {
                        "name": finder,
                        "version": "fixture",
                        "source_revision": "d" * 40,
                        "container_image_digest": "sha256:" + "e" * 64,
                        "dependency_inventory_sha256": "f" * 64,
                    },
                },
            )
    _write(root / planning.REQUEST, {"inputs": inputs, "runs": runs})
    for relative in (
        planning.POPULATION,
        planning.REGISTRY,
        planning.BASELINE,
        planning.REFERENCE + "/recovery.json",
        "fixture-policy.json",
    ):
        _write(root / relative, {})
    expected = {
        relative: file_sha256(root / relative)
        for relative in planning.EXPECTED_FILES
    }
    monkeypatch.setattr(planning, "EXPECTED_FILES", expected)
    monkeypatch.setattr(
        planning,
        "selected_inputs",
        lambda request, _population: request["inputs"],
    )
    monkeypatch.setattr(
        planning, "verify_reference_identities", lambda *_args: None
    )
    monkeypatch.setattr(
        planning,
        "source_tree_sha256",
        lambda path: (
            planning.INCUMBENT["source_tree_sha256"]
            if path == historical
            else "wrong"
            if defect == "source"
            else candidate["source_tree_sha256"]
        ),
    )
    monkeypatch.setattr(
        planning,
        "repository_revision",
        lambda path: (
            "wrong"
            if defect == "incumbent"
            else planning.INCUMBENT["execution_revision"]
            if path == historical
            else "c" * 40
        ),
    )
    monkeypatch.setattr(
        planning,
        "load_cumulative_policy",
        lambda _root: (
            {
                "compact_manifest_path": "fixture-policy.json",
                "unused_non_path": True,
            },
            {"bootstrap_resamples": 50000, "bootstrap_seed": 20260810},
        ),
    )
    recipes = {(row["dataset_identifier"], 1): object() for row in inputs}
    if defect == "recipe":
        recipes.pop(("fixture-continuum", 1))
    monkeypatch.setattr(
        planning, "evaluation_context", lambda _root: {"recipes": recipes}
    )
    if defect == "request":
        _write(root / planning.REQUEST, {})
    kwargs = {
        "evidence_root": root,
        "execution_root": tmp_path / "execution",
        "historical_root": historical,
        "scratch": tmp_path / "scratch",
        "output": tmp_path / "terminal.json",
    }
    admission = {
        "required_free_bytes": 88 * 1024**3,
        "estimated_duration_hours": [10, 24],
        "estimate_is_guarantee": False,
    }
    if defect is not None:
        with pytest.raises(ValueError, match=r"identity|checkout|recipe"):
            planning.build_replay_plan(root, **kwargs, admission=admission)
    else:
        plan = planning.build_replay_plan(root, **kwargs, admission=admission)
        assert plan["admission"] == admission
        assert plan["finder_execution_started"] is False
        assert plan["status"] == "frozen-non-executable"
        assert len(plan["tasks"]) == 2
        assert len(plan["retained_references"]) == 6
        assert len(plan["implementations"]) == 5
        assert all("hebog" not in row["captures"] for row in plan["tasks"])
        assert plan["bootstrap_resamples"] == 50000
        assert plan["configuration"] == {}
    assert not kwargs["scratch"].exists()
    assert not kwargs["output"].exists()


@pytest.mark.parametrize("defect", (None, "request", "products"))
def test_reference_reuse_binds_original_ordered_product_sets(
    tmp_path: Path,
    defect: str | None,
) -> None:
    verifier = runpy.run_path(
        str(
            _ROOT
            / "scripts/validation/reconstruct_phase5_viewed_references.py"
        )
    )
    request = {
        "inputs": [{"input_id": "fixture", "relative_directory": "input"}],
        "runs": [
            {
                "run_id": "reference",
                "finder_id": "released-pybdsf",
                "relative_directory": "result",
            },
            {
                "run_id": "obsolete",
                "finder_id": "hebog",
                "relative_directory": "unused",
            },
        ],
    }
    for relative in (
        "input/input.json",
        "result/result.json",
        "recovery-request.json",
    ):
        _write(tmp_path / relative, {})
    terminal = {
        "request_sha256": file_sha256(tmp_path / "recovery-request.json"),
        "input_bundle_set_sha256": verifier["_identity_set_sha256"](
            (("fixture", tmp_path / "input/input.json"),)
        ),
        "reference_result_set_sha256": verifier["_identity_set_sha256"](
            (("reference", tmp_path / "result/result.json"),)
        ),
    }
    _write(tmp_path / "recovery.json", terminal)
    if defect is not None:
        _write(
            tmp_path
            / (
                "recovery-request.json"
                if defect == "request"
                else "result/result.json"
            ),
            {"substituted": True},
        )
        with pytest.raises(ValueError, match="changed"):
            planning.verify_reference_identities(_ROOT, request, tmp_path)
    else:
        planning.verify_reference_identities(_ROOT, request, tmp_path)


@pytest.mark.parametrize("dirty", (False, True))
def test_execution_revision_refuses_tracked_edits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dirty: bool,
) -> None:
    def command(args: tuple[str, ...], **_kwargs: Any) -> str | bytes:
        return (
            (b" M changed.py\n" if dirty else b"")
            if args[1] == "status"
            else "a" * 40 + "\n"
        )

    monkeypatch.setattr(planning.subprocess, "check_output", command)
    if dirty:
        with pytest.raises(ValueError, match="tracked changes"):
            planning.repository_revision(tmp_path)
    else:
        assert planning.repository_revision(tmp_path) == "a" * 40


@pytest.mark.parametrize(
    "defect", (None, "recipe", "root", "output", "input", "references")
)
@pytest.mark.parametrize("lane", ("compact-blend", "continuum"))
def test_task_metadata_prevents_late_recipe_and_capture_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    defect: str | None,
    lane: str,
) -> None:
    context = planning.evaluation_context(_ROOT)
    (dataset, seed), recipe = next(iter(context["recipes"].items()))
    digest = importlib.import_module(
        "hebog.validation.datasets"
    ).recipe_sha256(recipe)
    manifest = tmp_path / "input.json"
    _write(
        manifest,
        {
            "dataset_identifier": dataset,
            "seed": seed,
            "recipe_sha256": digest,
        },
    )
    task: dict[str, Any] = {
        "input_id": f"{dataset}-seed-{seed}",
        "lane": lane,
        "dataset_identifier": dataset,
        "seed": seed,
        "recipe_sha256": digest,
        "root": str(tmp_path),
        "configuration": {},
        "output_directory": str(tmp_path / "pairs" / f"{dataset}-seed-{seed}"),
        "input_manifest": planning.binding(manifest),
        "captures": {
            name: {"path": name, "sha256": "a" * 64}
            for name in ("aegean", "released-pybdsf", "pinned-pybdsf-master")
        },
    }
    plan: dict[str, Any] = {
        "execution_root": str(tmp_path),
        "scratch": str(tmp_path),
        "configuration": {},
        "tasks": [task],
        "retained_references": dict(task["captures"]),
    }
    if lane == "continuum":
        task["captures"].pop("aegean")
    monkeypatch.setattr(planning, "evaluation_context", lambda _root: context)
    if defect in ("recipe", "root", "output"):
        task[
            {
                "recipe": "recipe_sha256",
                "root": "root",
                "output": "output_directory",
            }[defect]
        ] = "wrong"
    elif defect == "input":
        record = json.loads(manifest.read_bytes())
        record["seed"] += 1
        _write(manifest, record)
        task["input_manifest"] = planning.binding(manifest)
    elif defect == "references":
        task["captures"].pop("released-pybdsf")
    if defect is None:
        planning.verify_task_metadata(plan, tmp_path)
    else:
        with pytest.raises(ValueError, match="task"):
            planning.verify_task_metadata(plan, tmp_path)
