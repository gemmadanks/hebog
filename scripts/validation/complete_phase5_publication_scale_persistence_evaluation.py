#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportPrivateUsage=false
"""Complete publication-scale-persistence evaluation from sealed products."""

from __future__ import annotations

import argparse
import json
import os
import runpy
import subprocess
from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from hebog.validation import parent_construction_association_evaluation
from hebog.validation.external_runners import canonical_sha256, file_sha256

_ROOT = Path(__file__).parents[2]
_CONSUMED_WRAPPER = (
    _ROOT / "scripts/validation/"
    "review_phase5_publication_scale_persistence_cumulative_regressions.py"
)
_SMOKE_EVALUATOR = (
    _ROOT / "scripts/validation/"
    "evaluate_phase5_prospective_publication_scale_persistence_smoke.py"
)
_FAILURE = (
    _ROOT / "config/contracts/"
    "phase-5-publication-scale-persistence-evaluation-completion-failure.json"
)
_PRE_REVIEW = (
    _ROOT / "config/contracts/"
    "phase-5-publication-scale-persistence-evaluation-completion-pre-review.json"
)
_IDENTITY_REVIEW = (
    _ROOT / "config/contracts/"
    "phase-5-publication-scale-persistence-evaluation-completion-review.json"
)
_EXECUTION_DECISION = (
    _ROOT / "config/contracts/"
    "phase-5-publication-scale-persistence-evaluation-completion-execution-"
    "decision.json"
)
_REFERENCE_RECONSTRUCTION = Path(
    "benchmark-results/phase-5/"
    "viewed-reference-reconstruction-public-finder-correction"
)
_CLOSED_BASELINE = Path(
    "benchmark-results/phase-5/cumulative-regression-ledger-recovery.json"
)
_OUTPUT = Path(
    "benchmark-results/phase-5/cumulative-regression-ledger-public-finder-"
    "publication-scale-persistence.json"
)
_SCRATCH = Path(
    "/private/tmp/hebog-phase5-public-finder-publication-scale-persistence-"
    "937737d"
)
_CANDIDATE_REVISION = "937737d811dd229d71dbcfdbda6cb5829de6faca"
_CANDIDATE_SOURCE_TREE_SHA256 = (
    "9f8e4a67f0c74ac86bff4f398811a7d64620fb70512b118c0ad3bb1eb58644c8"
)
_CANDIDATE_CONFIGURATION_SHA256 = (
    "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
)
_CANDIDATE_PRODUCT_SET_SHA256 = (
    "77a71b5fd537e30efd67a6a225c9d0b52d9bc9d56417437b10bd659539a013b1"
)
_CONSUMED_WRAPPER_SHA256 = (
    "a0fe32d360ce04bfcfed6cde0e7f19b509648637e2f57c6ea1c11a651b653cc1"
)
_SMOKE_EVALUATOR_SHA256 = (
    "f17aea97cbaf83c87a7e776e3eff9dd9d9eb78fda3fab10097af98c9a96af68d"
)
_REFERENCE_RECONSTRUCTION_SHA256 = (
    "48209eae94b7dfe66c5098feac56ac8be608c76b6b1a1c4f6c1ff35028c69cc2"
)
_CLOSED_BASELINE_SHA256 = (
    "a45303dfa8f544830a65988fc0b3371678b9cda37cd5f62d2b650163e5dbfbf9"
)
_EXPECTED_INPUT_COUNT = 2400
_EXPECTED_REFERENCE_RUN_COUNT = 9600
_WORKERS = 2
_PROHIBITED_AUTHORIZATIONS = (
    "candidate_execution_authorized",
    "cutover_authorized",
    "fresh_qualification_authorized",
    "optimization_authorized",
    "release_authorized",
    "rescoring_authorized",
    "threshold_or_margin_tuning_authorized",
    "viewed_data_execution_authorized",
)


def _load_json(path: Path, *, label: str) -> dict[str, object]:
    """Load one required JSON object."""
    if not path.is_file():
        raise ValueError(f"{label} is absent")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} is malformed")
    return cast(dict[str, object], value)


def _git_revision() -> str:
    """Return the clean immutable completion revision."""
    status = subprocess.check_output(
        ("git", "status", "--porcelain", "--untracked-files=all"),
        cwd=_ROOT,
        text=True,
    )
    if status:
        raise ValueError("evaluation completion requires a clean checkout")
    return subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=_ROOT, text=True
    ).strip()


def _artifact_records(
    directory: Path,
    marker: Mapping[str, object],
    *,
    lane: str,
) -> None:
    """Hash every declared artifact and reject role or filename drift."""
    artifacts = marker.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("candidate product artifacts are malformed")
    expected_roles = (
        {
            "measurement-labels-fits",
            "segment-catalogue-json",
            "segment-labels-fits",
            "segment-mask-fits",
            "source-association-json",
        }
        if lane == "continuum"
        else {"compact-catalogue-json"}
    )
    roles: set[str] = set()
    names = {"complete.json"}
    for value in artifacts:
        if not isinstance(value, dict):
            raise ValueError("candidate product artifacts are malformed")
        artifact = cast(Mapping[str, object], value)
        role = artifact.get("role")
        relative_value = artifact.get("relative_path")
        if (
            not isinstance(role, str)
            or not isinstance(relative_value, str)
            or Path(relative_value).name != relative_value
        ):
            raise ValueError("candidate product artifacts are malformed")
        path = directory / relative_value
        if (
            not path.is_file()
            or artifact.get("byte_count") != path.stat().st_size
            or artifact.get("sha256") != file_sha256(path)
        ):
            raise ValueError("candidate product artifact identity changed")
        roles.add(role)
        names.add(relative_value)
    if (
        roles != expected_roles
        or {item.name for item in directory.iterdir()} != names
    ):
        raise ValueError("candidate product artifact set changed")


def verify_existing_products(
    scratch: Path,
    expected_inputs: Sequence[tuple[str, str]],
) -> str:
    """Verify the exact complete product set without compiling science."""
    if (
        len(expected_inputs) != _EXPECTED_INPUT_COUNT
        or len({input_id for input_id, _lane in expected_inputs})
        != _EXPECTED_INPUT_COUNT
    ):
        raise ValueError("candidate product population changed")
    products = scratch / "products"
    progress = scratch / "progress.log"
    if (
        not products.is_dir()
        or not progress.is_file()
        or {item.name for item in scratch.iterdir()}
        != {"products", "progress.log"}
    ):
        raise ValueError("candidate scratch layout changed")
    expected = dict(expected_inputs)
    if {item.name for item in products.iterdir()} != set(expected):
        raise ValueError("candidate product population changed")
    markers: list[dict[str, object]] = []
    for input_id in sorted(expected):
        directory = products / input_id
        marker_path = directory / "complete.json"
        marker = _load_json(marker_path, label="candidate marker")
        if (
            marker.get("schema_version") != 1
            or marker.get("input_id") != input_id
            or marker.get("configuration_sha256")
            != _CANDIDATE_CONFIGURATION_SHA256
            or marker.get("source_tree_sha256")
            != _CANDIDATE_SOURCE_TREE_SHA256
        ):
            raise ValueError("candidate product identity changed")
        _artifact_records(directory, marker, lane=expected[input_id])
        markers.append(marker)
    lines = progress.read_text(encoding="utf-8").splitlines()
    completed = {
        line.rsplit(" input=", maxsplit=1)[1]
        for line in lines
        if " input=" in line
    }
    if len(lines) != _EXPECTED_INPUT_COUNT or completed != set(expected):
        raise ValueError("candidate progress record is incomplete")
    identity = canonical_sha256(markers)
    if identity != _CANDIDATE_PRODUCT_SET_SHA256:
        raise ValueError("candidate product-set identity changed")
    return identity


def _load_consumed_wrapper() -> dict[str, Any]:
    """Load the exact failed replay wrapper without executing it."""
    if file_sha256(_CONSUMED_WRAPPER) != _CONSUMED_WRAPPER_SHA256:
        raise ValueError("consumed replay wrapper changed")
    return runpy.run_path(str(_CONSUMED_WRAPPER))


def _verified_reference(
    consumed: Mapping[str, Any],
) -> Any:
    """Verify and return the exact retained reference reconstruction."""
    materializer = consumed["_load_materializer"]()
    verified, _request = materializer["_verified_reference"](
        _ROOT, _REFERENCE_RECONSTRUCTION
    )
    if (
        len(verified.inputs) != _EXPECTED_INPUT_COUNT
        or len(verified.runs) != _EXPECTED_REFERENCE_RUN_COUNT
        or verified.reference_reconstruction_sha256
        != _REFERENCE_RECONSTRUCTION_SHA256
    ):
        raise ValueError("retained reference reconstruction changed")
    return verified


def verify_completion(arguments: argparse.Namespace) -> dict[str, object]:
    """Verify exact evidence and products without compiling science."""
    expected_arguments = {
        "reference_reconstruction": _REFERENCE_RECONSTRUCTION,
        "closed_component_baseline_ledger": _CLOSED_BASELINE,
        "output": _OUTPUT,
        "scratch": _SCRATCH,
        "workers": _WORKERS,
    }
    for field, expected in expected_arguments.items():
        if getattr(arguments, field, None) != expected:
            raise ValueError(f"evaluation completion {field} changed")
    if arguments.output.exists():
        raise ValueError("evaluation completion output already exists")
    for path, expected, label in (
        (_SMOKE_EVALUATOR, _SMOKE_EVALUATOR_SHA256, "smoke evaluator"),
        (
            arguments.reference_reconstruction / "recovery.json",
            _REFERENCE_RECONSTRUCTION_SHA256,
            "reference reconstruction",
        ),
        (
            arguments.closed_component_baseline_ledger,
            _CLOSED_BASELINE_SHA256,
            "closed baseline",
        ),
    ):
        if not path.is_file() or file_sha256(path) != expected:
            raise ValueError(f"evaluation completion {label} changed")
    failure = _load_json(_FAILURE, label="failed execution")
    pre_review = _load_json(_PRE_REVIEW, label="repair pre-review")
    if (
        failure.get("status")
        != ("failed-after-complete-candidate-products-before-atomic-ledger")
        or pre_review.get("status") != "reviewed-evaluation-dispatch-repair"
    ):
        raise ValueError("evaluation completion failure boundary changed")
    consumed = _load_consumed_wrapper()
    verified = _verified_reference(consumed)
    _verify_mask_separation_seams(consumed)
    expected_inputs = tuple(
        (item.input_id, item.lane) for item in verified.request.inputs
    )
    product_set = verify_existing_products(arguments.scratch, expected_inputs)
    return {
        "candidate_configuration_sha256": (_CANDIDATE_CONFIGURATION_SHA256),
        "candidate_product_count": len(expected_inputs),
        "candidate_product_set_sha256": product_set,
        "candidate_revision": _CANDIDATE_REVISION,
        "candidate_source_tree_sha256": _CANDIDATE_SOURCE_TREE_SHA256,
        "closed_baseline_sha256": _CLOSED_BASELINE_SHA256,
        "completion_program_sha256": file_sha256(Path(__file__)),
        "consumed_wrapper_sha256": _CONSUMED_WRAPPER_SHA256,
        "failure_sha256": file_sha256(_FAILURE),
        "pre_review_sha256": file_sha256(_PRE_REVIEW),
        "reference_reconstruction_sha256": (
            verified.reference_reconstruction_sha256
        ),
        "reference_run_count": len(verified.runs),
        "smoke_evaluator_sha256": _SMOKE_EVALUATOR_SHA256,
        "status": "pass",
    }


def _validate_authority(
    verified: Mapping[str, object],
) -> dict[str, object]:
    """Require one exact evaluation-only review and execution decision."""
    review = _load_json(_IDENTITY_REVIEW, label="identity review")
    decision = _load_json(_EXECUTION_DECISION, label="execution decision")
    if (
        review.get("status") != "reviewed-evaluation-only-completion"
        or review.get("verified_composition") != dict(verified)
        or decision.get("status")
        != "authorized-for-one-evaluation-only-completion"
        or decision.get("evaluation_only_completion_authorized") is not True
    ):
        raise ValueError("evaluation-only completion is not authorized")
    prohibited = decision.get("prohibited_authorizations")
    if not isinstance(prohibited, dict) or prohibited != dict.fromkeys(
        _PROHIBITED_AUTHORIZATIONS, False
    ):
        raise ValueError("evaluation-only authorization boundary changed")
    identity = decision.get("identity_review")
    if not isinstance(identity, dict) or identity != {
        "path": str(_IDENTITY_REVIEW.relative_to(_ROOT)),
        "sha256": file_sha256(_IDENTITY_REVIEW),
    }:
        raise ValueError("evaluation-only identity review changed")
    for field in (
        "candidate_product_set_sha256",
        "completion_program_sha256",
        "consumed_wrapper_sha256",
        "reference_reconstruction_sha256",
        "closed_baseline_sha256",
        "smoke_evaluator_sha256",
    ):
        if decision.get(field) != verified[field]:
            raise ValueError(f"evaluation-only {field} changed")
    return {
        **dict(verified),
        "identity_review_sha256": file_sha256(_IDENTITY_REVIEW),
        "execution_decision_sha256": file_sha256(_EXECUTION_DECISION),
        "repair_execution_revision": _git_revision(),
    }


def _install_completion_only(
    frozen: dict[str, Any],
    expected_inputs: Sequence[tuple[str, str]],
) -> None:
    """Admit only verified completed shards and forbid candidate execution."""
    expected = dict(expected_inputs)
    completed = frozen["_completed_candidate"]

    def candidate_source_tree(_root: Path) -> str:
        return _CANDIDATE_SOURCE_TREE_SHA256

    def verify_tasks(
        tasks: tuple[dict[str, object], ...],
        *,
        workers: int,
        progress_path: Path,
    ) -> None:
        if (
            workers != _WORKERS
            or len(tasks) != _EXPECTED_INPUT_COUNT
            or progress_path != _SCRATCH / "progress.log"
            or {cast(str, task["input_id"]) for task in tasks} != set(expected)
        ):
            raise ValueError("evaluation-only task population changed")
        for task in tasks:
            input_id = cast(str, task["input_id"])
            if task.get("lane") != expected[input_id] or not completed(
                Path(cast(str, task["output_directory"])),
                input_id=input_id,
                configuration_sha256=cast(str, task["configuration_sha256"]),
                source_sha256=cast(str, task["source_tree_sha256"]),
            ):
                raise ValueError("candidate product identity changed")

    def candidate_execution_forbidden(_task: dict[str, object]) -> str:
        raise RuntimeError("evaluation completion forbids candidate execution")

    frozen["source_tree_sha256"] = candidate_source_tree
    frozen["_run_candidate_tasks"] = verify_tasks
    frozen["_generate_candidate_product"] = candidate_execution_forbidden


def _install_mask_separation(
    frozen: dict[str, Any],
) -> AbstractContextManager[None]:
    """Install the exact smoke-proven evaluation overlay in the full lane."""
    if file_sha256(_SMOKE_EVALUATOR) != _SMOKE_EVALUATOR_SHA256:
        raise ValueError("smoke evaluator changed")
    smoke_wrapper = runpy.run_path(str(_SMOKE_EVALUATOR))
    load_smoke = smoke_wrapper.get("_base")
    if not callable(load_smoke):
        raise ValueError("smoke evaluator composition seam changed")
    smoke = load_smoke(_ROOT)
    if not isinstance(smoke, dict):
        raise ValueError("smoke evaluator composition seam changed")
    context = smoke.get("_mask_measurement_separation_evaluation")
    install_separated = smoke.get("_install_mask_separated_compiler")
    original = frozen.get("_install_prospective_compiler")
    if (
        not callable(context)
        or not callable(install_separated)
        or not callable(original)
    ):
        raise ValueError("mask-separation evaluation seam changed")

    def install(
        compiler_globals: dict[str, Any],
        prospective: Any,
        configuration_sha256: str,
    ) -> None:
        original(compiler_globals, prospective, configuration_sha256)
        install_separated(
            compiler_globals,
            measurement_configuration=_CANDIDATE_CONFIGURATION_SHA256,
        )

    frozen["_install_prospective_compiler"] = install
    return cast(AbstractContextManager[None], context())


def _verify_mask_separation_seams(consumed: Mapping[str, Any]) -> None:
    """Exercise the exact full-lane overlay dispatch without science I/O."""
    frozen = cast(dict[str, Any], consumed["_current_composition"]())
    original = frozen.get("_install_prospective_compiler")
    if not callable(original) or original.__name__ != "install_terminal_cycle":
        raise ValueError("prospective compiler installation seam changed")
    compiler: dict[str, Any] = {}

    def install_historical(
        namespace: dict[str, Any],
        _prospective: Any,
        _configuration_sha256: str,
    ) -> None:
        namespace["_continuum_image_observations"] = lambda: None

    probe: dict[str, Any] = {
        "_install_prospective_compiler": install_historical,
    }
    historical_support = (
        parent_construction_association_evaluation._recorded_support_labels
    )
    with _install_mask_separation(probe):
        if (
            parent_construction_association_evaluation._recorded_support_labels.__name__
            != "_mask_separated_support_labels"
        ):
            raise ValueError("mask-separation support overlay changed")
        probe["_install_prospective_compiler"](
            compiler,
            object(),
            _CANDIDATE_CONFIGURATION_SHA256,
        )
        if type(compiler.get("_continuum_image_observations")).__name__ != (
            "_MaskSeparatedContinuumCompiler"
        ):
            raise ValueError("mask-separation compiler overlay changed")
    if (
        parent_construction_association_evaluation._recorded_support_labels
        is not historical_support
    ):
        raise ValueError("mask-separation support overlay was not restored")


def _install_provenance(
    frozen: dict[str, Any], provenance: Mapping[str, object]
) -> None:
    """Add exact repair provenance to the final ledger serializer."""
    original = frozen["_canonical_json_bytes"]

    def serialize(value: object) -> bytes:
        document = value
        if isinstance(value, dict) and value.get("ledger_id") == (
            "phase-5-cumulative-regression-ledger"
        ):
            document = {
                **value,
                "evaluation_completion_provenance": dict(provenance),
            }
        return cast(bytes, original(document))

    frozen["_canonical_json_bytes"] = serialize


def run_authorized_completion(arguments: argparse.Namespace) -> None:
    """Compile and evaluate the sealed products exactly once."""
    verified_composition = verify_completion(arguments)
    provenance = _validate_authority(verified_composition)
    consumed = _load_consumed_wrapper()
    verified = _verified_reference(consumed)
    expected_inputs = tuple(
        (item.input_id, item.lane) for item in verified.request.inputs
    )
    frozen = cast(dict[str, Any], consumed["_current_composition"]())
    _install_completion_only(frozen, expected_inputs)
    _install_provenance(frozen, provenance)
    temporary = arguments.output.with_name(
        f".{arguments.output.name}.{uuid4().hex}.tmp"
    )
    execution_arguments = argparse.Namespace(**vars(arguments))
    execution_arguments.output = temporary
    frozen["_parse_args"] = lambda: execution_arguments
    with _install_mask_separation(frozen):
        frozen["main"]()
    os.link(temporary, arguments.output)
    temporary.unlink()


def _parse_args() -> argparse.Namespace:
    """Parse the fixed existing-product completion namespace."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reference-reconstruction",
        type=Path,
        default=_REFERENCE_RECONSTRUCTION,
    )
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    parser.add_argument("--scratch", type=Path, default=_SCRATCH)
    parser.add_argument(
        "--closed-component-baseline-ledger",
        type=Path,
        default=_CLOSED_BASELINE,
    )
    parser.add_argument("--verify-only", action="store_true")
    arguments = parser.parse_args()
    arguments.workers = _WORKERS
    arguments.campaign = None
    return arguments


def main() -> None:
    """Verify without writes or run the one authorized completion."""
    arguments = _parse_args()
    if arguments.verify_only:
        print(
            json.dumps(
                verify_completion(arguments),
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
        )
        return
    run_authorized_completion(arguments)


if __name__ == "__main__":
    main()
