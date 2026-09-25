"""Unit contracts for configurable public scientific composition."""

# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from astropy.io import fits

from hebog import public_science
from hebog.algorithms.multiscale import BeamShapePixels
from hebog.config import SourceFinderConfig
from hebog.public_science import (
    _aligned_mask,
    build_configured_continuum_products,
)
from hebog.science.profile import (
    ContinuumScienceProfile,
    configured_science_profile,
    load_continuum_science_profile,
)
from hebog.validation.tiled_detection import (
    PublishedContinuumInputs,
    publish_continuum_inputs,
)

_ROOT = Path(__file__).parents[2]


def _header(shape: tuple[int, int]) -> fits.Header:
    """Return one valid one-arcsecond celestial fixture header."""
    header = fits.Header()
    header["NAXIS"] = 2
    header["NAXIS1"] = shape[1]
    header["NAXIS2"] = shape[0]
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["CRPIX1"] = (shape[1] + 1) / 2
    header["CRPIX2"] = (shape[0] + 1) / 2
    header["CRVAL1"] = 10.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0
    header["BMAJ"] = 5.0 / 3600.0
    header["BMIN"] = 4.0 / 3600.0
    header["BPA"] = 0.0
    return header


def _config(
    *,
    minimum_island_pixels: int = 1,
    maximum_island_pixels: int | None = None,
) -> SourceFinderConfig:
    """Return one valid caller-owned configuration."""
    return SourceFinderConfig(
        detection_threshold_sigma=8.0,
        island_threshold_sigma=6.0,
        minimum_island_pixels=minimum_island_pixels,
        maximum_island_pixels=maximum_island_pixels,
    )


def _published(
    image: np.ndarray,
    config: SourceFinderConfig,
    beam: BeamShapePixels,
    work_directory: Path,
    rms: np.ndarray | None = None,
) -> PublishedContinuumInputs:
    """Publish the tiled passes over one zero-background plane."""
    return publish_continuum_inputs(
        np.asarray(image, dtype=np.float64),
        np.ones(image.shape, dtype=np.bool_),
        np.zeros(image.shape, dtype=np.float64),
        np.ones(image.shape, dtype=np.float64)
        if rms is None
        else np.asarray(rms, dtype=np.float64),
        beam=beam,
        review=configured_science_profile(_review(), config),
        work_directory=work_directory,
        header=_header(image.shape),
        config=config,
    )


def _review() -> ContinuumScienceProfile:
    """Load the installed phase-neutral science profile fixture."""
    return load_continuum_science_profile(
        (
            _ROOT / "src/hebog/resources/reviewed_continuum_profile.json"
        ).read_bytes()
    )


@pytest.mark.parametrize(
    ("matrix", "corrections", "message"),
    (
        (None, {}, "matrix must be an object"),
        ({}, None, "corrections must be an object"),
        (
            {
                "scale_orders": [1, 2, 4],
                "support_fraction_bounds": [0.5, 1.0],
                "detection_sigma": 5.0,
                "island_sigma": 3.0,
            },
            {"minimum_island_area_beams": 1.0},
            "scales must be 1, 2, and 3",
        ),
        (
            {
                "scale_orders": [1, 2, 3],
                "support_fraction_bounds": [0.25, 1.0],
                "detection_sigma": 5.0,
                "island_sigma": 3.0,
            },
            {"minimum_island_area_beams": 1.0},
            "support fraction must span 0.5--1",
        ),
        (
            {
                "scale_orders": [1, 2, 3],
                "support_fraction_bounds": [0.5, 1.0],
                "detection_sigma": 3.0,
                "island_sigma": 3.0,
            },
            {"minimum_island_area_beams": 1.0},
            "thresholds must be positive and ordered",
        ),
        (
            {
                "scale_orders": [1, 2, 3],
                "support_fraction_bounds": [0.5, 1.0],
                "detection_sigma": 5.0,
                "island_sigma": 3.0,
            },
            {"minimum_island_area_beams": 0.0},
            "minimum island area must be positive",
        ),
    ),
)
def test_science_profile_rejects_malformed_runtime_fields(
    matrix: object,
    corrections: object,
    message: str,
) -> None:
    """Runtime loading fails clearly when a required science field drifts."""
    payload = json.dumps(
        {"matrix": matrix, "corrections": corrections}
    ).encode()

    with pytest.raises(ValueError, match=message):
        load_continuum_science_profile(payload)


@pytest.mark.parametrize(
    "values, shape",
    [
        (np.ones((2, 2), dtype=np.float64), None),
        (np.ones((2, 2), dtype=np.bool_), (3, 2)),
        (np.ones((2, 2, 2), dtype=np.bool_), None),
    ],
)
def test_aligned_mask_rejects_invalid_public_science_inputs(
    values: np.ndarray,
    shape: tuple[int, int] | None,
) -> None:
    """The adapter fails closed on non-boolean or misaligned masks."""
    with pytest.raises(ValueError, match="aligned boolean two-dimensional"):
        _aligned_mask(values, name="test", shape=shape)


def test_configured_builder_rejects_usable_noise_outside_the_valid_domain(
    tmp_path: Path,
) -> None:
    """A usable local noise cannot exist where the estimate does not."""
    valid = np.ones((2, 2), dtype=np.bool_)
    valid[0, 0] = False

    published = _published(
        np.ones((2, 2), dtype=np.float64),
        _config(),
        BeamShapePixels(4.0, 3.0, 0.0),
        tmp_path,
    )

    with pytest.raises(ValueError, match="positive RMS must be"):
        build_configured_continuum_products(
            valid,
            np.ones((2, 2), dtype=np.bool_),
            fits.Header(),
            multiscale=published.multiscale,
            labels=published.labels,
            topology=published.topology,
            measurements=published.measurements,
            association=published.association,
            hierarchy=published.hierarchy,
            source_labels=published.source_labels,
            source_measurement_labels=(published.source_measurement_labels),
            component_rows=published.component_rows,
            source_rows=published.source_rows,
            source_positions=published.source_positions,
            component_local_rms=published.component_local_rms,
            source_local_rms=published.source_local_rms,
        )


def test_configured_builder_measures_the_published_component_topology(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The composition measures deblended components, never their parents."""
    normalized = np.zeros((11, 12), dtype=np.float64)
    normalized[2:9, 2:10] = np.array([6.0, 5.0, 4.0, 3.0, 3.0, 4.0, 5.0, 9.0])
    published = _published(
        normalized,
        SourceFinderConfig(5.0, 3.0, 7),
        BeamShapePixels(5.0, 4.0, 0.0),
        tmp_path,
    )
    captured: dict[str, np.ndarray] = {}

    def capture_catalogues(
        valid: np.ndarray,
        measurement_labels: np.ndarray,
        direct_labels: np.ndarray,
        *args: object,
        **kwargs: object,
    ) -> SimpleNamespace:
        """Record the ownership planes the catalogue builder received."""
        del valid, args, kwargs
        captured["measurement"] = measurement_labels
        captured["direct"] = direct_labels
        return SimpleNamespace(
            source_catalogue=(),
            component_catalogue=(),
            association=object(),
            measurement_dispositions=(),
        )

    monkeypatch.setattr(
        public_science,
        "build_hebog_reconstructed_source_catalogues",
        capture_catalogues,
    )

    result = build_configured_continuum_products(
        np.ones(normalized.shape, dtype=np.bool_),
        np.ones(normalized.shape, dtype=np.bool_),
        _header(normalized.shape),
        multiscale=published.multiscale,
        labels=published.labels,
        topology=published.topology,
        measurements=published.measurements,
        association=published.association,
        hierarchy=published.hierarchy,
        source_labels=published.source_labels,
        source_measurement_labels=(published.source_measurement_labels),
        component_rows=published.component_rows,
        source_rows=published.source_rows,
        source_positions=published.source_positions,
        component_local_rms=published.component_local_rms,
        source_local_rms=published.source_local_rms,
    )

    assert result is not None
    np.testing.assert_array_equal(
        captured["direct"],
        published.topology.direct_component_labels,
    )
    np.testing.assert_array_equal(
        captured["measurement"],
        published.topology.measurement_component_labels,
    )
    # Deblending changes component identity, never the support it covers.
    np.testing.assert_array_equal(
        captured["direct"] > 0,
        published.labels.component_labels > 0,
    )


def test_configured_builder_publishes_independent_connected_sources(
    tmp_path: Path,
) -> None:
    """Independent Gaussian models remain two sources in one island."""
    yy, xx = np.mgrid[:65, :65]
    normalized = 10.0 * np.exp(
        -((yy - 32) ** 2 + (xx - 29) ** 2) / 8.0
    ) + 9.5 * np.exp(-((yy - 32) ** 2 + (xx - 36) ** 2) / 8.0)

    published = _published(
        normalized,
        SourceFinderConfig(5.0, 3.0, 7),
        BeamShapePixels(5.0, 4.0, 0.0),
        tmp_path,
    )

    result = build_configured_continuum_products(
        np.ones(normalized.shape, dtype=np.bool_),
        np.ones(normalized.shape, dtype=np.bool_),
        _header(normalized.shape),
        multiscale=published.multiscale,
        labels=published.labels,
        topology=published.topology,
        measurements=published.measurements,
        association=published.association,
        hierarchy=published.hierarchy,
        source_labels=published.source_labels,
        source_measurement_labels=(published.source_measurement_labels),
        component_rows=published.component_rows,
        source_rows=published.source_rows,
        source_positions=published.source_positions,
        component_local_rms=published.component_local_rms,
        source_local_rms=published.source_local_rms,
    )

    assert result is not None
    assert result.detection.component_count == 1
    assert len(result.component_catalogue) == 2
    assert len(result.catalogue) == 2
    assert all(row.component_count == 1 for row in result.catalogue)
    assert result.deblended_parent_count == 1
    assert result.deferred_deblend_parent_count == 0
    assert tuple(
        len(membership.component_ids)
        for membership in result.source_association.memberships
    ) == (1, 1)


def test_configured_builder_retains_three_components_in_one_parent(
    tmp_path: Path,
) -> None:
    """Multi-peak topology is not limited to a pairwise special case."""
    yy, xx = np.mgrid[:65, :65]
    normalized = np.zeros(yy.shape, dtype=np.float64)
    for amplitude, x_center in ((10.0, 25), (9.5, 32), (9.0, 39)):
        normalized += amplitude * np.exp(
            -((yy - 32) ** 2 + (xx - x_center) ** 2) / 8.0
        )

    published = _published(
        normalized,
        SourceFinderConfig(5.0, 3.0, 7),
        BeamShapePixels(5.0, 4.0, 0.0),
        tmp_path,
    )

    result = build_configured_continuum_products(
        np.ones(normalized.shape, dtype=np.bool_),
        np.ones(normalized.shape, dtype=np.bool_),
        _header(normalized.shape),
        multiscale=published.multiscale,
        labels=published.labels,
        topology=published.topology,
        measurements=published.measurements,
        association=published.association,
        hierarchy=published.hierarchy,
        source_labels=published.source_labels,
        source_measurement_labels=(published.source_measurement_labels),
        component_rows=published.component_rows,
        source_rows=published.source_rows,
        source_positions=published.source_positions,
        component_local_rms=published.component_local_rms,
        source_local_rms=published.source_local_rms,
    )

    assert result is not None
    assert result.detection.component_count == 1
    assert len(result.component_catalogue) == 3
    assert len(result.catalogue) == 3
    assert all(row.component_count == 1 for row in result.catalogue)
    assert result.deblended_parent_count == 1
    assert result.deferred_deblend_parent_count == 0
    assert tuple(
        len(membership.component_ids)
        for membership in result.source_association.memberships
    ) == (1, 1, 1)


def _owner_local_rms(
    rms: np.ndarray,
    labels: np.ndarray,
) -> dict[int, float]:
    """Return each label's median local noise over its own exact support."""
    usable = np.isfinite(rms) & (rms > 0.0)
    return {
        int(label_value): float(
            np.median(rms[(labels == label_value) & usable])
        )
        for label_value in sorted(
            int(value) for value in np.unique(labels) if value > 0
        )
        if np.any((labels == label_value) & usable)
    }


def test_published_local_noise_belongs_to_each_owner_support(
    tmp_path: Path,
) -> None:
    """Every owner's noise is the median over the pixels it owns itself.

    A component owns its measurement support and a source owns the union of
    its components', which is exactly what the published source-label plane
    carries, so both are checked against the planes rather than the rounds
    that measured them.
    """
    yy, xx = np.mgrid[:65, :80]
    normalized = np.zeros(yy.shape, dtype=np.float64)
    for amplitude, centre_y, centre_x in (
        (12.0, 32, 20),
        (11.0, 32, 27),
        (10.0, 16, 60),
    ):
        normalized += amplitude * np.exp(
            -((yy - centre_y) ** 2 + (xx - centre_x) ** 2) / 8.0
        )
    rms = 1.0 + 0.01 * np.asarray(xx, dtype=np.float64)
    rms[:, 20] = np.nan

    published = _published(
        normalized,
        SourceFinderConfig(5.0, 3.0, 7),
        BeamShapePixels(5.0, 4.0, 0.0),
        tmp_path,
        rms=rms,
    )

    components = _owner_local_rms(
        rms, published.topology.measurement_component_labels
    )
    sources = _owner_local_rms(rms, published.source_labels)
    assert len(components) > 1, "the fixture must measure several components"
    assert len({*components.values()}) == len(components)
    assert dict(published.component_local_rms) == components
    assert dict(published.source_local_rms) == sources


def test_the_composition_names_each_owner_noise_by_its_identity(
    tmp_path: Path,
) -> None:
    """Rows are published by identity, so the noise they quote must be too."""
    yy, xx = np.mgrid[:65, :65]
    normalized = 10.0 * np.exp(
        -((yy - 32) ** 2 + (xx - 29) ** 2) / 8.0
    ) + 9.5 * np.exp(-((yy - 32) ** 2 + (xx - 36) ** 2) / 8.0)
    rms = 1.0 + 0.01 * np.asarray(xx, dtype=np.float64)

    published = _published(
        normalized,
        SourceFinderConfig(5.0, 3.0, 7),
        BeamShapePixels(5.0, 4.0, 0.0),
        tmp_path,
        rms=rms,
    )
    result = build_configured_continuum_products(
        np.ones(normalized.shape, dtype=np.bool_),
        np.ones(normalized.shape, dtype=np.bool_),
        _header(normalized.shape),
        multiscale=published.multiscale,
        labels=published.labels,
        topology=published.topology,
        measurements=published.measurements,
        association=published.association,
        hierarchy=published.hierarchy,
        source_labels=published.source_labels,
        source_measurement_labels=(published.source_measurement_labels),
        component_rows=published.component_rows,
        source_rows=published.source_rows,
        source_positions=published.source_positions,
        component_local_rms=published.component_local_rms,
        source_local_rms=published.source_local_rms,
    )

    assert result is not None
    association = published.association
    assert len(association.components) > 1
    assert result.local_rms_by_object_id == {
        **{
            record.component_id: published.component_local_rms[
                record.label_value
            ]
            for record in association.components
        },
        **{
            membership.source_id: published.source_local_rms[source_label]
            for source_label, membership in enumerate(
                association.memberships, start=1
            )
        },
    }
