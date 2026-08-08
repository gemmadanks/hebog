"""Freeze the Step 2C-A astrometry confirmation protocol."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import cast

from hebog.validation.contracts import PhaseFiveCorrectiveAReview


def _sha256(path: Path) -> str:
    """Return the exact identity of one frozen input."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _document(
    prior_protocol_path: Path,
    prior_decision_path: Path,
    confirmation_manifest_path: Path,
) -> dict[str, object]:
    """Derive and validate the protocol from the Step 2C-R contract."""
    document = cast(
        dict[str, object],
        json.loads(prior_protocol_path.read_text(encoding="utf-8")),
    )
    document["contract_id"] = "phase-5-corrective-a-review"
    document["status"] = "frozen-before-corrective-a-results"
    document["prior_decision_sha256"] = _sha256(prior_decision_path)
    document["supersedes_protocol_sha256"] = _sha256(prior_protocol_path)
    datasets = cast(list[dict[str, object]], document["dataset_manifests"])
    datasets[1] = {
        "image_count": 100,
        "manifest": "config/datasets/phase-5-corrective-a-confirmation.json",
        "manifest_sha256": _sha256(confirmation_manifest_path),
        "role": "regression",
    }
    document["astrometry_estimator"] = {
        "component_centre_bound_beams": 1.0,
        "fallback": "step-2c-r-robust-observable-moment",
        "family": (
            "local-rms-weighted-multigaussian-observable-centroid-shrinkage"
        ),
        "fit_margin_beams": 3.0,
        "loss": "soft-l1-local-rms-standardized",
        "maximum_components": 6,
        "maximum_iterations": 300,
        "maximum_model_moment_disagreement_beams": 1.0,
        "maximum_normalized_cost": 2.0,
        "maximum_sigma_major_beams": 3.0,
        "minimum_sigma_minor_fwhm_divisor": 2.355,
        "model_weight": 0.5,
        "peak_seed_sigma": 6.0,
        "peak_selection": "beam-separated-original-pixel-local-maxima",
        "peak_separation_beams": 2.0,
        "pixel_domain": "original-residual-pixels",
        "target": "observable-valid-domain-flux-centroid",
        "uncertainty": "correlated-noise-moment-propagation",
    }
    document["confirmation_reuse"] = "one-look-no-tuning-or-rescoring"
    validated = PhaseFiveCorrectiveAReview.model_validate(document)
    return cast(dict[str, object], validated.model_dump(mode="json"))


def _parse_args() -> argparse.Namespace:
    """Parse governed paths without making scientific values configurable."""
    root = Path(__file__).parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prior-protocol",
        type=Path,
        default=root / "config/contracts/phase-5-corrective-r-review.json",
    )
    parser.add_argument(
        "--prior-decision",
        type=Path,
        default=root / "config/contracts/phase-5-corrective-r-decision.json",
    )
    parser.add_argument(
        "--confirmation-manifest",
        type=Path,
        default=(
            root / "config/datasets/phase-5-corrective-a-confirmation.json"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "config/contracts/phase-5-corrective-a-review.json",
    )
    return parser.parse_args()


def main() -> None:
    """Write the canonical protocol once without replacing frozen input."""
    arguments = _parse_args()
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite frozen protocol: {arguments.output}"
        )
    document = _document(
        arguments.prior_protocol,
        arguments.prior_decision,
        arguments.confirmation_manifest,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(document, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
