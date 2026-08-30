# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownLambdaType=false
# pyright: reportUnknownVariableType=false
"""Contracts for the parent-construction provenance repair boundary."""

from __future__ import annotations

import json
import runpy
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

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
from hebog.validation.external_runners import file_sha256
from hebog.validation.parent_construction_association_evaluation import (
    ParentConstructionContinuumImageCompiler,
    install_parent_construction_association_evaluation,
)
from hebog.validation.source_association_evaluation_repair import (
    AssociatedContinuumCatalogueObject,
    associated_source_identifier,
    detection_component_identifier,
)

_ROOT = Path(__file__).parents[3]
_FAILURE = (
    _ROOT / "config/contracts/phase-5-public-finder-source-hierarchy-parent-"
    "construction-evaluation-provenance-failure.json"
)
_PRE_REVIEW = (
    _ROOT / "config/contracts/phase-5-public-finder-source-hierarchy-parent-"
    "construction-association-provenance-repair-pre-review.json"
)
_IMPLEMENTATION_DECISION = (
    _ROOT / "config/contracts/phase-5-public-finder-source-hierarchy-parent-"
    "construction-association-provenance-repair-implementation-decision.json"
)
_PROGRAM = (
    _ROOT / "scripts/validation/reconstruct_phase5_parent_construction_"
    "associations.py"
)
_OVERLAY = (
    _ROOT
    / "src/hebog/validation/parent_construction_association_evaluation.py"
)
_FROZEN_COMPILER = _ROOT / "src/hebog/validation/external_recovery_compiler.py"
_FROZEN_ASSOCIATION_EVALUATOR = (
    _ROOT / "src/hebog/validation/source_association_evaluation_repair.py"
)


def test_failure_separates_complete_products_from_absent_science() -> None:
    """A compiler defect cannot be presented as a scientific gate result."""
    failure = json.loads(_FAILURE.read_text(encoding="utf-8"))

    assert failure["status"] == (
        "failed-after-complete-candidate-products-before-atomic-ledger"
    )
    assert failure["candidate_execution"] == {
        "compact_product_count": 800,
        "continuum_product_count": 1600,
        "progress_line_count": 2400,
        "status": "complete",
        "total_product_count": 2400,
    }
    assert failure["output_published"] is False
    assert "source_association" in failure["failure"]["missing_evidence"]


def test_pre_review_requires_sidecar_truth_and_preserves_products() -> None:
    """The repair rejects coordinate inference and candidate mutation."""
    review = json.loads(_PRE_REVIEW.read_text(encoding="utf-8"))
    boundary = review["implementation_boundary"]

    assert review["status"] == (
        "implementation-authorized-by-explicit-user-fix-request"
    )
    assert any(
        "run-aware compiler seam" in action for action in boundary["allowed"]
    )
    assert any(
        "reruns only the frozen 1,600 Continuum" in action
        for action in boundary["allowed"]
    )
    assert any(
        "overwriting any of the 2,400" in action
        for action in boundary["forbidden"]
    )
    assert any(
        "inferring cryptographic membership" in action
        for action in boundary["forbidden"]
    )
    assert any(
        "before an exact execution decision" in action
        for action in boundary["forbidden"]
    )


def test_implementation_keeps_frozen_programs_byte_identical() -> None:
    """The sidecar repair has its own identity and no historical drift."""
    decision = json.loads(_IMPLEMENTATION_DECISION.read_text(encoding="utf-8"))
    implementation = decision["implementation"]

    assert implementation["evaluation_overlay_sha256"] == file_sha256(_OVERLAY)
    assert implementation["reconstruction_program_sha256"] == file_sha256(
        _PROGRAM
    )
    assert implementation["frozen_recovery_compiler_sha256"] == (
        file_sha256(_FROZEN_COMPILER)
    )
    assert implementation[
        "frozen_source_association_evaluator_sha256"
    ] == file_sha256(_FROZEN_ASSOCIATION_EVALUATOR)
    assert decision["authorization"][
        "provenance_reconstruction_authorized"
    ] is (False)


def test_reconstruction_authorization_rejects_broader_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One future sidecar decision cannot silently authorize science."""
    module = runpy.run_path(str(_PROGRAM))
    authorize = module["_authorize_reconstruction"]
    globals_ = authorize.__globals__
    composition = {"status": "pass"}
    decision = {
        "failure_sha256": file_sha256(_FAILURE),
        "implementation_decision_sha256": file_sha256(
            _IMPLEMENTATION_DECISION
        ),
        "pre_review_sha256": file_sha256(_PRE_REVIEW),
        "prohibited_authorizations": deepcopy(
            globals_["_PROHIBITED_AUTHORIZATIONS"]
        ),
        "reconstruction_authorized": True,
        "reconstruction_program_sha256": file_sha256(_PROGRAM),
        "status": "reviewed-before-association-provenance-reconstruction",
        "verified_composition": composition,
    }
    monkeypatch.setitem(
        globals_, "_json_object", lambda *_args, **_kwargs: decision
    )

    assert authorize(composition) is decision
    prohibited = cast(
        dict[str, bool], decision["prohibited_authorizations"]
    )
    prohibited["release_authorized"] = True
    with pytest.raises(ValueError, match="authority changed"):
        authorize(composition)


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


def test_sidecar_reconstruction_preserves_existing_science(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the omitted association survives exact product comparison."""
    module = runpy.run_path(str(_PROGRAM))
    reconstruct = module["_reconstruct_one"]
    globals_ = reconstruct.__globals__
    preserved = tmp_path / "preserved"
    preserved.mkdir()
    artifact_names = {
        "segment-catalogue-json": "catalogue.json",
        "segment-labels-fits": "labels.fits",
        "segment-mask-fits": "mask.fits",
    }
    for role, name in artifact_names.items():
        (preserved / name).write_bytes(role.encode())
    artifacts = [
        {
            "role": role,
            "relative_path": name,
            "byte_count": (preserved / name).stat().st_size,
            "sha256": file_sha256(preserved / name),
        }
        for role, name in artifact_names.items()
    ]
    (preserved / "complete.json").write_text(
        json.dumps({"artifacts": artifacts}), encoding="utf-8"
    )
    association = SourceAssociationResult(
        components=(), edges=(), memberships=()
    )

    def builder(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(source_association=association)

    def writer(
        _dataset: object,
        *,
        output: Path,
        **_kwargs: object,
    ) -> dict[str, Path]:
        writer.__globals__["build_post_correction_continuum_products"]()
        output_paths: dict[str, Path] = {}
        for role, name in artifact_names.items():
            path = output / name
            path.write_bytes(role.encode())
            output_paths[role] = path
        return output_paths

    writer.__globals__["build_post_correction_continuum_products"] = builder
    frozen: dict[str, Any] = {"_write_continuum_products": writer}
    monkeypatch.setitem(
        globals_,
        "_load_parent_wrapper",
        lambda: {
            "_load_source_association_composition": lambda: ({}, {}, frozen),
            "_install_parent_construction_static_seams": (
                lambda _frozen: None
            ),
        },
    )
    monkeypatch.setitem(
        globals_,
        "DatasetRecord",
        SimpleNamespace(model_validate=lambda _value: SimpleNamespace()),
    )
    monkeypatch.setitem(
        globals_, "load_comparison_catalogue", lambda _path: ()
    )
    monkeypatch.setitem(globals_, "load_fits_plane", lambda _path: [])

    def verify_association(*_args: object, **_kwargs: object) -> tuple[()]:
        return ()

    monkeypatch.setitem(
        globals_,
        "continuum_catalogue_objects_from_association",
        verify_association,
    )
    monkeypatch.setattr(
        "astropy.io.fits.getheader", lambda _path: SimpleNamespace()
    )
    destination = tmp_path / "sidecars" / "input-1"
    task = {
        "association_directory": str(destination),
        "dataset": {},
        "image_path": "image.fits",
        "input_id": "input-1",
        "mean_path": "mean.fits",
        "output_directory": str(preserved),
        "rms_path": "rms.fits",
    }

    assert reconstruct(task) == "input-1"
    assert {item.name for item in destination.iterdir()} == {
        "complete.json",
        "source_association.json",
    }
