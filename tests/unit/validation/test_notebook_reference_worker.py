# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Synthetic native outputs exercise the notebook worker without finders."""

from __future__ import annotations

import ast
import json
import os
import runpy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest
from astropy.io import fits
from astropy.table import Table

_ROOT = Path(__file__).parents[3]
_SCRIPT = _ROOT / "scripts/benchmark/run_notebook_reference.py"


@pytest.fixture
def worker() -> dict[str, Any]:
    return runpy.run_path(str(_SCRIPT))


@pytest.fixture
def image_path(tmp_path: Path) -> Path:
    header = fits.Header(
        {
            "BUNIT": "Jy/beam",
            "BMAJ": 0.001,
            "BMIN": 0.001,
            "BPA": 0.0,
            "CTYPE1": "RA---TAN",
            "CTYPE2": "DEC--TAN",
            "RADESYS": "ICRS",
            "CRPIX1": 5,
            "CRPIX2": 5,
            "CRVAL1": 180,
            "CRVAL2": 45,
            "CDELT1": -0.0003,
            "CDELT2": 0.0003,
        }
    )
    path = tmp_path / "input.fits"
    fits.PrimaryHDU(np.zeros((9, 11)), header).writeto(path)
    return path


@pytest.fixture
def fake_native(
    worker: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> list[dict[str, Any]]:
    """Replace only external finder computation; retain native readers."""
    calls: list[dict[str, Any]] = []
    original_helpers = worker["_helpers"]

    def helpers(name: str) -> dict[str, Any]:
        runner = original_helpers(name)
        if name == "run_phase5_external_pybdsf.py":

            def pybdsf(
                _module: Any, adapter: Any, config: Any, stage: Path
            ) -> Any:
                assert adapter.artifact_path("image").is_file()
                calls.append(config)
                sources = stage / "sources.fits"
                Table(names=("Source_id",), dtype=(int,)).write(sources)
                labels = stage / "labels.fits"
                fits.PrimaryHDU(np.zeros((9, 11), dtype=np.int32)).writeto(
                    labels
                )
                mask = stage / "mask.fits"
                mask.write_bytes(labels.read_bytes())
                return {
                    "source-catalogue-fits": sources,
                    "gaussian-catalogue-fits": sources,
                    "island-labels-fits": labels,
                    "island-mask-fits": mask,
                }

            runner["_run_pybdsf"] = pybdsf
        if name == "run_phase5_external_aegean.py":

            def aegean(adapter: Any, config: Any, stage: Path) -> Any:
                assert adapter.artifact_path("image").is_file()
                calls.append(config)
                component, island = stage / "comp.fits", stage / "isle.fits"
                runner["_write_empty_catalogues"](component, island)
                labels = stage / "labels.fits"
                fits.PrimaryHDU(np.zeros((9, 11), dtype=np.int32)).writeto(
                    labels
                )
                exclusions = stage / "exclusions.json"
                exclusions.write_text("{}")
                return {
                    "component-catalogue-fits": component,
                    "island-catalogue-fits": island,
                    "support-proxy-labels-fits": labels,
                    "catalogue-exclusions-json": exclusions,
                }

            runner["_run_aegean"] = aegean
        return runner

    monkeypatch.setitem(
        worker["run_reference"].__globals__, "_helpers", helpers
    )

    def identity(finder: str) -> dict[str, str]:
        return {"runtime_name": finder, "runtime_version": "test"}

    monkeypatch.setitem(
        worker["run_reference"].__globals__,
        "runtime_identity",
        identity,
    )
    original_import = worker["importlib"].import_module

    def import_module(name: str, *args: Any) -> Any:
        return (
            SimpleNamespace()
            if name == "bdsf"
            else original_import(name, *args)
        )

    monkeypatch.setattr(
        worker["importlib"],
        "import_module",
        import_module,
    )
    return calls


@pytest.mark.parametrize("finder", ["released-pybdsf", "aegean"])
def test_empty_native_outputs_are_published_and_readable(
    tmp_path: Path,
    worker: dict[str, Any],
    image_path: Path,
    fake_native: list[dict[str, Any]],
    finder: str,
) -> None:
    before_path = os.environ["PATH"]
    destination = tmp_path / "result"
    worker["run_reference"](
        image=image_path,
        output=destination,
        case_id="empty",
        finder=finder,
        container_image_id="sha256:" + "a" * 64,
        ncores=2,
    )
    result = json.loads((destination / "result.json").read_text())
    assert result["status"] == "success"
    assert result["finder_id"] == finder
    assert result["scientific_claims_authorized"] is False
    assert (
        json.loads((destination / "comparison_catalogue.json").read_text())
        == []
    )
    assert os.environ["PATH"] == before_path
    config = fake_native[0]
    if finder == "released-pybdsf":
        assert config["ncores"] == 2
        assert config["thresh_pix"] == 5.0
        assert config["atrous_do"] is True
    else:
        assert config["cores"] == 2
        assert (config["seedclip"], config["floodclip"]) == (5.0, 4.0)
    public = worker["_helpers"]("run_phase5_public_reference_finder.py")
    for artifact in result["artifacts"].values():
        assert (
            public["_sha256"](destination / artifact["path"])
            == artifact["sha256"]
        )
    with pytest.raises(FileExistsError):
        worker["run_reference"](
            image=image_path,
            output=destination,
            case_id="empty",
            finder=finder,
            container_image_id="sha256:" + "a" * 64,
            ncores=2,
        )


@pytest.mark.parametrize("version", ["1.14.1", "unexpected"])
def test_runtime_records_actual_inventory_and_rejects_wrong_release(
    worker: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    version: str,
) -> None:
    identity = worker["runtime_identity"]

    def observed_version(_package: str) -> str:
        return version

    monkeypatch.setattr(
        worker["importlib"].metadata, "version", observed_version
    )
    monkeypatch.setitem(
        identity.__globals__,
        "dependency_inventory_sha256",
        lambda: "actual-inventory",
    )
    if version == "unexpected":
        with pytest.raises(ValueError, match="found unexpected"):
            identity("released-pybdsf")
    else:
        assert (
            identity("released-pybdsf")["dependency_inventory_sha256"]
            == "actual-inventory"
        )


@pytest.mark.usefixtures("fake_native")
def test_failure_restores_environment_and_does_not_publish(
    tmp_path: Path,
    worker: dict[str, Any],
    image_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = worker["_helpers"]

    def helpers(name: str) -> dict[str, Any]:
        runner = original(name)
        if name == "run_phase5_external_aegean.py":

            def fail(*_args: Any) -> None:
                raise RuntimeError("external failure")

            runner["_run_aegean"] = fail
        return runner

    monkeypatch.setitem(
        worker["run_reference"].__globals__, "_helpers", helpers
    )
    before = os.environ["PATH"]
    with pytest.raises(RuntimeError, match="external failure"):
        worker["run_reference"](
            image=image_path,
            output=tmp_path / "result",
            case_id="empty",
            finder="aegean",
            container_image_id="image",
            ncores=1,
        )
    assert os.environ["PATH"] == before
    assert sorted(path.name for path in tmp_path.iterdir()) == ["input.fits"]


def test_prepared_outputs_load_in_notebook_and_hebog_input_resolver(
    tmp_path: Path,
    worker: dict[str, Any],
    image_path: Path,
    fake_native: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise setup -> native records -> actual notebook display helpers."""
    setup = runpy.run_path(
        str(_SCRIPT.with_name("prepare_notebook_comparison.py"))
    )
    prepare = setup["prepare_comparison"]

    def inspect(*_args: Any) -> dict[str, str]:
        return {
            "released-pybdsf": "sha256:" + "a" * 64,
            "aegean": "sha256:" + "b" * 64,
        }

    monkeypatch.setitem(
        prepare.__globals__,
        "_inspect_images",
        inspect,
    )

    def download(_url: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(image_path.read_bytes())

    monkeypatch.setitem(prepare.__globals__, "_download", download)

    def execute(**kwargs: Any) -> None:
        worker["run_reference"](
            image=kwargs["input_path"],
            output=kwargs["output"],
            case_id=kwargs["case_id"],
            finder=kwargs["finder_id"],
            container_image_id=kwargs["image"],
            ncores=kwargs["ncores"],
            core=kwargs["core"],
        )

    monkeypatch.setitem(prepare.__globals__, "_run_container", execute)
    root = tmp_path / "comparison"
    prepare(
        repository_root=tmp_path,
        output=root,
        datasets=("lotss-dr2-3c295-12arcmin",),
        images={"released-pybdsf": "pybdsf", "aegean": "aegean"},
    )
    notebook_path = _ROOT / "notebooks/campaign_source_finder_comparison.py"
    tree = ast.parse(notebook_path.read_text())
    imports_cell = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and any(isinstance(child, ast.ClassDef) for child in node.body)
    )
    loader_cell = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(child, ast.FunctionDef)
            and child.name == "load_campaign_cases"
            for child in node.body
        )
    )
    body: list[ast.stmt] = [
        ast.ImportFrom(
            module="__future__", names=[ast.alias(name="annotations")], level=0
        )
    ]
    body += [
        node
        for node in imports_cell.body
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.ClassDef))
    ]
    body += [
        node for node in loader_cell.body if isinstance(node, ast.FunctionDef)
    ]
    namespace: dict[str, Any] = {
        "__name__": __name__,
        "__file__": str(tmp_path / "notebooks/comparison.py"),
    }
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=body, type_ignores=[])),
            str(notebook_path),
            "exec",
        ),
        namespace,
    )
    kind, cases = namespace["load_campaign_cases"](root / "reference-campaign")
    assert kind == "public"
    assert len(cases) == 1
    assert len(cases[0].runs) == 2
    loaded, _path, overlays, _truth, warnings = namespace[
        "load_case_overlays"
    ](
        cases[0],
        tmp_path,
        root / "reference-campaign",
    )
    assert loaded.shape == (9, 11)
    assert set(overlays) == {
        "released-pybdsf/operational",
        "aegean/operational",
    }
    assert all(item.status == "success" for item in overlays.values())
    assert warnings == []
    assert (
        namespace["notebook_history_root"](root / "reference-campaign")
        == root / "hebog-refreshes"
    )
    history = root / "hebog-refreshes"
    history.mkdir()
    (history / "index.json").write_text("{}")
    assert namespace["notebook_history_root"](history / "run") == history
    resolver = runpy.run_path(
        str(_SCRIPT.with_name("run_phase5_current_public_hebog_campaign.py"))
    )
    path, core, record = resolver["_resolve_input"](
        tmp_path, root / "input-campaign", "lotss-dr2-3c295-12arcmin"
    )
    assert (
        path.is_file()
        and core is None
        and record["case_id"] == "lotss-dr2-3c295-12arcmin"
    )
    assert len(fake_native) == 2


@pytest.mark.parametrize("invalid", ["cores", "cube", "changed-input"])
def test_worker_failure_never_publishes_partial_products(
    worker: dict[str, Any],
    image_path: Path,
    fake_native: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    invalid: str,
) -> None:
    tmp_path = image_path.parent
    if invalid == "cube":
        fits.PrimaryHDU(np.zeros((2, 3, 4))).writeto(
            image_path, overwrite=True
        )
    if invalid == "changed-input":
        original = worker["_execute"]

        def execute(**kwargs: Any) -> Any:
            result = original(**kwargs)
            fits.setval(
                image_path, "HISTORY", value="changed during execution"
            )
            return result

        monkeypatch.setitem(
            worker["run_reference"].__globals__, "_execute", execute
        )
    with pytest.raises(ValueError, match=r"positive|2D|changed"):
        worker["run_reference"](
            image=image_path,
            output=tmp_path / "result",
            case_id="case",
            finder="released-pybdsf",
            container_image_id="image",
            ncores=0 if invalid == "cores" else 1,
        )
    assert not (tmp_path / "result").exists()
    assert len(fake_native) == (1 if invalid == "changed-input" else 0)


@pytest.mark.parametrize("core", [None, (2, 7, 3, 9)])
def test_worker_cli_passes_typed_paths_and_resource_options(
    worker: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    core: tuple[int, int, int, int] | None,
) -> None:
    received: dict[str, Any] = {}

    def execute(**kwargs: Any) -> None:
        received.update(kwargs)

    monkeypatch.setitem(worker["main"].__globals__, "run_reference", execute)
    monkeypatch.setattr(
        "sys.argv",
        [
            str(_SCRIPT),
            "--input",
            "/input.fits",
            "--output",
            "/output",
            "--case-id",
            "case",
            "--finder-id",
            "aegean",
            "--container-image-id",
            "image",
            "--ncores",
            "3",
            *(["--core", *(str(item) for item in core)] if core else []),
        ],
    )
    worker["main"]()
    assert received == {
        "image": Path("/input.fits"),
        "output": Path("/output"),
        "case_id": "case",
        "finder": "aegean",
        "container_image_id": "image",
        "ncores": 3,
        "core": core,
    }


@pytest.mark.parametrize("finder", ["released-pybdsf", "aegean"])
def test_reference_preserves_sdc1_core(
    tmp_path: Path,
    worker: dict[str, Any],
    image_path: Path,
    fake_native: list[dict[str, Any]],
    finder: str,
) -> None:
    output = tmp_path / "core-result"
    worker["run_reference"](
        image=image_path,
        output=output,
        case_id="sdc1-fixture",
        finder=finder,
        container_image_id="image",
        ncores=1,
        core=(2, 7, 3, 9),
    )
    assert len(fake_native) == 1
    result = json.loads((output / "result.json").read_text())
    assert result["core_bounds_yx_half_open"] == [2, 7, 3, 9]
    role = (
        "island-labels-fits"
        if finder == "released-pybdsf"
        else "support-proxy-labels-fits"
    )
    assert cast(
        Any, fits.getdata(output / result["artifacts"][role]["path"])
    ).squeeze().shape == (
        5,
        6,
    )
    assert cast(
        Any,
        fits.getdata(output / result["artifacts"][f"native-{role}"]["path"]),
    ).shape == (9, 11)


@pytest.mark.parametrize(
    "core", [(-1, 5, 0, 5), (0, 10, 0, 5), (0, 5, 2, 12), (4, 2, 0, 5)]
)
def test_invalid_core_stops_before_finder(
    tmp_path: Path,
    worker: dict[str, Any],
    image_path: Path,
    fake_native: list[dict[str, Any]],
    core: tuple[int, int, int, int],
) -> None:
    with pytest.raises(ValueError, match="core exceeds"):
        worker["run_reference"](
            image=image_path,
            output=tmp_path / "invalid",
            case_id="invalid",
            finder="aegean",
            container_image_id="image",
            ncores=1,
            core=core,
        )
    assert fake_native == []
    assert not (tmp_path / "invalid").exists()
