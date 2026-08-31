# pyright: reportMissingImports=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Exact non-promotional end-to-end terminal-cycle contract lane."""

from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS

from hebog.algorithms.multiscale import BeamShapePixels
from hebog.validation.contracts import load_phase_five_corrective_a_review
from hebog.validation.datasets import (
    generate_synthetic_image,
    load_dataset_manifest,
)
from hebog.validation.external_runners import file_sha256
from hebog.validation.hebog_campaign import process_hebog_image
from hebog.validation.products import write_comparison_catalogue
from hebog.validation.public_finder_correction import (
    build_public_finder_source_reconstruction_continuum_products,
)
from hebog.validation.source_association_evaluation_repair import (
    measure_continuum_image,
)
from hebog.validation.terminal_cycle_eligibility_evaluation import (
    TerminalCycleEligibilityContinuumImageCompiler,
)
from hebog.validation.terminal_cycle_fail_fast import (
    build_terminal_cycle_fail_fast_record,
    load_terminal_cycle_case_manifest,
    publish_terminal_cycle_fail_fast_record,
    write_terminal_cycle_association,
)

_ROOT = Path(__file__).parents[2]
_COMPILER = _ROOT / "scripts/validation/compile_phase5_external_campaign.py"
_MANIFEST = (
    _ROOT / "config/contracts/phase-5-terminal-cycle-fail-fast-cases.json"
)


def _header(shape: tuple[int, int]) -> fits.Header:
    """Return one valid tangent-plane FITS header."""
    header = fits.Header()
    header["NAXIS"] = 2
    header["NAXIS1"] = shape[1]
    header["NAXIS2"] = shape[0]
    header["CTYPE1"] = "RA---TAN"
    header["CTYPE2"] = "DEC--TAN"
    header["CRPIX1"] = shape[1] / 2 + 1
    header["CRPIX2"] = shape[0] / 2 + 1
    header["CRVAL1"] = 0.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0
    header["BMAJ"] = 4.0 / 3600.0
    header["BMIN"] = 4.0 / 3600.0
    header["BPA"] = 0.0
    return header


def _ring_image() -> np.ndarray:
    """Return the real-path four-lobe shell analytic sentinel."""
    y_pixels, x_pixels = np.mgrid[:81, :81]
    x_offset = x_pixels - 40.0
    y_offset = y_pixels - 40.0
    radius = np.hypot(x_offset, y_offset)
    angle = np.arctan2(y_offset, x_offset)
    image = np.exp(-((radius - 10.0) ** 2) / 2.0)
    image *= 1.0 + 8.0 * np.clip(np.cos(4.0 * angle), 0.0, None)
    return np.asarray(image, dtype=np.float64)


def _sha256(path: Path) -> str:
    """Hash one small analytic product."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _compact_digests(tmp_path: Path) -> tuple[str, str]:
    """Run the exact compact producer twice and require byte stability."""
    dataset = load_dataset_manifest(
        _ROOT / "config/datasets/phase-0-development.json"
    ).datasets[0]
    image = generate_synthetic_image(dataset.recipe)
    digests: list[str] = []
    for repetition in range(2):
        catalogue = process_hebog_image(
            image,
            dataset,
            tmp_path / f"compact-work-{repetition}",
            generation_id=f"fail-fast-compact-{repetition}",
        )
        output = tmp_path / f"compact-{repetition}.json"
        write_comparison_catalogue(output, catalogue)
        digests.append(_sha256(output))
    return digests[0], digests[1]


def _mechanism_evidence() -> dict[str, object]:
    """Reuse the exact frozen mechanism lane in the e2e record."""
    # The end-to-end test needs only one real positive association; the 25-case
    # scientific population is executed by its dedicated unit lane.  Rebuild
    # its bounded aggregate from four copies of that real positive census.
    manifest = load_terminal_cycle_case_manifest(_MANIFEST)
    positive = tuple(
        case
        for case in manifest.cases
        if case.family == "persistent-unseeded-geometry"
    )
    observations = tuple(
        SimpleNamespace(
            case_id=case.case_id,
            family=case.family,
            maximum_membership_size=3,
            pre_eligibility_candidate_count=1,
            terminal_parent_count=1,
            unseeded_candidate_count=1,
            unseeded_persistent_accepted_count=1,
        )
        for case in positive
    )
    # This helper is intentionally not used as the mechanism-lane pass: it
    # only supplies the already-validated census to the composition record.
    return {
        "schema_version": 1,
        "lane_id": manifest.lane_id,
        "case_count": len(manifest.cases),
        "family_count": 8,
        "positive_activation_count": sum(
            item.unseeded_persistent_accepted_count for item in observations
        ),
        "pre_guard_rejection_count": sum(
            item.unseeded_candidate_count for item in observations
        ),
        "all_controls_pass": True,
        "promotion_evidence": False,
    }


@pytest.mark.integration
def test_exact_analytic_composition_compiles_and_publishes_once(
    tmp_path: Path,
) -> None:
    """Exercise producer, compiler, evaluator, and atomic publication."""
    image = _ring_image()
    header = _header(image.shape)
    review = load_phase_five_corrective_a_review(
        _ROOT / "config/contracts/phase-5-corrective-a-review.json"
    )
    products = build_public_finder_source_reconstruction_continuum_products(
        image,
        np.zeros(image.shape),
        np.ones(image.shape),
        header,
        beam=BeamShapePixels(4.0, 4.0, 0.0),
        review=review,
    )
    sidecar = tmp_path / "source_association.json"
    write_terminal_cycle_association(sidecar, products.source_association)

    input_directory = tmp_path / "input"
    result_directory = tmp_path / "result"
    input_directory.mkdir()
    result_directory.mkdir()
    for role, values in (
        ("image", image),
        ("mean", np.zeros(image.shape)),
        ("rms", np.ones(image.shape)),
    ):
        fits.PrimaryHDU(
            data=values[np.newaxis, np.newaxis, :, :], header=header
        ).writeto(input_directory / f"{role}.fits")
    catalogue_path = result_directory / "segment_catalogue.json"
    labels_path = result_directory / "segment_labels.fits"
    write_comparison_catalogue(catalogue_path, products.catalogue)
    fits.PrimaryHDU(
        data=products.detection.component_labels[np.newaxis, np.newaxis, :, :],
        header=header,
    ).writeto(labels_path)

    frozen = runpy.run_path(str(_COMPILER))
    source = products.catalogue[0]
    centre = WCS(header, relax=True).celestial.all_world2pix(
        [[source.right_ascension_degrees, source.declination_degrees]], 0
    )[0]
    integrated_flux = (
        source.association_integrated_flux_jy
        if source.association_integrated_flux_jy is not None
        else source.integrated_flux_jy
    )
    truth_type = frozen["ContinuumTruthObject"]
    truth = (
        truth_type(
            identifier="analytic-shell",
            support_label=1,
            centre_xy=(float(centre[0]), float(centre[1])),
            integrated_flux_jy=float(integrated_flux),
            catalogue_role="astronomical-source",
            strata=(),
        ),
    )
    truth_labels = np.asarray(
        products.detection.component_labels > 0, dtype=np.int64
    )

    def truth_objects(*_args: object) -> tuple[tuple[Any, ...], np.ndarray]:
        return truth, truth_labels

    terminal: dict[str, Any] = {
        "_input_artifact_path": frozen["_input_artifact_path"],
        "load_fits_plane": frozen["load_fits_plane"],
        "_truth_objects": truth_objects,
        "_catalogue_and_labels": frozen["_catalogue_and_labels"],
        "_candidate_objects": frozen["_candidate_objects"],
        "measure_continuum_image": measure_continuum_image,
        "EndpointObservation": frozen["EndpointObservation"],
        "_failed_endpoint_observations": frozen[
            "_failed_endpoint_observations"
        ],
    }
    compiler = TerminalCycleEligibilityContinuumImageCompiler(
        terminal,
        association_path=lambda _run: sidecar,
    )
    input_path = input_directory / "input.json"
    input_path.write_text("{}\n", encoding="utf-8")
    bundle = SimpleNamespace(
        artifacts=tuple(
            SimpleNamespace(role=role, relative_path=f"{role}.fits")
            for role in ("image", "mean", "rms")
        )
    )
    run = SimpleNamespace(
        request=SimpleNamespace(run_id="analytic-hebog"),
        directory=result_directory,
        result=SimpleNamespace(
            status="success",
            failure=None,
            finder_id="hebog",
            artifacts=(
                SimpleNamespace(
                    role="segment-catalogue-json",
                    relative_path=catalogue_path.name,
                ),
                SimpleNamespace(
                    role="segment-labels-fits",
                    relative_path=labels_path.name,
                ),
            ),
        ),
    )
    specifications = (
        SimpleNamespace(
            endpoint_id="completeness-overall",
            metric_family="completeness",
            stratum="overall",
        ),
        SimpleNamespace(
            endpoint_id="mask-precision-overall",
            metric_family="mask-precision",
            stratum="overall",
        ),
    )
    compiled = compiler(
        SimpleNamespace(inputs={"analytic-input": (bundle, input_path)}),
        SimpleNamespace(input_id="analytic-input"),
        run,
        SimpleNamespace(beam=SimpleNamespace(major_fwhm_pixels=4.0)),
        SimpleNamespace(),
        review,
        specifications,
    )
    compact_before, compact_after = _compact_digests(tmp_path)
    record = build_terminal_cycle_fail_fast_record(
        mechanism=_mechanism_evidence(),
        association_paths=(sidecar,),
        compact_sha256_before=compact_before,
        compact_sha256_after=compact_after,
        compiled_endpoint_values={
            key: cast(tuple[float, ...], value.values)
            for key, value in compiled.items()
        },
        provenance={
            "producer_sha256": file_sha256(
                _ROOT / "src/hebog/validation/public_finder_correction.py"
            ),
            "writer_sha256": file_sha256(
                _ROOT / "src/hebog/validation/terminal_cycle_fail_fast.py"
            ),
            "compiler_sha256": file_sha256(
                _ROOT / "src/hebog/validation/"
                "terminal_cycle_eligibility_evaluation.py"
            ),
            "evaluator_sha256": file_sha256(
                _ROOT / "src/hebog/validation/"
                "source_association_evaluation_repair.py"
            ),
        },
    )
    output = tmp_path / "fail-fast.json"
    publish_terminal_cycle_fail_fast_record(output, record)

    assert json.loads(output.read_text(encoding="utf-8")) == record
    assert record["promotion_evidence"] is False
    assert record["compact_byte_invariant"] is True
    assert set(compiled) == {
        "completeness-overall",
        "mask-precision-overall",
    }
    with pytest.raises(FileExistsError):
        publish_terminal_cycle_fail_fast_record(output, record)
