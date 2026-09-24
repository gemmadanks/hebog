"""Contracts of component calibration statistics.

The endpoint these statistics serve must describe every matched component,
not only the ones that happen to publish an uncertainty. Hebog publishes a
beam-constrained shape without a shape uncertainty when a free fit is not
significantly extended, so a pull statistic silently covers a minority that
is selected for having fluctuated large.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

import pytest

from hebog.validation.component_calibration import (
    ComponentComparison,
    great_circle_right_ascension_error_degrees,
    summarise_component_calibration,
)


def _comparison(
    *,
    matched: bool = True,
    beam_constrained: bool = False,
    excesses: Mapping[str, float | None] | None = None,
    pulls: Mapping[str, float | None] | None = None,
) -> ComponentComparison:
    """Return one matched component with the fields a test cares about."""
    return ComponentComparison(
        matched=matched,
        beam_constrained=beam_constrained,
        excesses={"integrated": 0.0, "major": 0.0} | dict(excesses or {}),
        pulls={"integrated": 0.0, "major": None} | dict(pulls or {}),
    )


def test_excess_covers_every_matched_component() -> None:
    """The published value is measurable whether or not an error is."""
    rows = [
        *[_comparison() for _ in range(3)],
        _comparison(excesses={"major": 0.12}, pulls={"major": 1.5}),
    ]

    summary = summarise_component_calibration(rows)

    assert summary["matched"] == 4
    assert summary["excess"]["major"]["count"] == 4
    assert summary["excess"]["major"]["median"] == pytest.approx(0.0)
    assert summary["pull"]["major"]["count"] == 1
    assert summary["pull"]["major"]["median"] == pytest.approx(1.5)


def test_pull_statistics_report_how_much_of_the_population_they_cover() -> (
    None
):
    """A pull over a selected minority must say so beside its median."""
    rows = [
        *[_comparison() for _ in range(9)],
        _comparison(pulls={"major": 2.0}),
    ]

    summary = summarise_component_calibration(rows)

    assert summary["pull"]["major"]["reported_fraction"] == pytest.approx(0.1)
    assert summary["pull"]["integrated"]["reported_fraction"] == pytest.approx(
        1.0
    )


def test_coverage_and_spread_describe_the_reported_pulls() -> None:
    rows = [
        _comparison(pulls={"integrated": value})
        for value in (-2.0, -0.5, 0.0, 0.5, 2.0)
    ]

    pulls = summarise_component_calibration(rows)["pull"]["integrated"]

    assert pulls["median"] == pytest.approx(0.0)
    assert pulls["coverage"] == pytest.approx(0.6)
    assert pulls["standard_deviation"] == pytest.approx(1.5, abs=0.2)


def test_excess_reports_a_tail_as_well_as_a_median() -> None:
    """A median hides the flux tail that Rapthor consumes."""
    rows = [
        _comparison(excesses={"integrated": value})
        for value in (0.0, 0.01, 0.02, 0.03, 0.80)
    ]

    excess = summarise_component_calibration(rows)["excess"]["integrated"]

    assert excess["median"] == pytest.approx(0.02)
    # The tail, not the median, is what a flux outlier shows up in.
    assert excess["absolute_p95"] > 0.5


def test_unmatched_components_count_against_completeness_only() -> None:
    rows = [
        _comparison(),
        _comparison(
            matched=False,
            excesses={"integrated": None, "major": None},
            pulls={"integrated": None},
        ),
    ]

    summary = summarise_component_calibration(rows)

    assert summary["sources"] == 2
    assert summary["matched"] == 1
    assert summary["completeness"] == pytest.approx(0.5)
    assert summary["excess"]["integrated"]["count"] == 1


def test_the_beam_constrained_share_is_reported() -> None:
    """It explains the selection behind every shape statistic below it."""
    rows = [
        _comparison(beam_constrained=True),
        _comparison(beam_constrained=True),
        _comparison(beam_constrained=False, excesses={"major": 0.1}),
    ]

    summary = summarise_component_calibration(rows)

    assert summary["beam_constrained_fraction"] == pytest.approx(2 / 3)


def test_a_stratum_without_matches_reports_no_statistics() -> None:
    summary = summarise_component_calibration(
        [
            _comparison(
                matched=False,
                excesses={"integrated": None, "major": None},
                pulls={"integrated": None},
            )
        ]
    )

    assert summary["completeness"] == pytest.approx(0.0)
    assert summary["excess"]["integrated"] is None
    assert summary["pull"]["integrated"] is None
    assert summary["beam_constrained_fraction"] is None


@pytest.mark.parametrize(
    ("declination", "expected"),
    (
        (0.0, 0.002),
        (45.0, 0.002 / math.sqrt(2.0)),
        (-45.0, 0.002 / math.sqrt(2.0)),
        (60.0, 0.001),
    ),
)
def test_a_coordinate_ra_error_becomes_a_great_circle_error(
    declination: float, expected: float
) -> None:
    """The offset is great-circle, so the divisor has to be as well.

    Hebog publishes ``E_RA`` as an error on the RA coordinate, larger than the
    on-sky error by 1/cos(dec). Dividing a great-circle offset by it directly
    would report a pull a factor cos(dec) too small, and the sign of the
    declination cannot change the conversion.
    """
    assert great_circle_right_ascension_error_degrees(
        0.002, declination_degrees=declination
    ) == pytest.approx(expected)


def test_an_unpublished_ra_error_has_no_great_circle_value() -> None:
    """A component without an uncertainty has no pull to convert."""
    assert (
        great_circle_right_ascension_error_degrees(
            None, declination_degrees=45.0
        )
        is None
    )
