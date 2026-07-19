"""Persist the scientific difference between frozen PyBDSF references."""

from __future__ import annotations

import argparse
from pathlib import Path

from hebog.validation.comparison import (
    compare_catalogues,
    compare_masks,
    compare_rms_maps,
)
from hebog.validation.evidence import (
    EvidenceStatus,
    ScientificComparisonEvidence,
    write_evidence,
)
from hebog.validation.products import (
    ProductName,
    ReferenceProductSet,
    canonical_product_set_sha256,
    load_fits_plane,
    load_mask_plane,
    load_pybdsf_catalogue,
    load_reference_product_manifest,
    product_set_by_reference,
    validate_reference_product_files,
)

_BEAM_FWHM_DEGREES = 0.001111111111111111
_MAXIMUM_SEPARATION_BEAMS = 0.5


def _parse_args() -> argparse.Namespace:
    """Parse repository-relative manifest and evidence destinations."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def _path(
    root: Path, product_set: ReferenceProductSet, name: ProductName
) -> Path:
    """Resolve one product from its governed repository-relative path."""
    return root / product_set.artifacts[name].relative_path


def main() -> None:
    """Compare master to release and persist the complete typed report."""
    args = _parse_args()
    root = args.repository_root.resolve()
    manifest = load_reference_product_manifest(args.manifest)
    validate_reference_product_files(root, manifest)
    candidate = product_set_by_reference(manifest, "master")
    reference = product_set_by_reference(manifest, "release")
    if candidate.configuration_sha256 != reference.configuration_sha256:
        raise ValueError("reference configurations differ")
    catalogue = compare_catalogues(
        load_pybdsf_catalogue(_path(root, reference, "source_catalog.fits")),
        load_pybdsf_catalogue(_path(root, candidate, "source_catalog.fits")),
        beam_fwhm_degrees=_BEAM_FWHM_DEGREES,
        maximum_separation_beams=_MAXIMUM_SEPARATION_BEAMS,
    )
    true_sky_rms = compare_rms_maps(
        load_fits_plane(_path(root, reference, "true_sky_rms.fits")),
        load_fits_plane(_path(root, candidate, "true_sky_rms.fits")),
    )
    flat_noise_rms = compare_rms_maps(
        load_fits_plane(_path(root, reference, "flat_noise_rms.fits")),
        load_fits_plane(_path(root, candidate, "flat_noise_rms.fits")),
    )
    mask = compare_masks(
        load_mask_plane(_path(root, reference, "source_filter_mask.fits")),
        load_mask_plane(_path(root, candidate, "source_filter_mask.fits")),
    )
    evidence = ScientificComparisonEvidence(
        schema_version=1,
        evidence_type="scientific-comparison",
        run_id="phase-0-pybdsf-master-vs-release-compact",
        captured_at=candidate.captured_at,
        status=EvidenceStatus.EXPLORATORY,
        dataset=manifest.dataset,
        candidate=candidate.subject,
        reference=reference.subject,
        candidate_product_manifest_sha256=canonical_product_set_sha256(
            candidate
        ),
        reference_product_manifest_sha256=canonical_product_set_sha256(
            reference
        ),
        configuration_sha256=candidate.configuration_sha256,
        beam_fwhm_degrees=_BEAM_FWHM_DEGREES,
        maximum_separation_beams=_MAXIMUM_SEPARATION_BEAMS,
        catalogue=catalogue,
        true_sky_rms=true_sky_rms,
        flat_noise_rms=flat_noise_rms,
        mask=mask,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_evidence(args.output, evidence)


if __name__ == "__main__":
    main()
