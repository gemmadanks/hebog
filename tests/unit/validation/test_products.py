# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportAttributeAccessIssue=false
"""Tests for validation product readers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from astropy.io import fits

from hebog.validation.products import load_pybdsf_catalogue

_ROOT = Path(__file__).parents[3]
_CATALOGUE = (
    _ROOT / "tests/data/pybdsf/pybdsf-compact-reference-256/release/"
    "source_catalog.fits"
)


def test_pybdsf_reader_treats_nonpositive_errors_as_unavailable(
    tmp_path: Path,
) -> None:
    """PyBDSF zero and NaN sentinels do not become invalid uncertainties."""
    output = tmp_path / "catalogue.fits"
    with fits.open(_CATALOGUE) as source:
        source[1].data["E_RA"][0] = np.nan
        source[1].data["E_Maj"][0] = 0.0
        source.writeto(output)

    row = load_pybdsf_catalogue(output)[0]

    assert row.right_ascension_error_degrees is None
    assert row.fitted_shape is not None
    assert row.fitted_shape.major_fwhm_error_degrees is None
