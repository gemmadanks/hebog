# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownLambdaType=false
# pyright: reportUnknownVariableType=false
"""Contracts for the parent-construction provenance repair boundary."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from astropy.io import fits

from hebog.data_models.source_association import (
    CatalogueSourceMembership,
    DetectionComponentRecord,
    SourceAssociationResult,
)
from hebog.validation.comparison import CatalogueSource
from hebog.validation.external_recovery_compiler import (
    RecoveryContinuumImageCompiler,
)
from hebog.validation.parent_construction_association_evaluation import (
    ParentConstructionContinuumImageCompiler,
    install_parent_construction_association_evaluation,
)
from hebog.validation.source_association_evaluation_repair import (
    AssociatedContinuumCatalogueObject,
    associated_source_identifier,
    detection_component_identifier,
)


def _header() -> fits.Header:
    """Return one small valid celestial header."""
    header = fits.Header()
    header["NAXIS"] = 2
    header["NAXIS1"] = 2
    header["NAXIS2"] = 1
    header["CTYPE1"] = "RA---TAN"
    header["CTYPE2"] = "DEC--TAN"
    header["CRPIX1"] = 1.0
    header["CRPIX2"] = 1.0
    header["CRVAL1"] = 10.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -0.001
    header["CDELT2"] = 0.001
    return header


def _associated_fixture(
    path: Path,
) -> tuple[CatalogueSource, np.ndarray[Any, Any]]:
    """Write identity evidence whose recovered support starts earlier."""
    component_id = detection_component_identifier((0, 1))
    source_id = associated_source_identifier((component_id,))
    association = SourceAssociationResult(
        components=(
            DetectionComponentRecord(
                component_id=component_id,
                label_value=7,
                canonical_pixel_yx=(0, 1),
                centroid_yx=(0.0, 1.0),
                covariance_pixels_squared=None,
            ),
        ),
        edges=(),
        memberships=(
            CatalogueSourceMembership(
                source_id=source_id,
                component_ids=(component_id,),
            ),
        ),
    )
    path.write_text(json.dumps(asdict(association)), encoding="utf-8")
    source = CatalogueSource(
        identifier=source_id,
        right_ascension_degrees=10.0,
        declination_degrees=-30.0,
        peak_flux_jy_per_beam=1.0,
        integrated_flux_jy=2.0,
        association_integrated_flux_jy=2.0,
        island_identifier=source_id,
        component_count=1,
    )
    return source, np.asarray(((7, 7),), dtype=np.int64)


def test_overlay_compiler_requires_explicit_association_sidecar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recovered owner coordinates are never used as direct identities."""
    association_path = tmp_path / "source-association.json"
    source, labels = _associated_fixture(association_path)
    measured: list[tuple[Any, ...]] = []
    fallback: list[str] = []

    def candidate_objects(
        *_args: object, **_kwargs: object
    ) -> tuple[str, ...]:
        fallback.append("used")
        return ("fallback",)

    terminal: dict[str, Any] = {
        "_input_artifact_path": (
            lambda _bundle, _input, _role: Path("image.fits")
        ),
        "load_fits_plane": lambda _path: np.ones(labels.shape),
        "_truth_objects": lambda *_args: (("truth",), labels),
        "_catalogue_and_labels": lambda _run: ((source,), labels),
        "_candidate_objects": candidate_objects,
        "measure_continuum_image": (
            lambda _truth, candidates, **_kwargs: (
                measured.append(candidates)
                or {"completeness": {"overall": 1.0}}
            )
        ),
        "EndpointObservation": lambda **kwargs: kwargs,
        "_failed_endpoint_observations": lambda *_args, **_kwargs: {},
    }
    monkeypatch.setattr(
        "hebog.validation.external_recovery_compiler.fits.getheader",
        lambda _path: _header(),
    )
    compiler = ParentConstructionContinuumImageCompiler(
        terminal,
        association_path=lambda _run: association_path,
    )
    run = SimpleNamespace(
        result=SimpleNamespace(
            status="success", failure=None, finder_id="hebog"
        )
    )
    arguments = (
        SimpleNamespace(
            inputs={"input-1": (SimpleNamespace(), Path("input.json"))}
        ),
        SimpleNamespace(input_id="input-1"),
        run,
        SimpleNamespace(beam=SimpleNamespace(major_fwhm_pixels=2.0)),
        SimpleNamespace(),
        SimpleNamespace(),
        (
            SimpleNamespace(
                metric_family="completeness",
                stratum="overall",
                endpoint_id="completeness-overall",
            ),
        ),
    )

    compiler(*arguments)

    assert isinstance(measured[0][0], AssociatedContinuumCatalogueObject)
    assert measured[0][0].support_labels == (7,)
    assert fallback == []
    run.result.finder_id = "released-pybdsf"
    compiler(*arguments)
    assert fallback == ["used"]
    run.result.finder_id = "hebog"
    association_path.unlink()
    with pytest.raises(ValueError, match="cannot be loaded"):
        ParentConstructionContinuumImageCompiler(
            terminal,
            association_path=lambda _run: association_path,
        )(*arguments)


def test_overlay_compiler_preserves_failed_run_policy() -> None:
    """A failed finder never resolves or reads an association sidecar."""
    compiler = ParentConstructionContinuumImageCompiler(
        {
            "_candidate_objects": lambda *_args, **_kwargs: (),
            "_failed_endpoint_observations": (
                lambda _specifications, **kwargs: {"endpoint": kwargs}
            ),
        },
        association_path=lambda _run: pytest.fail("sidecar was resolved"),
    )
    output = compiler(
        SimpleNamespace(),
        SimpleNamespace(input_id="input-1"),
        SimpleNamespace(
            result=SimpleNamespace(
                status="failure",
                failure=SimpleNamespace(message="finder failed exactly"),
            )
        ),
        SimpleNamespace(),
        SimpleNamespace(),
        SimpleNamespace(),
        (SimpleNamespace(endpoint_id="endpoint"),),
    )

    assert output["endpoint"]["reason"] == "finder failed exactly"


def test_overlay_installer_replaces_only_the_compiler_object() -> None:
    """Frozen functions and all unrelated terminal globals remain intact."""

    def candidate_objects(*_args: object, **_kwargs: object) -> tuple[()]:
        return ()

    def measure(*_args: object, **_kwargs: object) -> dict[object, object]:
        return {}

    unchanged = object()
    terminal: dict[str, Any] = {
        "_candidate_objects": candidate_objects,
        "measure_continuum_image": measure,
        "unchanged": unchanged,
    }
    terminal["_continuum_image_observations"] = RecoveryContinuumImageCompiler(
        terminal
    )

    install_parent_construction_association_evaluation(
        terminal,
        association_path=lambda _run: Path("association.json"),
    )

    assert isinstance(
        terminal["_continuum_image_observations"],
        ParentConstructionContinuumImageCompiler,
    )
    assert terminal["_candidate_objects"] is candidate_objects
    assert terminal["measure_continuum_image"] is measure
    assert terminal["unchanged"] is unchanged

    with pytest.raises(ValueError, match="evaluation seam changed"):
        install_parent_construction_association_evaluation(
            {}, association_path=lambda _run: Path("association.json")
        )
