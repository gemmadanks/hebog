"""Compile a validated raw PyBDSF campaign into governed evidence."""

from __future__ import annotations

import argparse
from pathlib import Path

from hebog.validation.baselines import (
    BaselineEvidenceMetadata,
    compile_pybdsf_benchmark_evidence,
)
from hebog.validation.datasets import DatasetRole
from hebog.validation.evidence import (
    EvidenceStatus,
    WorkloadClass,
    write_evidence,
)


def _parse_args() -> argparse.Namespace:
    """Parse one explicit evidence compilation request."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign_directory", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--height", required=True, type=int)
    parser.add_argument("--width", required=True, type=int)
    parser.add_argument(
        "--dataset-role",
        choices=tuple(role.value for role in DatasetRole),
        required=True,
    )
    parser.add_argument(
        "--workload-class",
        choices=tuple(item.value for item in WorkloadClass),
        required=True,
    )
    parser.add_argument(
        "--status",
        choices=tuple(item.value for item in EvidenceStatus),
        default=EvidenceStatus.REVIEWED.value,
    )
    parser.add_argument(
        "--storage-identifier",
        default="host-bind-mounted-local-volume",
    )
    return parser.parse_args()


def main() -> None:
    """Compile and atomically write one typed evidence document."""
    args = _parse_args()
    evidence = compile_pybdsf_benchmark_evidence(
        args.campaign_directory,
        BaselineEvidenceMetadata(
            run_id=args.run_id,
            dataset_role=DatasetRole(args.dataset_role),
            shape_yx=(args.height, args.width),
            workload_class=WorkloadClass(args.workload_class),
            status=EvidenceStatus(args.status),
            storage_identifier=args.storage_identifier,
        ),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_evidence(args.output, evidence)


if __name__ == "__main__":
    main()
