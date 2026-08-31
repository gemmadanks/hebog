#!/usr/bin/env python3
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Materialize an exact Hebog candidate on the frozen smoke population."""

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from hebog.validation.external_runners import (
    ExternalRuntimeIdentity,
    canonical_sha256,
    source_tree_sha256,
)

_TERMINAL_PARENT_WRAPPER = (
    "scripts/validation/review_phase5_public_finder_terminal_parent_"
    "correction_cumulative_regressions.py"
)
_TERMINAL_FEATURE_WRAPPER = (
    "scripts/validation/review_phase5_public_finder_terminal_feature_"
    "persistence_cumulative_regressions.py"
)
_EXPECTED_SMOKE_INPUT_COUNT = 128


def _current_configuration(root: Path) -> str:
    """Return the exact terminal-cycle scientific configuration."""
    from hebog.validation.public_finder_correction import (  # noqa: PLC0415
        public_finder_terminal_cycle_eligibility_configuration,
    )

    paths = (
        "config/contracts/phase-5-corrective-a-review.json",
        "config/contracts/phase-5-public-finder-correction.json",
        "config/contracts/phase-5-public-finder-source-reconstruction-pre-review.json",
        "config/contracts/phase-5-public-finder-source-reconstruction-implementation-decision.json",
        "config/contracts/phase-5-public-finder-source-reconstruction-root-cause-pre-review.json",
        "config/contracts/phase-5-public-finder-source-reconstruction-root-cause-repair-implementation-decision.json",
        "config/contracts/phase-5-public-finder-source-hierarchy-parent-construction-pre-review.json",
        "config/contracts/phase-5-public-finder-source-hierarchy-parent-construction-implementation-decision.json",
        "docs/reference/phase-5-public-finder-persistent-support-parent-correction.md",
        "config/contracts/phase-5-public-finder-terminal-parent-correction-implementation-decision.json",
        "config/contracts/phase-5-public-finder-terminal-feature-persistence-pre-review.json",
        "config/contracts/phase-5-public-finder-terminal-feature-persistence-implementation-decision.json",
        "config/contracts/phase-5-public-finder-terminal-cycle-eligibility-pre-review.json",
        "config/contracts/phase-5-public-finder-terminal-cycle-eligibility-implementation-decision.json",
    )
    configuration = public_finder_terminal_cycle_eligibility_configuration(
        *(root / path for path in paths)
    )
    return canonical_sha256(configuration)


def _selected_inputs(request_path: Path, population_path: Path) -> set[str]:
    """Resolve the frozen result-neutral selection without new imports."""
    population = json.loads(population_path.read_text(encoding="utf-8"))
    request = json.loads(request_path.read_text(encoding="utf-8"))
    source = population["source_request"]
    selection = population["selection"]
    from hebog.validation.external_runners import file_sha256  # noqa: PLC0415

    if file_sha256(request_path) != source["sha256"]:
        raise ValueError("prospective smoke source request changed")
    groups: dict[tuple[str, str], list[str]] = {}
    for value in request["inputs"]:
        key = (value["lane"], value["dataset_identifier"])
        groups.setdefault(key, []).append(value["input_id"])
    selected: list[str] = []
    for (lane, _dataset), identifiers in sorted(groups.items()):
        count = (
            selection["compact_count"]
            if lane == "compact-blend"
            else selection["continuum_count_per_dataset"]
        )
        selected.extend(
            sorted(
                identifiers,
                key=lambda item: (
                    hashlib.sha256(item.encode()).hexdigest(),
                    item,
                ),
            )[:count]
        )
    ordered = tuple(sorted(selected))
    if (
        canonical_sha256(ordered)
        != selection["selected_input_set_canonical_sha256"]
    ):
        raise ValueError("prospective smoke selected input set changed")
    return set(ordered)


def _current_composition(
    root: Path,
    *,
    revision: str,
    configuration: str,
) -> dict[str, Any]:
    """Install the exact current producer over the last closed wrapper."""
    from hebog.validation.terminal_cycle_eligibility_evaluation import (  # noqa: PLC0415
        install_terminal_cycle_eligibility_evaluation,
    )

    wrapper = runpy.run_path(str(root / _TERMINAL_FEATURE_WRAPPER))
    _, _, frozen = wrapper["_load_source_association_composition"]()
    wrapper["_install_terminal_feature_persistence_static_seams"](frozen)
    previous_identity = frozen["_candidate_runtime_identity"]
    runtime = previous_identity(wrapper["_CANDIDATE_REVISION"])

    def candidate_identity(value: str) -> ExternalRuntimeIdentity:
        if value != revision:
            raise ValueError("prospective candidate revision changed")
        return ExternalRuntimeIdentity(
            name=runtime.name,
            version=runtime.version,
            source_revision=revision,
            container_image_digest=runtime.container_image_digest,
            dependency_inventory_sha256=runtime.dependency_inventory_sha256,
        )

    frozen["_CANDIDATE_REVISION"] = revision
    frozen["_candidate_configuration_sha256"] = lambda: configuration
    frozen["_candidate_runtime_identity"] = candidate_identity
    previous_installer = frozen["_install_prospective_compiler"]

    def install_terminal_cycle(
        compiler_globals: dict[str, Any],
        prospective: Any,
        configuration_sha256: str,
    ) -> None:
        previous_installer(compiler_globals, prospective, configuration_sha256)
        install_terminal_cycle_eligibility_evaluation(
            compiler_globals,
            association_path=wrapper["_association_artifact_path"],
        )

    frozen["_install_prospective_compiler"] = install_terminal_cycle
    return cast(dict[str, Any], frozen)


def _composition(task: dict[str, object]) -> dict[str, Any]:
    """Load one candidate's exact producer inside a worker."""
    tooling_root = Path(cast(str, task["tooling_root"]))
    mode = cast(str, task["candidate_mode"])
    if mode == "incumbent":
        wrapper = runpy.run_path(str(tooling_root / _TERMINAL_PARENT_WRAPPER))
        _, _, frozen = wrapper["_load_source_association_composition"]()
        wrapper["_install_terminal_parent_static_seams"](frozen)
        return cast(dict[str, Any], frozen)
    if mode == "current":
        return _current_composition(
            tooling_root,
            revision=cast(str, task["candidate_revision"]),
            configuration=cast(str, task["configuration_sha256"]),
        )
    raise ValueError("prospective candidate mode is unsupported")


def _generate_product(task: dict[str, object]) -> str:
    """Materialize one restartable product in a spawned worker."""
    frozen = _composition(task)
    candidate_task = {
        key: value
        for key, value in task.items()
        if key
        not in {
            "candidate_mode",
            "candidate_revision",
            "repository_root",
            "tooling_root",
        }
    }
    return cast(str, frozen["_generate_candidate_product"](candidate_task))


def _verified_reference(
    root: Path, reference: Path
) -> tuple[Any, dict[str, Any]]:
    """Verify all retained inputs and references through the frozen wrapper."""
    wrapper = runpy.run_path(str(root / _TERMINAL_PARENT_WRAPPER))
    arguments = SimpleNamespace(
        campaign=None,
        reference_reconstruction=reference,
        closed_component_baseline_ledger=(
            Path(
                "benchmark-results/phase-5/cumulative-regression-ledger-recovery.json"
            )
        ),
    )
    verified = wrapper["_verify_reference_reconstruction"](arguments)
    _, _, frozen = wrapper["_load_source_association_composition"]()
    return verified, cast(dict[str, Any], frozen)


def _candidate_tasks(
    arguments: argparse.Namespace,
) -> tuple[dict[str, object], ...]:
    """Return exactly the selected candidate tasks after full verification."""
    candidate_root = arguments.repository_root
    tooling_root = arguments.tooling_root
    verified, frozen = _verified_reference(
        tooling_root, arguments.reference_reconstruction
    )
    compiler = runpy.run_path(str(frozen["_COMPILER_PATH"]))
    frozen["_install_historical_source_view"](compiler)
    terminal = compiler["_configured_terminal"]()
    compiler_globals = terminal["compile_terminal_analysis"].__globals__
    registry = compiler_globals["load_endpoint_registry"](
        frozen["_REGISTRY_PATH"], frozen["_COMPILER_PATH"]
    )
    compact, _ = compiler_globals["_dataset_maps"](
        tooling_root / registry["compact_manifest_path"]
    )
    continuum, _ = compiler_globals["_dataset_maps"](
        tooling_root / registry["continuum_manifest_path"]
    )
    selected = _selected_inputs(
        arguments.source_request,
        arguments.population,
    )
    if arguments.candidate_mode == "current":
        configuration = _current_configuration(candidate_root)
        revision = subprocess.check_output(
            ("git", "rev-parse", "HEAD"), cwd=candidate_root, text=True
        ).strip()
        expected_source_sha256 = None
    else:
        wrapper = runpy.run_path(str(tooling_root / _TERMINAL_PARENT_WRAPPER))
        configuration = cast(str, wrapper["_CANDIDATE_CONFIGURATION_SHA256"])
        revision = cast(str, wrapper["_CANDIDATE_REVISION"])
        expected_source_sha256 = cast(
            str, wrapper["_CANDIDATE_SOURCE_TREE_SHA256"]
        )
    source_sha256 = source_tree_sha256(candidate_root)
    if (
        expected_source_sha256 is not None
        and source_sha256 != expected_source_sha256
    ):
        raise ValueError("prospective incumbent source tree changed")
    tasks = frozen["_candidate_tasks"](
        verified,
        {**compact, **continuum},
        arguments.scratch,
        configuration_sha256=configuration,
        source_sha256=source_sha256,
    )
    return tuple(
        {
            **task,
            "candidate_mode": arguments.candidate_mode,
            "candidate_revision": revision,
            "repository_root": str(candidate_root),
            "tooling_root": str(tooling_root),
        }
        for task in tasks
        if task["input_id"] in selected
    )


def main() -> None:
    """Verify, materialize, and retain exactly one smoke product set."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--tooling-root", required=True, type=Path)
    parser.add_argument("--reference-reconstruction", required=True, type=Path)
    parser.add_argument("--source-request", required=True, type=Path)
    parser.add_argument("--population", required=True, type=Path)
    parser.add_argument("--scratch", required=True, type=Path)
    parser.add_argument(
        "--candidate-mode", choices=("current", "incumbent"), required=True
    )
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="verify every frozen dependency without creating scratch data",
    )
    arguments = parser.parse_args()
    arguments.repository_root = arguments.repository_root.resolve()
    arguments.tooling_root = arguments.tooling_root.resolve()
    if arguments.workers < 1:
        raise ValueError(
            "prospective materialization workers must be positive"
        )
    tasks = _candidate_tasks(arguments)
    if len(tasks) != _EXPECTED_SMOKE_INPUT_COUNT:
        raise ValueError("prospective smoke task count differs")
    identities = {
        "candidate_mode": arguments.candidate_mode,
        "candidate_revision": tasks[0]["candidate_revision"],
        "candidate_source_tree_sha256": tasks[0]["source_tree_sha256"],
        "candidate_configuration_sha256": tasks[0]["configuration_sha256"],
        "selected_input_count": len(tasks),
    }
    if arguments.verify_only:
        if arguments.scratch.exists():
            raise FileExistsError(
                "prospective verify-only scratch path already exists"
            )
        print(json.dumps(identities, allow_nan=False, sort_keys=True))
        return
    arguments.scratch.mkdir(parents=True, exist_ok=False)
    progress_path = arguments.scratch / "progress.log"
    with (
        progress_path.open("a", encoding="utf-8") as progress,
        ProcessPoolExecutor(max_workers=arguments.workers) as executor,
    ):
        futures = {executor.submit(_generate_product, task) for task in tasks}
        for completed, future in enumerate(as_completed(futures), start=1):
            input_id = future.result()
            progress.write(
                f"{datetime.now(UTC).isoformat()} "
                f"completed={completed}/{_EXPECTED_SMOKE_INPUT_COUNT} "
                f"input={input_id}\n"
            )
            progress.flush()
    print(json.dumps(identities, allow_nan=False, sort_keys=True))
    print(arguments.scratch)


if __name__ == "__main__":
    main()
