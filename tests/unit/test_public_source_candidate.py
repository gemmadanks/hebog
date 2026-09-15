# pyright: reportPrivateUsage=false
"""Public catalogue projection of one evaluated source row."""

from __future__ import annotations

import pytest

from hebog import public_api
from hebog.science.models import CatalogueSource


def _source(
    *,
    deconvolved_major_fwhm_degrees: float | None,
    quality_flags: tuple[str, ...],
) -> CatalogueSource:
    return CatalogueSource(
        identifier="source-1",
        right_ascension_degrees=180.0,
        declination_degrees=-30.0,
        peak_flux_jy_per_beam=0.2,
        integrated_flux_jy=0.3,
        deconvolved_major_fwhm_degrees=deconvolved_major_fwhm_degrees,
        deconvolution_status=(
            "unavailable"
            if deconvolved_major_fwhm_degrees is None
            else "major-axis-only"
        ),
        quality_flags=quality_flags,
    )


@pytest.mark.parametrize(
    ("major_fwhm", "input_flags", "expected_flags"),
    (
        (1.0e-3, ("edge", "major-axis-only"), ("edge", "major-axis-only")),
        (None, ("edge", "major-axis-only"), ("edge",)),
        (None, (), ()),
    ),
    ids=("major-axis-only", "stale-flag-removed", "unflagged"),
)
def test_major_axis_only_flag_follows_the_published_measurement(
    major_fwhm: float | None,
    input_flags: tuple[str, ...],
    expected_flags: tuple[str, ...],
) -> None:
    """A row is flagged exactly when it publishes a major-axis-only size."""
    candidate = public_api._source_candidate(
        _source(
            deconvolved_major_fwhm_degrees=major_fwhm,
            quality_flags=input_flags,
        ),
        island_id="island-1",
        local_rms=0.01,
        reference_frequency_hz=144.0e6,
        additional_island_ids=("island-2",),
    )

    assert candidate.quality_flags == expected_flags
    assert candidate.deconvolved_major_fwhm_degrees == major_fwhm
    assert candidate.additional_island_ids == ("island-2",)
    assert candidate.flux.local_rms_jy_per_beam == 0.01
