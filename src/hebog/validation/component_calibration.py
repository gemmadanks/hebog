"""Statistics for component measurement calibration against injected truth.

Two questions are asked of every published component, and they are not the
same question:

- how far the published value lies from truth, which is measurable for
  every matched component; and
- how that distance compares with the published uncertainty, the pull,
  which is measurable only where an uncertainty is published.

Hebog publishes a beam-constrained shape, with no shape uncertainty, when a
free fit is not significantly extended. A pull statistic therefore covers
only the components whose free fit survived that test, which selects
upward fluctuations: on beam-sized sources the selected minority showed a
+12% median size excess while the population's excess was zero. Every pull
here is reported with the fraction of matched components it covers, so a
statistic over a selected minority cannot be read as a population result.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from math import cos, radians
from typing import Any

import numpy as np

_COVERAGE_LIMIT = 1.0
_TAIL_PERCENTILE = 95.0


@dataclass(frozen=True, slots=True)
class ComponentComparison:
    """One published component measured against its injected truth.

    ``excesses`` are fractional differences from truth, ``(published /
    truth) - 1``, except where a field documents another unit. ``pulls`` are
    those differences divided by the published uncertainty, and are ``None``
    where no uncertainty accompanies the value.
    """

    matched: bool
    beam_constrained: bool
    excesses: Mapping[str, float | None] = field(
        default_factory=dict[str, "float | None"]
    )
    pulls: Mapping[str, float | None] = field(
        default_factory=dict[str, "float | None"]
    )


def great_circle_right_ascension_error_degrees(
    right_ascension_error_degrees: float | None,
    *,
    declination_degrees: float,
) -> float | None:
    """Convert an error on the RA coordinate into a great-circle error.

    A pull divides an offset by an uncertainty, so the two must share a
    convention, and published catalogues do not agree on which one ``E_RA``
    uses. Hebog publishes an error on the RA coordinate: the tangent-plane
    one-sigma divided by cos(dec), in :mod:`hebog.algorithms.astrometry`.
    PyBDSF ``c70103be3`` publishes a great-circle error instead, because its
    ``pix2coord`` returns an angular separation. Position offsets are reported
    as great-circle angles, so a coordinate error is converted here rather than
    by scaling the offset, which would leave the pull a factor cos(dec) small.

    ``None`` passes through, because an unpublished uncertainty has no pull.

    Examples:
        >>> round(
        ...     great_circle_right_ascension_error_degrees(
        ...         0.002, declination_degrees=60.0
        ...     ),
        ...     9,
        ... )
        0.001
        >>> great_circle_right_ascension_error_degrees(
        ...     None, declination_degrees=60.0
        ... ) is None
        True
    """
    if right_ascension_error_degrees is None:
        return None
    return right_ascension_error_degrees * cos(radians(declination_degrees))


def _values(
    rows: Sequence[ComponentComparison],
    selector: str,
    *,
    pull: bool,
) -> list[float]:
    """Return the finite values of one field over matched components."""
    return [
        float(value)
        for row in rows
        if row.matched
        for value in ((row.pulls if pull else row.excesses).get(selector),)
        if value is not None and np.isfinite(value)
    ]


def _excess_statistics(
    values: Sequence[float], matched: int
) -> dict[str, float] | None:
    """Describe how far published values lie from truth."""
    if not values:
        return None
    array = np.asarray(values, dtype=np.float64)
    return {
        "count": int(array.size),
        "reported_fraction": array.size / matched,
        "median": float(np.median(array)),
        "absolute_p95": float(np.percentile(np.abs(array), _TAIL_PERCENTILE)),
    }


def _pull_statistics(
    values: Sequence[float], matched: int
) -> dict[str, float] | None:
    """Describe published uncertainties, and how much they describe.

    ``reported_fraction`` is the share of matched components carrying an
    uncertainty for this field. Read the median and coverage only against
    it: a small fraction means a selected subset, not the population.
    """
    if not values:
        return None
    array = np.asarray(values, dtype=np.float64)
    return {
        "count": int(array.size),
        "reported_fraction": array.size / matched,
        "median": float(np.median(array)),
        "standard_deviation": (
            float(np.std(array, ddof=1)) if array.size > 1 else float("nan")
        ),
        "coverage": float(np.mean(np.abs(array) <= _COVERAGE_LIMIT)),
    }


def summarise_component_calibration(
    rows: Sequence[ComponentComparison],
) -> dict[str, Any]:
    """Summarise one stratum of matched components.

    Excess statistics cover every matched component. Pull statistics cover
    only those publishing an uncertainty, and say what share that is.
    """
    matched_rows = [row for row in rows if row.matched]
    matched = len(matched_rows)
    fields = sorted(
        {name for row in rows for name in row.excesses}
        | {name for row in rows for name in row.pulls}
    )
    return {
        "sources": len(rows),
        "matched": matched,
        "completeness": matched / len(rows) if rows else 0.0,
        "beam_constrained_fraction": (
            sum(row.beam_constrained for row in matched_rows) / matched
            if matched
            else None
        ),
        "excess": {
            name: _excess_statistics(
                _values(rows, name, pull=False), matched or 1
            )
            for name in fields
        },
        "pull": {
            name: _pull_statistics(
                _values(rows, name, pull=True), matched or 1
            )
            for name in fields
        },
    }
