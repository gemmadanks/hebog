"""Unit contracts for configurable public scientific composition."""

# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import numpy.typing as npt
import pytest
from astropy.io import fits

from hebog import public_science
from hebog.algorithms.multiscale import BeamShapePixels
from hebog.config import SourceFinderConfig
from hebog.public_api import (
    component_records_from_windows,
)
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
) -> PublishedContinuumInputs:
    """Publish the tiled passes over one zero-background plane."""
    return publish_continuum_inputs(
        np.asarray(image, dtype=np.float64),
        np.ones(image.shape, dtype=np.bool_),
        np.zeros(image.shape, dtype=np.float64),
        np.ones(image.shape, dtype=np.float64),
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


def test_component_records_do_not_depend_on_the_read_batch_size(
    tmp_path: Path,
) -> None:
    """One read per batch must describe what one read per component does.

    The residual is assembled from storage chunks far larger than a
    component, so neighbours share a read. How many share it is a memory
    and decode decision, and it may never reach the records.
    """
    yy, xx = np.mgrid[:96, :96]
    normalized: npt.NDArray[np.float64] = np.zeros((96, 96), dtype=np.float64)
    for centre_y, centre_x, peak in (
        (16, 16, 12.0),
        (16, 76, 9.0),
        (52, 44, 15.0),
        (80, 20, 10.5),
        (80, 78, 11.0),
    ):
        normalized += peak * np.exp(
            -((yy - centre_y) ** 2 + (xx - centre_x) ** 2) / 8.0
        )
    published = _published(
        normalized,
        SourceFinderConfig(5.0, 3.0, 7),
        BeamShapePixels(5.0, 4.0, 0.0),
        tmp_path,
    )
    labels = published.topology.direct_component_labels
    assert int(np.count_nonzero(np.unique(labels) > 0)) == 5
    valid_pixels: npt.NDArray[np.bool_] = np.ones((96, 96), dtype=np.bool_)

    batched, per_component = (
        component_records_from_windows(
            published.image_source,
            published.background_rms,
            direct_component_labels=labels,
            valid_pixels=valid_pixels,
            maximum_batch_read_pixels=budget,
        )
        for budget in (normalized.size, 1)
    )

    assert batched == per_component
    assert len(batched) == 5


def test_component_records_describe_nothing_without_a_component(
    tmp_path: Path,
) -> None:
    """Labels that admit no component ask the store for no residual."""
    normalized: npt.NDArray[np.float64] = np.zeros((48, 48), dtype=np.float64)
    normalized[24, 24] = 40.0
    published = _published(
        normalized,
        SourceFinderConfig(5.0, 3.0, 7),
        BeamShapePixels(5.0, 4.0, 0.0),
        tmp_path,
    )

    records = component_records_from_windows(
        published.image_source,
        published.background_rms,
        direct_component_labels=np.zeros((48, 48), dtype=np.int32),
        valid_pixels=np.ones((48, 48), dtype=np.bool_),
    )

    assert records == ()
