# pyright: reportMissingTypeStubs=false
"""Tests for the prospective external-comparison compiler kernel."""

from __future__ import annotations

import runpy
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from hebog.validation.comparison import CatalogueSource
from hebog.validation.external_successor_compiler import (
    ContinuumCatalogueObject,
    ContinuumTruthObject,
    continuum_catalogue_objects,
    measure_continuum_image,
    native_support_objects,
)
from hebog.validation.observable_truth import (
    observable_truth_integrated_flux_jy,
)

_ROOT = Path(__file__).parents[3]
_TERMINAL_COMPILER = (
    _ROOT / "scripts/validation/compile_phase5_external_campaign.py"
)


def _truth(
    identifier: str,
    label: int,
    centre_xy: tuple[float, float],
    flux: float,
) -> ContinuumTruthObject:
    return ContinuumTruthObject(
        identifier=identifier,
        support_label=label,
        centre_xy=centre_xy,
        integrated_flux_jy=flux,
        catalogue_role="astronomical-source",
        strata=("morphology-diffuse",),
    )


def _candidate(
    identifier: str,
    label: int,
    centre_xy: tuple[float, float],
    flux: float,
) -> ContinuumCatalogueObject:
    return ContinuumCatalogueObject(
        identifier=identifier,
        support_label=label,
        centre_xy=centre_xy,
        integrated_flux_jy=flux,
    )


def _header() -> fits.Header:
    header = fits.Header()
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["CRPIX1"] = 1.0
    header["CRPIX2"] = 1.0
    header["CRVAL1"] = 10.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0
    return header


def _source(identifier: str, island_identifier: str) -> CatalogueSource:
    return CatalogueSource(
        identifier=identifier,
        right_ascension_degrees=10.0,
        declination_degrees=-30.0,
        peak_flux_jy_per_beam=1.0,
        integrated_flux_jy=2.0,
        association_integrated_flux_jy=3.0,
        island_identifier=island_identifier,
    )


def test_observable_truth_flux_excludes_masked_and_off_image_signal() -> None:
    """Edge truth is normalized to the valid pixels a finder can observe."""
    signal = np.asarray(
        (
            (1.0, 2.0, 3.0),
            (4.0, 5.0, 6.0),
        ),
        dtype=np.float64,
    )
    valid = np.asarray(
        (
            (False, True, True),
            (False, True, False),
        ),
        dtype=np.bool_,
    )

    actual = observable_truth_integrated_flux_jy(
        signal,
        valid,
        beam_major_fwhm_pixels=2.0,
        beam_minor_fwhm_pixels=1.0,
    )

    beam_area_pixels = 2.0 * np.pi / (8.0 * np.log(2.0)) * 2.0
    assert actual == pytest.approx((2.0 + 3.0 + 5.0) / beam_area_pixels)


def test_observable_truth_flux_rejects_unmeasurable_domains() -> None:
    """Prospective truth cannot silently publish a zero or invalid flux."""
    with pytest.raises(ValueError, match="aligned two-dimensional"):
        observable_truth_integrated_flux_jy(
            np.ones((2, 2), dtype=np.float64),
            np.ones((2, 1), dtype=np.bool_),
            beam_major_fwhm_pixels=2.0,
            beam_minor_fwhm_pixels=1.0,
        )
    with pytest.raises(ValueError, match="positive observable"):
        observable_truth_integrated_flux_jy(
            -np.ones((2, 2), dtype=np.float64),
            np.ones((2, 2), dtype=np.bool_),
            beam_major_fwhm_pixels=2.0,
            beam_minor_fwhm_pixels=1.0,
        )
    with pytest.raises(ValueError, match="beam axes"):
        observable_truth_integrated_flux_jy(
            np.ones((2, 2), dtype=np.float64),
            np.ones((2, 2), dtype=np.bool_),
            beam_major_fwhm_pixels=float("nan"),
            beam_minor_fwhm_pixels=1.0,
        )


def test_native_support_objects_include_fitless_labels() -> None:
    """Every positive native label receives one topology-only object."""
    labels = np.asarray(
        (
            (0, 4, 4, 0, 0),
            (0, 4, 4, 9, 9),
            (0, 0, 0, 9, 9),
        ),
        dtype=np.int32,
    )

    supports = native_support_objects(labels)

    assert tuple(item.identifier for item in supports) == (
        "support-4",
        "support-9",
    )
    assert tuple(item.support_label for item in supports) == (4, 9)
    assert supports[0].centre_xy == pytest.approx((1.5, 0.5))
    assert supports[1].centre_xy == pytest.approx((3.5, 1.5))


@pytest.mark.parametrize(
    ("finder_id", "island_identifier", "expected_label"),
    (
        ("hebog", "hebog-segment-4", 4),
        ("released-pybdsf", "3", 4),
        ("pinned-pybdsf-master", "3", 4),
    ),
)
def test_catalogue_translation_allows_mask_only_native_labels(
    finder_id: str,
    island_identifier: str,
    expected_label: int,
) -> None:
    """Measurable rows may be a strict subset of positive native labels."""
    labels = np.asarray(((4, 4, 9), (4, 4, 9)), dtype=np.int32)

    candidates = continuum_catalogue_objects(
        (_source("source-1", island_identifier),),
        labels,
        finder_id=finder_id,  # type: ignore[arg-type]
        header=_header(),
    )

    assert len(candidates) == 1
    assert candidates[0].support_label == expected_label
    assert candidates[0].centre_xy == pytest.approx((0.0, 0.0))
    assert candidates[0].integrated_flux_jy == 3.0


def test_catalogue_translation_rejects_absent_and_malformed_labels() -> None:
    """Subset semantics cannot conceal broken catalogue identities."""
    labels = np.asarray(((1, 1), (0, 0)), dtype=np.int32)

    with pytest.raises(ValueError, match="support label is absent"):
        continuum_catalogue_objects(
            (_source("source-1", "3"),),
            labels,
            finder_id="released-pybdsf",
            header=_header(),
        )
    with pytest.raises(
        ValueError,
        match="PyBDSF island identity is malformed",
    ):
        continuum_catalogue_objects(
            (_source("source-1", "3.0"),),
            labels,
            finder_id="released-pybdsf",
            header=_header(),
        )
    with pytest.raises(ValueError, match="Hebog segment island identity"):
        continuum_catalogue_objects(
            (_source("source-1", "segment-1"),),
            labels,
            finder_id="hebog",
            header=_header(),
        )
    with pytest.raises(ValueError, match="Hebog segment island identity"):
        continuum_catalogue_objects(
            (_source("source-1", "hebog-segment-x"),),
            labels,
            finder_id="hebog",
            header=_header(),
        )
    with pytest.raises(
        ValueError, match="PyBDSF island identity is malformed"
    ):
        continuum_catalogue_objects(
            (_source("source-1", "-1"),),
            labels,
            finder_id="released-pybdsf",
            header=_header(),
        )
    with pytest.raises(ValueError, match="lacks an island identity"):
        continuum_catalogue_objects(
            (
                CatalogueSource(
                    identifier="source-1",
                    right_ascension_degrees=10.0,
                    declination_degrees=-30.0,
                    peak_flux_jy_per_beam=1.0,
                    integrated_flux_jy=2.0,
                ),
            ),
            labels,
            finder_id="released-pybdsf",
            header=_header(),
        )
    with pytest.raises(ValueError, match="finder identity is unsupported"):
        continuum_catalogue_objects(
            (_source("source-1", "0"),),
            labels,
            finder_id="aegean",  # type: ignore[arg-type]
            header=_header(),
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        ({"identifier": ""}, "identifier"),
        ({"support_label": 0}, "support label"),
        ({"centre_xy": (np.nan, 0.0)}, "centre"),
        ({"integrated_flux_jy": 0.0}, "flux"),
    ),
)
def test_catalogue_objects_reject_nonphysical_fields(
    changes: dict[str, object],
    message: str,
) -> None:
    """Successor records cannot encode an invented measurement."""
    values: dict[str, object] = {
        "identifier": "source-1",
        "support_label": 1,
        "centre_xy": (1.0, 1.0),
        "integrated_flux_jy": 1.0,
    }
    values.update(changes)

    with pytest.raises(ValueError, match=message):
        ContinuumCatalogueObject(**values)  # type: ignore[arg-type]


def test_truth_strata_must_be_canonical() -> None:
    """Duplicate or unsorted stratum identities cannot change endpoints."""
    with pytest.raises(ValueError, match="strata must be canonical"):
        ContinuumTruthObject(
            identifier="truth-1",
            support_label=1,
            centre_xy=(1.0, 1.0),
            integrated_flux_jy=1.0,
            catalogue_role="astronomical-source",
            strata=("z", "a", "z"),
        )


def test_truth_role_must_be_supported() -> None:
    """A runtime-invalid role cannot silently change endpoint membership."""
    with pytest.raises(ValueError, match="catalogue role is unsupported"):
        ContinuumTruthObject(
            identifier="truth-1",
            support_label=1,
            centre_xy=(1.0, 1.0),
            integrated_flux_jy=1.0,
            catalogue_role="unknown",  # type: ignore[arg-type]
            strata=("morphology-diffuse",),
        )


@pytest.mark.parametrize(
    "labels",
    (
        np.asarray((0, 1), dtype=np.int32),
        np.asarray(((0.0, 1.0),), dtype=np.float64),
        np.asarray(((0, -1),), dtype=np.int32),
    ),
)
def test_native_supports_reject_invalid_label_planes(
    labels: np.ndarray,
) -> None:
    """Topology objects require exact non-negative integer planes."""
    with pytest.raises(ValueError, match="candidate label plane"):
        native_support_objects(labels)


def test_mask_only_support_participates_in_split_topology() -> None:
    """A fitless half of one detection split remains in the denominator."""
    truth_labels = np.zeros((5, 7), dtype=np.int32)
    truth_labels[1:3, 1:5] = 1
    candidate_labels = np.zeros_like(truth_labels)
    candidate_labels[1:3, 1:3] = 1
    candidate_labels[1:3, 3:5] = 2
    truth = (_truth("truth-1", 1, (2.5, 1.5), 2.0),)
    catalogue = (_candidate("source-1", 1, (1.5, 1.5), 2.0),)

    metrics = measure_continuum_image(
        truth,
        catalogue,
        truth_label_plane=truth_labels,
        candidate_label_plane=candidate_labels,
        beam_fwhm_pixels=2.0,
    )

    assert metrics["completeness"]["overall"] == 1.0
    assert metrics["reliability"]["overall"] == 1.0
    assert metrics["mask-recall"]["overall"] == 1.0
    assert metrics["split-fraction"]["overall"] == 1.0


def test_mask_only_support_does_not_invent_catalogue_measurements() -> None:
    """Label-only recovery stays absent from catalogue and flux metrics."""
    truth_labels = np.zeros((6, 8), dtype=np.int32)
    truth_labels[1:3, 1:3] = 1
    truth_labels[3:5, 5:7] = 2
    candidate_labels = truth_labels.copy()
    truth = (
        _truth("truth-1", 1, (1.5, 1.5), 2.0),
        _truth("truth-2", 2, (5.5, 3.5), 3.0),
    )
    catalogue = (_candidate("source-1", 1, (1.5, 1.5), 2.0),)

    metrics = measure_continuum_image(
        truth,
        catalogue,
        truth_label_plane=truth_labels,
        candidate_label_plane=candidate_labels,
        beam_fwhm_pixels=2.0,
    )

    assert metrics["completeness"]["overall"] == 0.5
    assert metrics["reliability"]["overall"] == 1.0
    assert metrics["integrated-flux-median"]["overall"] == (0.0,)
    assert metrics["mask-recall"]["overall"] == 1.0


def test_mask_only_detection_without_any_row_stays_explicit() -> None:
    """A label-only detection has mask recovery but unavailable measurement."""
    labels = np.zeros((4, 4), dtype=np.int32)
    labels[1:3, 1:3] = 1
    truth = (_truth("truth-1", 1, (1.5, 1.5), 2.0),)

    metrics = measure_continuum_image(
        truth,
        (),
        truth_label_plane=labels,
        candidate_label_plane=labels,
        beam_fwhm_pixels=2.0,
    )

    assert metrics["completeness"]["overall"] == 0.0
    assert metrics["reliability"]["overall"] == 0.0
    assert metrics["integrated-flux-median"]["overall"] == ()
    assert metrics["mask-recall"]["overall"] == 1.0


def test_artifact_match_is_excluded_from_conditional_measurements() -> None:
    """Artifact topology cannot create an astronomical flux observation."""
    labels = np.zeros((4, 4), dtype=np.int32)
    labels[1:3, 1:3] = 1
    truth = (
        ContinuumTruthObject(
            identifier="artifact-1",
            support_label=1,
            centre_xy=(1.5, 1.5),
            integrated_flux_jy=2.0,
            catalogue_role="artifact",
            strata=("morphology-artifact",),
        ),
    )

    metrics = measure_continuum_image(
        truth,
        (_candidate("candidate-1", 1, (1.5, 1.5), 2.0),),
        truth_label_plane=labels,
        candidate_label_plane=labels,
        beam_fwhm_pixels=2.0,
    )

    assert metrics["completeness"]["overall"] == 1.0
    assert metrics["integrated-flux-median"]["overall"] == ()


def test_measurement_rejects_incomplete_or_misaligned_inputs() -> None:
    """The successor rejects missing truth and broken plane identity."""
    labels = np.asarray(((1, 1), (0, 0)), dtype=np.int32)
    truth = (_truth("truth-1", 1, (0.5, 0.0), 1.0),)

    with pytest.raises(ValueError, match="truth must not be empty"):
        measure_continuum_image(
            (),
            (),
            truth_label_plane=labels,
            candidate_label_plane=labels,
            beam_fwhm_pixels=2.0,
        )
    with pytest.raises(ValueError, match="must share shape"):
        measure_continuum_image(
            truth,
            (),
            truth_label_plane=labels,
            candidate_label_plane=np.zeros((3, 3), dtype=np.int32),
            beam_fwhm_pixels=2.0,
        )
    with pytest.raises(ValueError, match="absent from native labels"):
        measure_continuum_image(
            truth,
            (_candidate("source-2", 2, (0.5, 0.0), 1.0),),
            truth_label_plane=labels,
            candidate_label_plane=labels,
            beam_fwhm_pixels=2.0,
        )


def test_catalogued_supports_preserve_terminal_metric_values() -> None:
    """The successor changes no metric when every label has a row."""
    truth_labels = np.zeros((6, 8), dtype=np.int32)
    truth_labels[1:3, 1:3] = 1
    truth_labels[3:5, 5:7] = 2
    candidate_labels = truth_labels.copy()
    truth = (
        _truth("truth-1", 1, (1.5, 1.5), 2.0),
        _truth("truth-2", 2, (5.5, 3.5), 3.0),
    )
    catalogue = (
        _candidate("source-1", 1, (1.5, 1.5), 2.2),
        _candidate("source-2", 2, (5.5, 3.5), 2.7),
    )
    actual = measure_continuum_image(
        truth,
        catalogue,
        truth_label_plane=truth_labels,
        candidate_label_plane=candidate_labels,
        beam_fwhm_pixels=2.0,
    )
    terminal = runpy.run_path(str(_TERMINAL_COMPILER))
    terminal_truth_type = terminal["ContinuumTruthObject"]
    terminal_candidate_type = terminal["ContinuumCandidateObject"]
    expected = terminal["measure_continuum_image"](
        tuple(
            terminal_truth_type(
                identifier=item.identifier,
                support_label=item.support_label,
                centre_xy=item.centre_xy,
                integrated_flux_jy=item.integrated_flux_jy,
                catalogue_role=item.catalogue_role,
                strata=item.strata,
            )
            for item in truth
        ),
        tuple(
            terminal_candidate_type(
                identifier=item.identifier,
                support_label=item.support_label,
                centre_xy=item.centre_xy,
                integrated_flux_jy=item.integrated_flux_jy,
            )
            for item in catalogue
        ),
        truth_label_plane=truth_labels,
        candidate_label_plane=candidate_labels,
        beam_fwhm_pixels=2.0,
    )

    assert actual == expected


def test_catalogued_support_centres_preserve_terminal_topology() -> None:
    """Native label completion cannot move existing support descriptors."""
    truth_labels = np.zeros((12, 12), dtype=np.int32)
    truth_labels[1:3, 1:3] = 1
    candidate_labels = np.zeros_like(truth_labels)
    candidate_labels[8:10, 7:9] = 1
    candidate_labels[8:10, 9:11] = 2
    truth = (_truth("truth-1", 1, (1.5, 1.5), 2.0),)
    catalogue = (
        _candidate("source-1", 1, (1.5, 1.5), 1.0),
        _candidate("source-2", 2, (1.8, 1.5), 1.0),
    )

    actual = measure_continuum_image(
        truth,
        catalogue,
        truth_label_plane=truth_labels,
        candidate_label_plane=candidate_labels,
        beam_fwhm_pixels=2.0,
    )
    terminal = runpy.run_path(str(_TERMINAL_COMPILER))
    expected = terminal["measure_continuum_image"](
        (
            terminal["ContinuumTruthObject"](
                identifier="truth-1",
                support_label=1,
                centre_xy=(1.5, 1.5),
                integrated_flux_jy=2.0,
                catalogue_role="astronomical-source",
                strata=("morphology-diffuse",),
            ),
        ),
        tuple(
            terminal["ContinuumCandidateObject"](
                identifier=item.identifier,
                support_label=item.support_label,
                centre_xy=item.centre_xy,
                integrated_flux_jy=item.integrated_flux_jy,
            )
            for item in catalogue
        ),
        truth_label_plane=truth_labels,
        candidate_label_plane=candidate_labels,
        beam_fwhm_pixels=2.0,
    )

    assert actual == expected
    assert actual["split-fraction"]["overall"] == 1.0
