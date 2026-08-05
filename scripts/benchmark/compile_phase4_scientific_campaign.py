"""Compile isolated Hebog and PyBDSF shards into paired campaign evidence."""

from __future__ import annotations

import argparse
from pathlib import Path

from hebog.validation.campaigns import compile_scientific_campaign
from hebog.validation.evidence import (
    CampaignImplementationEvidence,
    load_evidence,
    write_evidence,
)


def _parse_args() -> argparse.Namespace:
    """Parse ordered candidate/reference shard paths and output identity."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("shards", nargs="+", type=Path)
    return parser.parse_args()


def _load_shard(path: Path) -> CampaignImplementationEvidence:
    """Load one strict isolated implementation result."""
    evidence = load_evidence(path)
    if not isinstance(evidence, CampaignImplementationEvidence):
        raise TypeError(f"not a campaign implementation shard: {path}")
    return evidence


def main() -> None:
    """Compile the ordered candidate-first shards and write atomically."""
    args = _parse_args()
    if args.output.exists():
        raise FileExistsError(
            f"refusing to overwrite campaign evidence: {args.output}"
        )
    campaign = compile_scientific_campaign(
        run_id=args.run_id,
        shards=tuple(_load_shard(path) for path in args.shards),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_evidence(args.output, campaign)


if __name__ == "__main__":
    main()
