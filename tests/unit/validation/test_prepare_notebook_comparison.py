# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Offline notebook setup contracts: no real downloads or containers."""

from __future__ import annotations

import hashlib
import io
import json
import runpy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar, cast

import numpy as np
import pytest
from astropy.io import fits

_ROOT = Path(__file__).parents[3]
_SCRIPT = _ROOT / "scripts/benchmark/prepare_notebook_comparison.py"


@pytest.fixture
def setup() -> dict[str, Any]:
    return runpy.run_path(str(_SCRIPT))


def test_dry_run_has_no_side_effects(
    tmp_path: Path,
    setup: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("dry run must not inspect containers, download or execute")

    run = setup["prepare_comparison"]
    for name in ("_inspect_images", "_download", "_run_container"):
        monkeypatch.setitem(run.__globals__, name, forbidden)
    plan = run(
        repository_root=_ROOT,
        output=tmp_path / "outside",
        datasets=(),
        images={"released-pybdsf": "pybdsf", "aegean": "aegean"},
        dry_run=True,
    )
    assert len(plan["datasets"]) == 13
    assert sum(name.startswith("sdc1-") for name in plan["datasets"]) == 8
    assert {
        "hydra-deep",
        "hydra-shallow",
        "lotss-dr2-wide-ra13-90arcmin",
    } <= set(plan["datasets"])
    assert len(plan["downloads"]) == 6
    assert list(tmp_path.iterdir()) == []


@pytest.fixture
def fake_execution(
    tmp_path: Path,
    setup: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, Any], list[str]]:
    run = setup["prepare_comparison"]
    calls: list[str] = []

    def inspect(*_args: Any) -> dict[str, str]:
        return {
            "released-pybdsf": "sha256:" + "a" * 64,
            "aegean": "sha256:" + "b" * 64,
        }

    monkeypatch.setitem(
        run.__globals__,
        "_inspect_images",
        inspect,
    )
    monkeypatch.setitem(
        run.__globals__,
        "_download_inventory",
        lambda: {
            "hydra-deep-image": SimpleNamespace(
                filename="field.fits", url="https://example.invalid/field"
            )
        },
    )
    monkeypatch.setitem(
        run.__globals__, "_program_identity", lambda: "program-v1"
    )

    def download(_url: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"fixture FITS")
        calls.append("download")

    def execute(**kwargs: Any) -> None:
        destination = kwargs["output"]
        destination.mkdir(parents=True)
        (destination / "catalogue.json").write_text("[]")
        result: dict[str, Any] = {
            "status": "success",
            "case_id": kwargs["case_id"],
            "finder_id": kwargs["finder_id"],
            "mode": "operational",
            "input_sha256": setup["_sha256"](kwargs["input_path"]),
            "container_image_id": kwargs["image"],
            "artifacts": {
                "comparison-catalogue-json": {
                    "path": "catalogue.json",
                    "byte_size": 2,
                    "sha256": setup["_sha256"](destination / "catalogue.json"),
                }
            },
        }
        roles = (
            (
                "source-catalogue-fits",
                "gaussian-catalogue-fits",
                "island-labels-fits",
                "island-mask-fits",
            )
            if kwargs["finder_id"] == "released-pybdsf"
            else (
                "component-catalogue-fits",
                "island-catalogue-fits",
                "support-proxy-labels-fits",
                "catalogue-exclusions-json",
            )
        )
        for role in roles:
            result["artifacts"][role] = dict(
                result["artifacts"]["comparison-catalogue-json"]
            )
        (destination / "result.json").write_text(json.dumps(result))
        calls.append(kwargs["finder_id"])

    monkeypatch.setitem(run.__globals__, "_download", download)
    monkeypatch.setitem(run.__globals__, "_run_container", execute)
    arguments = {
        "repository_root": tmp_path,
        "output": tmp_path / "comparison",
        "datasets": ("hydra-deep",),
        "images": {"released-pybdsf": "pybdsf", "aegean": "aegean"},
    }
    return arguments, calls


def test_prepares_separate_inputs_and_reference_campaigns(
    setup: dict[str, Any],
    fake_execution: tuple[dict[str, Any], list[str]],
) -> None:
    arguments, calls = fake_execution
    setup["prepare_comparison"](**arguments)
    root = arguments["output"]
    inputs = json.loads((root / "input-campaign/campaign.json").read_text())
    references = json.loads(
        (root / "reference-campaign/campaign.json").read_text()
    )
    assert len(inputs["results"]) == 1
    assert len(references["results"]) == 2
    assert references["scientific_claims_authorized"] is False
    assert (root / "reference-campaign/inputs/hydra-deep/input.json").is_file()
    assert calls == ["download", "released-pybdsf", "aegean"]
    setup["prepare_comparison"](**arguments, resume=True)
    assert calls == ["download", "released-pybdsf", "aegean"]


def test_failure_can_resume_without_repeating_completed_finder(
    setup: dict[str, Any],
    fake_execution: tuple[dict[str, Any], list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arguments, calls = fake_execution
    run = setup["prepare_comparison"]
    execute = run.__globals__["_run_container"]

    def fail_aegean(**kwargs: Any) -> None:
        if kwargs["finder_id"] == "aegean":
            raise RuntimeError("fixture container failure")
        execute(**kwargs)

    monkeypatch.setitem(run.__globals__, "_run_container", fail_aegean)
    with pytest.raises(RuntimeError, match="container failure"):
        run(**arguments)
    assert not (
        arguments["output"] / "reference-campaign/campaign.json"
    ).exists()
    monkeypatch.setitem(run.__globals__, "_run_container", execute)
    run(**arguments, resume=True)
    assert calls == ["download", "released-pybdsf", "aegean"]


def test_resume_rejects_changed_artifact(
    setup: dict[str, Any],
    fake_execution: tuple[dict[str, Any], list[str]],
) -> None:
    arguments, _calls = fake_execution
    run = setup["prepare_comparison"]
    run(**arguments)
    artifact = next(
        arguments["output"].glob(
            "reference-campaign/results/**/catalogue.json"
        )
    )
    artifact.write_text("changed")
    with pytest.raises(ValueError, match="artifact"):
        run(**arguments, resume=True)


def test_existing_output_is_not_overwritten(
    setup: dict[str, Any],
    fake_execution: tuple[dict[str, Any], list[str]],
) -> None:
    arguments, calls = fake_execution
    arguments["output"].mkdir()
    with pytest.raises(FileExistsError):
        setup["prepare_comparison"](**arguments)
    assert calls == []


def test_dry_run_with_image_builds_does_not_build(
    tmp_path: Path,
    setup: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("dry-run must not build images")

    run = setup["prepare_comparison"]
    monkeypatch.setitem(run.__globals__, "_build_images", forbidden)
    plan = run(
        repository_root=_ROOT,
        output=tmp_path / "comparison",
        datasets=(),
        images={"released-pybdsf": "pybdsf", "aegean": "aegean"},
        dry_run=True,
        build_images=True,
    )
    assert plan["build_images"] is True
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "change",
    ["cores", "input", "images", "missing-artifact", "escape-artifact"],
)
def test_resume_rejects_incompatible_or_damaged_state(
    setup: dict[str, Any],
    fake_execution: tuple[dict[str, Any], list[str]],
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    arguments, calls = fake_execution
    run = setup["prepare_comparison"]
    run(**arguments)
    if change == "cores":
        arguments["ncores"] = 3
    elif change == "input":
        image = (
            arguments["repository_root"]
            / "benchmark-results/notebook-data/field.fits"
        )
        image.write_bytes(b"changed")
    elif change == "images":

        def inspect(*_args: Any) -> dict[str, str]:
            return {"released-pybdsf": "new-image", "aegean": "new-image"}

        monkeypatch.setitem(run.__globals__, "_inspect_images", inspect)
    else:
        path = next(
            arguments["output"].glob(
                "reference-campaign/results/**/result.json"
            )
        )
        result = json.loads(path.read_text())
        if change == "missing-artifact":
            result["artifacts"].pop("comparison-catalogue-json")
        else:
            result["artifacts"]["comparison-catalogue-json"]["path"] = (
                "/outside.json"
            )
        path.write_text(json.dumps(result))
    with pytest.raises(ValueError, match=r"changed|artifact"):
        run(**arguments, resume=True)
    assert calls == ["download", "released-pybdsf", "aegean"]


@pytest.mark.parametrize("valid", [True, False])
def test_local_images_are_inspected_without_pulling(
    setup: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    valid: bool,
) -> None:
    calls: list[list[str]] = []

    def command(args: list[str], **_kwargs: Any) -> Any:
        calls.append(args)
        return SimpleNamespace(
            stdout=json.dumps([{"Id": "sha256:" + "a" * 64}] if valid else [])
        )

    monkeypatch.setattr(setup["subprocess"], "run", command)
    images = {"released-pybdsf": "pybdsf", "aegean": "aegean"}
    if valid:
        assert len(setup["_inspect_images"]("podman", images)) == 2
    else:
        with pytest.raises(ValueError, match="immutable"):
            setup["_inspect_images"]("podman", images)
    assert all(args[:3] == ["podman", "image", "inspect"] for args in calls)


@pytest.mark.parametrize("core", [None, [2, 7, 3, 9]])
def test_container_command_keeps_inputs_read_only_and_prevents_pulls(
    tmp_path: Path,
    setup: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    core: list[int] | None,
) -> None:
    calls: list[list[str]] = []

    def command(args: list[str], **_kwargs: Any) -> None:
        calls.append(args)

    monkeypatch.setattr(setup["subprocess"], "run", command)
    setup["_run_container"](
        repository_root=tmp_path,
        comparison_root=tmp_path / "comparison",
        engine="podman",
        image="sha256:" + "a" * 64,
        input_path=tmp_path / "input.fits",
        output=tmp_path / "comparison/result",
        case_id="case",
        finder_id="aegean",
        ncores=2,
        core=core,
    )
    args = calls[0]
    assert "--network=none" in args and "--pull=never" in args
    assert f"{tmp_path}:/repository:ro" in args
    assert f"{tmp_path / 'comparison'}:/comparison:rw" in args
    assert args[args.index("--cpus") + 1] == "2"
    assert "OPENBLAS_NUM_THREADS=1" in args
    assert args[args.index("--input") + 1] == "/repository/input.fits"

    if core is not None:
        assert args[-5:] == ["--core", "2", "7", "3", "9"]
    else:
        assert "--core" not in args


@pytest.mark.parametrize("corrupt", [False, True])
def test_build_reuses_existing_recipes_and_checks_package_transfers(
    setup: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    corrupt: bool,
) -> None:
    filenames = ["bdsf-1.14.1.tar.gz", "aegeantools-2.3.5-py3-none-any.whl"]
    payload = b"package fixture"

    def metadata(_url: str, **_kwargs: Any) -> io.BytesIO:
        return io.BytesIO(
            json.dumps(
                {
                    "urls": [
                        {
                            "filename": name,
                            "url": "https://example.invalid/" + name,
                            "digests": {
                                "sha256": hashlib.sha256(payload).hexdigest()
                            },
                        }
                        for name in filenames
                    ]
                }
            ).encode()
        )

    def download(_url: str, path: Path) -> None:
        path.write_bytes(b"corrupt" if corrupt else payload)

    calls: list[list[str]] = []

    def command(args: list[str], **_kwargs: Any) -> None:
        context = Path(args[-1])
        assert all((context / name).is_file() for name in filenames)
        assert (context / "requirements-pybdsf-runtime.txt").is_file()
        calls.append(args)

    monkeypatch.setattr(setup["urllib"].request, "urlopen", metadata)
    monkeypatch.setitem(
        setup["_build_images"].__globals__, "_download", download
    )
    monkeypatch.setattr(setup["subprocess"], "run", command)
    images = {"released-pybdsf": "pybdsf", "aegean": "aegean"}
    if corrupt:
        with pytest.raises(ValueError, match="checksum"):
            setup["_build_images"]("podman", images)
        assert not calls
    else:
        setup["_build_images"]("podman", images)
        assert len(calls) == 2
        assert calls[0][calls[0].index("--target") + 1] == "released"
        assert "--target" not in calls[1]
        assert all(not Path(args[-1]).exists() for args in calls)


@pytest.mark.parametrize(
    "invalid",
    ["cores", "dataset", "images", "output", "resume", "resume-build"],
)
def test_invalid_requests_stop_before_downloads(
    setup: dict[str, Any],
    fake_execution: tuple[dict[str, Any], list[str]],
    invalid: str,
) -> None:
    arguments, calls = fake_execution
    if invalid == "cores":
        arguments["ncores"] = 0
    elif invalid == "dataset":
        arguments["datasets"] = ("unlisted",)
    elif invalid == "images":
        arguments["images"] = {}
    elif invalid == "output":
        arguments["output"] = arguments["repository_root"]
    elif invalid == "resume":
        arguments["resume"] = True
    else:
        arguments["output"].mkdir()
        (arguments["output"] / "request.json").write_text("{}")
        arguments.update(resume=True, build_images=True)
    with pytest.raises((ValueError, FileNotFoundError)):
        setup["prepare_comparison"](**arguments)
    assert calls == []


def test_requested_builds_precede_downloads(
    setup: dict[str, Any],
    fake_execution: tuple[dict[str, Any], list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arguments, calls = fake_execution

    def build(*_args: Any) -> None:
        calls.append("build")

    monkeypatch.setitem(
        setup["prepare_comparison"].__globals__, "_build_images", build
    )
    setup["prepare_comparison"](**arguments, build_images=True)
    assert calls == ["build", "download", "released-pybdsf", "aegean"]


def test_cli_dry_run_and_download_helper_use_existing_inventory(
    tmp_path: Path,
    setup: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            str(_SCRIPT),
            "--dry-run",
            "--build-images",
            "--dataset",
            "lotss-dr2-m51-20arcmin",
        ],
    )
    runpy.run_path(str(_SCRIPT), run_name="__main__")
    result = json.loads(capsys.readouterr().out)
    assert result["datasets"] == ["lotss-dr2-m51-20arcmin"]
    payload = b"SIMPLE  =" + b" " * (2880 - 9)

    class Response(io.BytesIO):
        headers: ClassVar[dict[str, str]] = {}

    def response(_url: str, **_kwargs: Any) -> Response:
        return Response(payload)

    monkeypatch.setattr(setup["urllib"].request, "urlopen", response)
    path = tmp_path / "image.fits"
    setup["_download"]("https://example.invalid/image", path)
    assert path.read_bytes() == payload


@pytest.mark.parametrize("change", ["status", "missing", "same-size-hash"])
def test_result_validation_rejects_failure_and_broken_files(
    setup: dict[str, Any],
    fake_execution: tuple[dict[str, Any], list[str]],
    change: str,
) -> None:
    arguments, _calls = fake_execution
    setup["prepare_comparison"](**arguments)
    path = next(
        arguments["output"].glob("reference-campaign/results/**/result.json")
    )
    if change == "status":
        result = json.loads(path.read_text())
        result["status"] = "failure"
        path.write_text(json.dumps(result))
    elif change == "missing":
        (path.parent / "catalogue.json").unlink()
    else:
        (path.parent / "catalogue.json").write_text("{}")
    with pytest.raises(ValueError, match=r"identity|artifact"):
        setup["prepare_comparison"](**arguments, resume=True)


def test_source_change_during_execution_cannot_seal_campaign(
    setup: dict[str, Any],
    fake_execution: tuple[dict[str, Any], list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arguments, _calls = fake_execution
    identities = iter(("before", "after"))
    monkeypatch.setitem(
        setup["prepare_comparison"].__globals__,
        "_program_identity",
        lambda: next(identities),
    )
    with pytest.raises(RuntimeError, match="programs changed"):
        setup["prepare_comparison"](**arguments)
    assert not (
        arguments["output"] / "reference-campaign/campaign.json"
    ).exists()


def test_all_thirteen_cases_share_six_downloads_and_preserve_sdc1_cores(
    setup: dict[str, Any],
    fake_execution: tuple[dict[str, Any], list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arguments, calls = fake_execution
    run = setup["prepare_comparison"]
    original = runpy.run_path(str(_SCRIPT))
    cases = original["_comparison_cases"]()
    for name, case in cases.items():
        if name.startswith("sdc1-"):
            case.update(bounds_xy=[3, 8, 2, 7], halo_pixels=2)
    monkeypatch.setitem(run.__globals__, "_comparison_cases", lambda: cases)
    monkeypatch.setitem(
        run.__globals__, "_download_inventory", original["_download_inventory"]
    )
    header = fits.Header(
        {
            "CTYPE1": "RA---TAN",
            "CTYPE2": "DEC--TAN",
            "CRPIX1": 8.0,
            "CRPIX2": 7.0,
            "CRVAL1": 180.0,
            "CRVAL2": 45.0,
            "CDELT1": -0.001,
            "CDELT2": 0.001,
            "BMAJ": 0.002,
            "BMIN": 0.002,
            "BUNIT": "Jy/beam",
        }
    )
    pixels = np.arange(14 * 16, dtype=float).reshape(1, 1, 14, 16)

    def download(_url: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        fits.PrimaryHDU(pixels, header).writeto(destination)
        calls.append("download")

    monkeypatch.setitem(run.__globals__, "_download", download)
    arguments["datasets"] = ()
    run(**arguments)
    assert calls.count("download") == 6
    assert calls.count("released-pybdsf") == calls.count("aegean") == 13
    inputs = arguments["output"] / "input-campaign"
    for name in cases:
        record = json.loads(
            (inputs / "inputs" / name / "input.json").read_text()
        )
        image = arguments["repository_root"] / record["input_path"]
        if name.startswith("sdc1-"):
            assert record["local_core_yx_half_open"] == [2, 7, 2, 7]
            np.testing.assert_array_equal(
                cast(Any, fits.getdata(image)), pixels[:, :, 0:9, 1:10]
            )
            assert fits.getheader(image)["CRPIX1"] == 7.0
        elif name.startswith("lotss-"):
            assert cast(Any, fits.getdata(image)).shape == (14, 16)
            assert fits.getheader(image)["RESTFRQ"] == 144_000_000.0
        else:
            assert image.parent.name == "notebook-data"
    before = list(calls)
    run(**arguments, resume=True)
    assert calls == before


def _lotss_header(**frequency: float) -> fits.Header:
    """Return one LoTSS-like cutout header with optional frequency keys."""
    header = fits.Header(
        {
            "CTYPE1": "RA---TAN",
            "CTYPE2": "DEC--TAN",
            "CRPIX1": 3.0,
            "CRPIX2": 3.0,
            "CRVAL1": 202.47,
            "CRVAL2": 47.19,
            "CDELT1": -0.0004,
            "CDELT2": 0.0004,
            "BMAJ": 0.0017,
            "BMIN": 0.0017,
            "BPA": 90.0,
            "BUNIT": "JY/BEAM",
        }
    )
    header.update(frequency)
    return header


@pytest.mark.parametrize(
    ("frequency", "expected_hz"),
    (
        ({}, 144_000_000.0),
        ({"RESTFRQ": 143_650_000.0}, 143_650_000.0),
        ({"RESTFREQ": 150_000_000.0}, 150_000_000.0),
        ({"RESTFRQ": 0.0}, 144_000_000.0),
    ),
    ids=("missing", "wcs-spelling", "pybdsf-spelling", "invalid"),
)
def test_lotss_normalisation_writes_both_frequency_spellings(
    tmp_path: Path,
    setup: dict[str, Any],
    frequency: dict[str, float],
    expected_hz: float,
) -> None:
    """Released PyBDSF reads RESTFREQ even when a cutout has only RESTFRQ."""
    download = tmp_path / "download.fits"
    destination = tmp_path / "input.fits"
    pixels = np.arange(25, dtype=float).reshape(5, 5)
    fits.PrimaryHDU(pixels, _lotss_header(**frequency)).writeto(download)

    setup["_normalise_lotss_image"](download, destination)

    header = cast(fits.Header, fits.getheader(destination))
    assert header["RESTFRQ"] == expected_hz
    assert header["RESTFREQ"] == expected_hz
    np.testing.assert_array_equal(cast(Any, fits.getdata(destination)), pixels)
