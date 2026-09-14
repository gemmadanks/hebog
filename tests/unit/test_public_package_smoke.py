"""The installed-workflow checker rejects missing or dishonest products."""

from __future__ import annotations

import hashlib
import runpy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.mark.parametrize(
    "defect,message",
    (
        ("none", None),
        ("empty-none", None),
        ("hash", "product identity"),
        ("count", "run identity"),
        ("run", "run identity"),
        ("shape", "wrong shape"),
        ("gaussian", "lost its isolated source"),
        ("empty-gaussian", "control has sources"),
        ("empty-noise", "invents noise"),
    ),
)
def test_package_product_checker_rejects_broken_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    defect: str,
    message: str | None,
) -> None:
    """Fault injection tests the checker, not another source-finder path."""
    namespace = runpy.run_path(
        str(Path(__file__).parents[2] / "scripts/public_api_package_smoke.py")
    )
    check = namespace["_check_products"]
    path = tmp_path / "product"
    path.write_bytes(b"bounded-checker-fixture")
    empty = defect.startswith("empty-")
    product = SimpleNamespace(
        path=path,
        content_sha256=(
            "0" * 64
            if defect == "hash"
            else hashlib.sha256(path.read_bytes()).hexdigest()
        ),
        scientific_status="valid"
        if defect == "empty-noise"
        else "unavailable",
    )
    result = SimpleNamespace(
        run_id="fixture",
        catalogue=product,
        rms=product,
        mask=product,
        diagnostics=product,
        rms_path=path,
        mask_path=path,
        source_count=0 if empty or defect == "count" else 1,
    )
    catalogue = SimpleNamespace(
        sources=() if empty else ("source",),
        gaussian_components=(
            ()
            if defect == "gaussian" or (empty and defect != "empty-gaussian")
            else ("gaussian",)
        ),
    )
    diagnostics = SimpleNamespace(
        run_id="wrong" if defect == "run" else "fixture"
    )

    def read_catalogue(_product: object) -> SimpleNamespace:
        return catalogue

    def read_diagnostics(_product: object) -> SimpleNamespace:
        return diagnostics

    def read_image(_path: object) -> np.ndarray:
        return np.zeros((1, 2) if defect == "shape" else (2, 2))

    monkeypatch.setitem(
        check.__globals__, "read_catalogue_fits_product", read_catalogue
    )
    monkeypatch.setitem(
        check.__globals__, "read_diagnostics_product", read_diagnostics
    )
    monkeypatch.setattr(
        namespace["fits"],
        "getdata",
        read_image,
    )
    if message is None:
        check(result, (2, 2), empty=empty)
    else:
        with pytest.raises(RuntimeError, match=message):
            check(result, (2, 2), empty=empty)
