"""Evaluate large Phase 4 shards without co-resident Pydantic campaigns."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from hebog.validation.campaign_runtime import (
    contract_set_sha256,
    dataset_by_identifier,
    require_reviewed_qualification_inputs,
)
from hebog.validation.contracts import (
    load_paired_noninferiority_contract,
    load_phase_four_scientific_gates,
)
from hebog.validation.evidence import (
    CampaignImplementationEvidence,
    load_evidence,
    write_evidence,
)
from hebog.validation.phase_four_bounded import (
    canonical_evidence_file_sha256,
    evaluate_phase_four_qualification_summaries,
    file_sha256,
    load_implementation_summary,
    summarize_phase_four_implementation,
    write_implementation_summary,
)

_QUALIFICATION_IMPLEMENTATION_COUNT = 3


def _worker_parser() -> argparse.ArgumentParser:
    """Return the private one-shard summary parser."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--shard", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--scientific-gates", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def _evaluation_parser() -> argparse.ArgumentParser:
    """Return the public bounded-evaluation parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", required=True, type=Path)
    parser.add_argument("--campaign-file-sha256", required=True)
    parser.add_argument("--campaign-run-id", required=True)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument(
        "--scientific-contract",
        required=True,
        action="append",
        type=Path,
    )
    parser.add_argument("--scientific-gates", required=True, type=Path)
    parser.add_argument("--comparison-protocol", required=True, type=Path)
    parser.add_argument("--shard", required=True, action="append", type=Path)
    parser.add_argument(
        "--shard-file-sha256",
        required=True,
        action="append",
    )
    parser.add_argument("--candidate-id", default="hebog")
    parser.add_argument("--primary-reference-id", default="pybdsf-release")
    parser.add_argument("--secondary-reference-id", default="pybdsf-master")
    parser.add_argument("--output", required=True, type=Path)
    return parser


def _summarize_worker(arguments: argparse.Namespace) -> None:
    """Load one large shard, publish its bounded state, and exit."""
    evidence = load_evidence(arguments.shard)
    if not isinstance(evidence, CampaignImplementationEvidence):
        raise TypeError(
            f"not a campaign implementation shard: {arguments.shard}"
        )
    summary = summarize_phase_four_implementation(
        evidence,
        dataset_by_identifier(arguments.manifest, arguments.dataset_id),
        load_phase_four_scientific_gates(arguments.scientific_gates),
        source_shard_sha256=file_sha256(arguments.shard),
    )
    write_implementation_summary(arguments.output, summary)


def _require_hashes(
    paths: list[Path],
    expected_sha256: list[str],
    *,
    description: str,
) -> None:
    """Require one reviewed digest for every ordered input path."""
    if len(paths) != len(expected_sha256):
        raise ValueError(f"{description} paths and SHA-256 values differ")
    for path, expected in zip(paths, expected_sha256, strict=True):
        observed = file_sha256(path)
        if observed != expected:
            raise ValueError(
                f"{description} SHA-256 changed for {path}: {observed}"
            )


def _worker_command(
    arguments: argparse.Namespace,
    shard: Path,
    output: Path,
) -> list[str]:
    """Return one isolated child command for a large implementation shard."""
    return [
        sys.executable,
        str(Path(__file__).resolve()),
        "_summarize",
        "--shard",
        str(shard),
        "--manifest",
        str(arguments.manifest),
        "--dataset-id",
        arguments.dataset_id,
        "--scientific-gates",
        str(arguments.scientific_gates),
        "--output",
        str(output),
    ]


def _evaluate(arguments: argparse.Namespace) -> None:
    """Summarize each shard in isolation and publish one exact decision."""
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite qualification decision: {arguments.output}"
        )
    if len(arguments.shard) != _QUALIFICATION_IMPLEMENTATION_COUNT:
        raise ValueError("bounded evaluation requires exactly three shards")
    if file_sha256(arguments.campaign) != arguments.campaign_file_sha256:
        raise ValueError("compiled campaign file SHA-256 changed")
    _require_hashes(
        arguments.shard,
        arguments.shard_file_sha256,
        description="implementation shard",
    )
    dataset = dataset_by_identifier(arguments.manifest, arguments.dataset_id)
    require_reviewed_qualification_inputs(
        dataset,
        scientific_contracts=arguments.scientific_contract,
        scientific_gates=arguments.scientific_gates,
        comparison_protocol=arguments.comparison_protocol,
    )
    with TemporaryDirectory(prefix="hebog-phase4-bounded-") as temporary:
        temporary_root = Path(temporary)
        summary_paths = [
            temporary_root / f"summary-{index}.json"
            for index in range(_QUALIFICATION_IMPLEMENTATION_COUNT)
        ]
        for shard, summary_path in zip(
            arguments.shard,
            summary_paths,
            strict=True,
        ):
            subprocess.run(
                _worker_command(arguments, shard, summary_path),
                check=True,
            )
        summaries = tuple(
            load_implementation_summary(path) for path in summary_paths
        )
    decision = evaluate_phase_four_qualification_summaries(
        summaries,
        dataset,
        load_paired_noninferiority_contract(arguments.comparison_protocol),
        load_phase_four_scientific_gates(arguments.scientific_gates),
        scientific_contract_set_sha256=contract_set_sha256(
            arguments.scientific_contract
        ),
        source_campaign_run_id=arguments.campaign_run_id,
        source_campaign_sha256=canonical_evidence_file_sha256(
            arguments.campaign
        ),
        candidate_identifier=arguments.candidate_id,
        primary_reference_identifier=arguments.primary_reference_id,
        secondary_reference_identifier=arguments.secondary_reference_id,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    write_evidence(arguments.output, decision)


def main() -> None:
    """Dispatch a private shard worker or a complete bounded evaluation."""
    if len(sys.argv) > 1 and sys.argv[1] == "_summarize":
        _summarize_worker(_worker_parser().parse_args(sys.argv[2:]))
        return
    _evaluate(_evaluation_parser().parse_args())


if __name__ == "__main__":
    main()
