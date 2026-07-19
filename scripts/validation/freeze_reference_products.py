"""Freeze stable products from reviewed release and master campaigns."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import cast

from hebog.validation.evidence import BenchmarkEvidence, load_evidence
from hebog.validation.products import (
    ProductArtifact,
    ReferenceProductManifest,
    ReferenceProductSet,
    write_reference_product_manifest,
)


def _parse_args() -> argparse.Namespace:
    """Parse the two reviewed campaigns and repository destinations."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--release-campaign", required=True, type=Path)
    parser.add_argument("--release-evidence", required=True, type=Path)
    parser.add_argument("--master-campaign", required=True, type=Path)
    parser.add_argument("--master-evidence", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    return parser.parse_args()


def _sha256(path: Path) -> str:
    """Return one complete artifact digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _checked_evidence(path: Path) -> BenchmarkEvidence:
    """Require reviewed benchmark evidence as the product provenance root."""
    evidence = load_evidence(path)
    if not isinstance(evidence, BenchmarkEvidence):
        raise TypeError(f"not benchmark evidence: {path}")
    if evidence.status.value != "reviewed":
        raise ValueError(
            f"reference products require reviewed evidence: {path}"
        )
    return evidence


def _freeze_set(
    *,
    repository_root: Path,
    campaign: Path,
    evidence: BenchmarkEvidence,
    reference: str,
    destination: Path,
) -> ReferenceProductSet:
    """Copy and bind one stable measured repetition to its evidence."""
    index = json.loads(
        (campaign / "baseline-index.json").read_text(encoding="utf-8")
    )
    measured_run_path = cast(list[str], index["runs"])[1]
    repetition_directory = (campaign / measured_run_path).parent
    raw = json.loads(
        (repetition_directory / "run.json").read_text(encoding="utf-8")
    )
    raw_artifacts = cast(dict[str, dict[str, object]], raw["artifacts"])
    product_destination = destination / reference
    product_destination.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    for name, identity in sorted(raw_artifacts.items()):
        artifact = Path(name)
        if (
            artifact.name != name
            or artifact.is_absolute()
            or ".." in artifact.parts
        ):
            raise ValueError(f"invalid artifact name: {name!r}")
        source = (repetition_directory / artifact).resolve()
        if not source.is_relative_to(repetition_directory.resolve()):
            raise ValueError(
                f"artifact path escapes repetition directory: {name!r}"
            )
        target = (product_destination / artifact).resolve()
        if not target.is_relative_to(product_destination.resolve()):
            raise ValueError(f"artifact target escapes destination: {name!r}")
        if target.exists() and _sha256(target) != _sha256(source):
            raise ValueError(f"existing frozen artifact differs: {target}")
        if not target.exists():
            shutil.copyfile(source, target)
        observed_sha = _sha256(target)
        if observed_sha != identity["sha256"]:
            raise ValueError(f"copied artifact digest changed: {target}")
        relative_path = target.resolve().relative_to(repository_root.resolve())
        artifacts[name] = ProductArtifact(
            relative_path=relative_path.as_posix(),
            bytes=target.stat().st_size,
            sha256=observed_sha,
        )
    return ReferenceProductSet(
        reference=reference,
        captured_at=evidence.captured_at,
        source_run_id=evidence.run_id,
        source_repetition_index=1,
        subject=evidence.subject,
        related_software=evidence.related_software,
        configuration_sha256=evidence.configuration_sha256,
        environment_sha256=evidence.environment_sha256,
        artifacts=artifacts,
    )


def main() -> None:
    """Freeze both reference sets and write their governed manifest."""
    args = _parse_args()
    repository_root = args.repository_root.resolve()
    destination = args.destination.resolve()
    if not destination.is_relative_to(repository_root):
        raise ValueError("destination must stay inside repository root")
    release = _checked_evidence(args.release_evidence)
    master = _checked_evidence(args.master_evidence)
    if release.dataset != master.dataset:
        raise ValueError("release and master evidence use different datasets")
    product_sets = tuple(
        _freeze_set(
            repository_root=repository_root,
            campaign=campaign,
            evidence=evidence,
            reference=reference,
            destination=destination,
        )
        for reference, campaign, evidence in (
            ("release", args.release_campaign, release),
            ("master", args.master_campaign, master),
        )
    )
    manifest = ReferenceProductManifest(
        schema_version=1,
        dataset=release.dataset,
        product_sets=product_sets,
    )
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    write_reference_product_manifest(args.manifest, manifest)


if __name__ == "__main__":
    main()
