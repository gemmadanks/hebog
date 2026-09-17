"""Tests for public measurements projected into pixel coordinates."""

from __future__ import annotations

import numpy as np
import pytest

from hebog.validation.public_measurement_projection import (
    ContinuumCatalogueObject,
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
    """Projected rows cannot encode an invented measurement."""
    values: dict[str, object] = {
        "identifier": "source-1",
        "support_label": 1,
        "centre_xy": (1.0, 1.0),
        "integrated_flux_jy": 1.0,
    }
    values.update(changes)

    with pytest.raises(ValueError, match=message):
        ContinuumCatalogueObject(**values)  # type: ignore[arg-type]
