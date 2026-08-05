"""Run Hebog over a governed Phase 4 scientific campaign."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import sys
import time
import traceback
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from hebog.validation.campaign_runtime import (
    campaign_dataset_identity,
    canonical_sha256,
    contract_set_sha256,
    dataset_by_identifier,
    dependency_inventory_sha256,
    failure_from_exception,
    json_document,
    phase_four_outlier_thresholds,
    require_reviewed_qualification_inputs,
)
from hebog.validation.campaigns import diagnose_phase_four_realization
from hebog.validation.comparison import CatalogueOutlierThresholds
from hebog.validation.datasets import (
    DatasetRecord,
    SyntheticRecipe,
    iter_dataset_recipes,
)
from hebog.validation.evidence import (
    CampaignImplementationEvidence,
    CampaignImplementationIdentity,
    CampaignRealizationDiagnostic,
    EvidenceStatus,
    SoftwareIdentity,
    write_evidence,
)
from hebog.validation.hebog_campaign import (
    RecipeProcessor,
    hebog_campaign_configuration,
    process_hebog_recipe,
)

_hebog_configuration = hebog_campaign_configuration
_process_recipe = process_hebog_recipe

_MAXIMUM_REALIZATION_WORKERS = 32


@dataclass(frozen=True, slots=True)
class _RealizationWork:
    """One independent campaign image and its deterministic output path."""

    recipe: SyntheticRecipe
    dataset: DatasetRecord
    directory: Path
    implementation_identifier: str
    outlier_thresholds: CatalogueOutlierThresholds
    maximum_separation_beams: float
    position_angle_minimum_axis_ratio: float


def _run_realization(  # noqa: PLR0913
    recipe: SyntheticRecipe,
    dataset: DatasetRecord,
    directory: Path,
    *,
    implementation_identifier: str,
    outlier_thresholds: CatalogueOutlierThresholds,
    maximum_separation_beams: float,
    position_angle_minimum_axis_ratio: float,
    process_recipe: RecipeProcessor = _process_recipe,
) -> CampaignRealizationDiagnostic:
    """Run and diagnose one seed while retaining implementation failures."""
    try:
        candidate = process_recipe(recipe, dataset, directory)
    except Exception as error:
        traceback_text = traceback.format_exc()
        print(traceback_text, end="", file=sys.stderr, flush=True)
        return CampaignRealizationDiagnostic(
            implementation_identifier=implementation_identifier,
            seed=recipe.seed,
            status="failure",
            failure=failure_from_exception(
                error,
                stage="hebog-source-finding",
                traceback_text=traceback_text,
            ),
        )
    try:
        return diagnose_phase_four_realization(
            dataset,
            recipe,
            candidate,
            implementation_identifier=implementation_identifier,
            outlier_thresholds=outlier_thresholds,
            maximum_separation_beams=maximum_separation_beams,
            position_angle_minimum_axis_ratio=(
                position_angle_minimum_axis_ratio
            ),
        )
    except Exception as error:
        traceback_text = traceback.format_exc()
        print(traceback_text, end="", file=sys.stderr, flush=True)
        return CampaignRealizationDiagnostic(
            implementation_identifier=implementation_identifier,
            seed=recipe.seed,
            status="failure",
            failure=failure_from_exception(
                error,
                stage="campaign-comparison",
                traceback_text=traceback_text,
            ),
        )


def _execute_realization(
    work: _RealizationWork,
) -> CampaignRealizationDiagnostic:
    """Execute one pickleable campaign item with serial image science."""
    return _run_realization(
        work.recipe,
        work.dataset,
        work.directory,
        implementation_identifier=work.implementation_identifier,
        outlier_thresholds=work.outlier_thresholds,
        maximum_separation_beams=work.maximum_separation_beams,
        position_angle_minimum_axis_ratio=(
            work.position_angle_minimum_axis_ratio
        ),
    )


def _validate_realization_workers(value: int) -> int:
    """Require an explicit bounded image-level campaign allocation."""
    if (
        isinstance(value, bool)
        or not 1 <= value <= _MAXIMUM_REALIZATION_WORKERS
    ):
        raise ValueError("realization workers must be between 1 and 32")
    return value


def _realization_results(
    work: tuple[_RealizationWork, ...],
    workers: int,
) -> Iterator[CampaignRealizationDiagnostic]:
    """Preserve recipe order while optionally running independent images."""
    if workers == 1:
        for item in work:
            yield _execute_realization(item)
        return
    with ProcessPoolExecutor(max_workers=workers) as executor:
        yield from executor.map(_execute_realization, work)


def _parse_args() -> argparse.Namespace:
    """Parse one isolated candidate campaign request."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--scientific-gates", required=True, type=Path)
    parser.add_argument(
        "--scientific-contract",
        action="append",
        required=True,
        type=Path,
    )
    parser.add_argument("--comparison-protocol", required=True, type=Path)
    parser.add_argument("--implementation-id", default="hebog")
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--hebog-commit", required=True)
    parser.add_argument("--source-tree-sha256")
    parser.add_argument("--container-image-digest")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--realization-workers", default=1, type=int)
    parser.add_argument("--maximum-separation-beams", default=0.5, type=float)
    parser.add_argument(
        "--position-angle-minimum-axis-ratio",
        default=1.1,
        type=float,
    )
    return parser.parse_args()


def _run(args: argparse.Namespace) -> CampaignImplementationEvidence:
    """Run every governed seed and return one strict candidate shard."""
    observed_version = importlib.metadata.version("hebog")
    if observed_version != args.expected_version:
        raise RuntimeError(
            "installed Hebog version does not match the requested candidate: "
            f"expected {args.expected_version}, observed {observed_version}"
        )
    dataset = dataset_by_identifier(args.manifest, args.dataset_id)
    require_reviewed_qualification_inputs(
        dataset,
        scientific_contracts=args.scientific_contract,
        scientific_gates=args.scientific_gates,
        comparison_protocol=args.comparison_protocol,
    )
    configuration = _hebog_configuration()
    realization_workers = _validate_realization_workers(
        args.realization_workers
    )
    configuration["campaign_realization_workers"] = realization_workers
    outlier_thresholds = phase_four_outlier_thresholds(args.scientific_gates)
    started = time.perf_counter()
    realizations: list[CampaignRealizationDiagnostic] = []
    recipes = tuple(
        sorted(iter_dataset_recipes(dataset), key=lambda recipe: recipe.seed)
    )
    with TemporaryDirectory(prefix="hebog-phase4-candidate-") as temporary:
        root = Path(temporary)
        work = tuple(
            _RealizationWork(
                recipe=recipe,
                dataset=dataset,
                directory=root / f"seed-{recipe.seed}",
                implementation_identifier=args.implementation_id,
                outlier_thresholds=outlier_thresholds,
                maximum_separation_beams=args.maximum_separation_beams,
                position_angle_minimum_axis_ratio=(
                    args.position_angle_minimum_axis_ratio
                ),
            )
            for recipe in recipes
        )
        for item in work:
            item.directory.mkdir()
        for index, realization in enumerate(
            _realization_results(work, realization_workers)
        ):
            realizations.append(realization)
            print(
                json.dumps(
                    {
                        "completed": index + 1,
                        "elapsed_seconds": time.perf_counter() - started,
                        "total": len(recipes),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
    return CampaignImplementationEvidence(
        schema_version=1,
        evidence_type="scientific-campaign-implementation",
        run_id=args.run_id,
        captured_at=datetime.now(UTC),
        status=EvidenceStatus.EXPLORATORY,
        dataset=campaign_dataset_identity(dataset),
        configuration_sha256=contract_set_sha256(args.scientific_contract),
        comparison_protocol_sha256=canonical_sha256(
            json_document(args.comparison_protocol)
        ),
        implementation=CampaignImplementationIdentity(
            identifier=args.implementation_id,
            role="candidate",
            execution_configuration_sha256=canonical_sha256(configuration),
            software=SoftwareIdentity(
                name="hebog",
                version=observed_version,
                commit_sha=args.hebog_commit,
                source_tree_sha256=args.source_tree_sha256,
                container_image_digest=args.container_image_digest,
                dependency_inventory_sha256=dependency_inventory_sha256(),
            ),
        ),
        wall_seconds=time.perf_counter() - started,
        realizations=tuple(realizations),
    )


def main() -> None:
    """Run Hebog and atomically write its candidate evidence shard."""
    args = _parse_args()
    if args.output.exists():
        raise FileExistsError(
            f"refusing to overwrite campaign evidence: {args.output}"
        )
    evidence = _run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_evidence(args.output, evidence)


if __name__ == "__main__":
    main()
