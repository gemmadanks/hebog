# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Run one isolated PyBDSF implementation over a Phase 4 campaign."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import sys
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast

import numpy as np
from astropy.io import fits

from hebog.validation.campaign_runtime import (
    campaign_dataset_identity as _dataset_identity,
)
from hebog.validation.campaign_runtime import (
    canonical_sha256 as _canonical_sha256,
)
from hebog.validation.campaign_runtime import (
    contract_set_sha256 as _contract_set_sha256,
)
from hebog.validation.campaign_runtime import (
    dataset_by_identifier as _dataset_by_identifier,
)
from hebog.validation.campaign_runtime import (
    dependency_inventory_sha256 as _dependency_inventory_sha256,
)
from hebog.validation.campaign_runtime import (
    failure_from_exception as _failure_from_exception,
)
from hebog.validation.campaign_runtime import json_document as _json_document
from hebog.validation.campaign_runtime import (
    phase_four_outlier_thresholds as _outlier_thresholds,
)
from hebog.validation.campaign_runtime import (
    require_reviewed_qualification_inputs as _require_reviewed_inputs,
)
from hebog.validation.campaigns import diagnose_phase_four_realization
from hebog.validation.comparison import (
    CatalogueOutlierThresholds,
    CatalogueSource,
)
from hebog.validation.datasets import (
    DatasetRecord,
    DatasetRole,
    SyntheticRecipe,
    generate_synthetic_image,
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
from hebog.validation.materialization import synthetic_fits_header
from hebog.validation.products import load_pybdsf_catalogue


def _parse_args() -> argparse.Namespace:
    """Parse one isolated reference campaign request."""
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
    parser.add_argument("--implementation-id", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--pybdsf-commit", required=True)
    parser.add_argument("--container-image-digest", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--ncores", default=4, type=int)
    parser.add_argument("--maximum-separation-beams", default=0.5, type=float)
    parser.add_argument(
        "--position-angle-minimum-axis-ratio",
        default=1.1,
        type=float,
    )
    return parser.parse_args()


def _pybdsf_configuration(ncores: int) -> dict[str, object]:
    """Return the exact released Rapthor/LSMTool PyBDSF profile."""
    if ncores < 1:
        raise ValueError("ncores must be positive")
    return {
        "adaptive_rms_box": True,
        "adaptive_thresh": 75.0,
        "atrous_do": True,
        "atrous_jmax": 3,
        "mean_map": "zero",
        "ncores": ncores,
        "rms_box": [150, 50],
        "rms_box_bright": [35, 7],
        "rms_map": True,
        "thresh": "hard",
        "thresh_isl": 3.0,
        "thresh_pix": 5.0,
    }


def _write_input(
    path: Path,
    dataset: DatasetRecord,
    recipe: SyntheticRecipe,
) -> None:
    """Materialize the exact shared float64 image seen by PyBDSF."""
    image = generate_synthetic_image(recipe)
    fits.PrimaryHDU(
        data=np.asarray(image[np.newaxis, np.newaxis, :, :], dtype=np.float64),
        header=synthetic_fits_header(dataset),
    ).writeto(path)


def _process_recipe(
    bdsf_module: Any,
    recipe: SyntheticRecipe,
    dataset: DatasetRecord,
    directory: Path,
    configuration: dict[str, object],
) -> tuple[CatalogueSource, ...]:
    """Run the exact PyBDSF profile and read its source-list catalogue."""
    input_path = directory / "input.fits"
    catalogue_path = directory / "catalogue.fits"
    _write_input(input_path, dataset, recipe)
    image = bdsf_module.process_image(
        str(input_path),
        mean_map=configuration["mean_map"],
        rms_box=tuple(cast(list[int], configuration["rms_box"])),
        thresh_pix=configuration["thresh_pix"],
        thresh_isl=configuration["thresh_isl"],
        thresh=configuration["thresh"],
        adaptive_rms_box=configuration["adaptive_rms_box"],
        adaptive_thresh=configuration["adaptive_thresh"],
        rms_box_bright=tuple(cast(list[int], configuration["rms_box_bright"])),
        atrous_do=configuration["atrous_do"],
        atrous_jmax=configuration["atrous_jmax"],
        rms_map=configuration["rms_map"],
        quiet=True,
        ncores=configuration["ncores"],
        outdir=str(directory),
    )
    image.write_catalog(
        outfile=str(catalogue_path),
        format="fits",
        catalog_type="srl",
        clobber=True,
        force_output=True,
    )
    return load_pybdsf_catalogue(catalogue_path)


def _run_realization(  # noqa: PLR0913
    bdsf_module: Any,
    recipe: SyntheticRecipe,
    dataset: DatasetRecord,
    directory: Path,
    configuration: dict[str, object],
    *,
    implementation_identifier: str,
    outlier_thresholds: CatalogueOutlierThresholds,
    maximum_separation_beams: float,
    position_angle_minimum_axis_ratio: float,
) -> CampaignRealizationDiagnostic:
    """Run and diagnose one seed while preserving either failure stage."""
    try:
        candidate = _process_recipe(
            bdsf_module,
            recipe,
            dataset,
            directory,
            configuration,
        )
    except Exception as error:
        traceback_text = traceback.format_exc()
        print(traceback_text, end="", file=sys.stderr, flush=True)
        return CampaignRealizationDiagnostic(
            implementation_identifier=implementation_identifier,
            seed=recipe.seed,
            status="failure",
            failure=_failure_from_exception(
                error,
                stage="pybdsf-source-finding",
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
            failure=_failure_from_exception(
                error,
                stage="campaign-comparison",
                traceback_text=traceback_text,
            ),
        )


def _run(
    args: argparse.Namespace, bdsf_module: Any
) -> CampaignImplementationEvidence:
    """Run every governed seed and return one strict reference shard."""
    observed_version = importlib.metadata.version("bdsf")
    if observed_version != args.expected_version:
        raise RuntimeError(
            "installed PyBDSF version does not match the requested reference: "
            f"expected {args.expected_version}, observed {observed_version}"
        )
    dataset = _dataset_by_identifier(args.manifest, args.dataset_id)
    if dataset.role not in {DatasetRole.REGRESSION, DatasetRole.QUALIFICATION}:
        raise ValueError(
            "Phase 4 reference campaigns require regression or "
            "qualification data"
        )
    _require_reviewed_inputs(
        dataset,
        scientific_contracts=args.scientific_contract,
        scientific_gates=args.scientific_gates,
        comparison_protocol=args.comparison_protocol,
    )
    configuration = _pybdsf_configuration(args.ncores)
    outlier_thresholds = _outlier_thresholds(args.scientific_gates)
    started = time.perf_counter()
    realizations: list[CampaignRealizationDiagnostic] = []
    recipes = tuple(
        sorted(iter_dataset_recipes(dataset), key=lambda recipe: recipe.seed)
    )
    with TemporaryDirectory(prefix="hebog-phase4-pybdsf-") as temporary:
        root = Path(temporary)
        for index, recipe in enumerate(recipes):
            directory = root / f"seed-{recipe.seed}"
            directory.mkdir()
            realizations.append(
                _run_realization(
                    bdsf_module,
                    recipe,
                    dataset,
                    directory,
                    configuration,
                    implementation_identifier=args.implementation_id,
                    outlier_thresholds=outlier_thresholds,
                    maximum_separation_beams=args.maximum_separation_beams,
                    position_angle_minimum_axis_ratio=(
                        args.position_angle_minimum_axis_ratio
                    ),
                )
            )
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
        dataset=_dataset_identity(dataset),
        configuration_sha256=_contract_set_sha256(args.scientific_contract),
        comparison_protocol_sha256=_canonical_sha256(
            _json_document(args.comparison_protocol)
        ),
        implementation=CampaignImplementationIdentity(
            identifier=args.implementation_id,
            role="reference",
            execution_configuration_sha256=_canonical_sha256(configuration),
            software=SoftwareIdentity(
                name="pybdsf",
                version=observed_version,
                commit_sha=args.pybdsf_commit,
                container_image_digest=args.container_image_digest,
                dependency_inventory_sha256=(_dependency_inventory_sha256()),
            ),
        ),
        wall_seconds=time.perf_counter() - started,
        realizations=tuple(realizations),
    )


def main() -> None:
    """Run one isolated PyBDSF reference and atomically write its shard."""
    args = _parse_args()
    if args.output.exists():
        raise FileExistsError(
            f"refusing to overwrite campaign evidence: {args.output}"
        )
    import bdsf  # type: ignore[import-not-found]  # noqa: PLC0415

    evidence = _run(args, bdsf)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_evidence(args.output, evidence)


if __name__ == "__main__":
    main()
