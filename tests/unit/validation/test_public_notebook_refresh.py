"""Tests for the diagnostic public-notebook refresh runner."""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).parents[3]
_REFRESH = runpy.run_path(
    str(_ROOT / "scripts/benchmark/refresh_public_notebook_hebog.py")
)


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _input_record(
    tmp_path: Path, **overrides: object
) -> tuple[Path, dict[str, object]]:
    """Write one repository-relative input record and its image bytes."""
    image = tmp_path / "images/input.fits"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")
    record: dict[str, object] = {
        "case_id": "case",
        "input_location": "repository",
        "input_path": "images/input.fits",
        "input_sha256": _REFRESH["_sha256"](image),
        "local_core_yx_half_open": [1, 3, 2, 5],
        **overrides,
    }
    campaign = tmp_path / "input-campaign"
    (campaign / "inputs/case").mkdir(parents=True)
    _write_json(campaign / "inputs/case/input.json", record)
    return campaign, record


def test_input_resolver_returns_verified_image_and_core(
    tmp_path: Path,
) -> None:
    """Prepared cutouts keep their local half-open output core."""
    campaign, record = _input_record(tmp_path)

    path, core, loaded = _REFRESH["_resolve_input"](tmp_path, campaign, "case")

    assert path == tmp_path / "images/input.fits"
    assert (core.y_start, core.y_stop, core.x_start, core.x_stop) == (
        1,
        3,
        2,
        5,
    )
    assert loaded == record


@pytest.mark.parametrize(
    ("overrides", "message"),
    (
        ({"case_id": "other"}, "identity changed"),
        ({"input_path": "../input.fits"}, "unsafe input path"),
        ({"input_location": "elsewhere"}, "unsupported input location"),
        ({"input_sha256": "0" * 64}, "checksum changed"),
        ({"local_core_yx_half_open": [1, 2]}, "invalid core bounds"),
    ),
)
def test_input_resolver_rejects_changed_or_unsafe_records(
    tmp_path: Path, overrides: dict[str, object], message: str
) -> None:
    """A refresh cannot silently run Hebog on a different or unsafe input."""
    campaign, _ = _input_record(tmp_path, **overrides)

    with pytest.raises(ValueError, match=message):
        _REFRESH["_resolve_input"](tmp_path, campaign, "case")


def test_input_resolver_requires_the_image(tmp_path: Path) -> None:
    """A missing prepared image stops before any finder runs."""
    campaign, _ = _input_record(tmp_path)
    (tmp_path / "images/input.fits").unlink()

    with pytest.raises(FileNotFoundError, match="missing input"):
        _REFRESH["_resolve_input"](tmp_path, campaign, "case")


def test_preflight_uses_the_hebog_runners_configuration(
    tmp_path: Path,
    capsys: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A refresh must not reconstruct an obsolete candidate identity."""
    input_campaign = tmp_path / "input.json"
    reference_campaign = tmp_path / "reference.json"
    runner_path = tmp_path / "scripts/benchmark/run_notebook_hebog.py"
    runner_path.parent.mkdir(parents=True)
    expected = "e" * 64
    runner_path.write_text(
        "def hebog_configuration_sha256():\n"
        f"    return {expected!r}\n"
        "def run_notebook_hebog(**kwargs):\n"
        "    raise AssertionError('preflight must not execute a finder')\n",
        encoding="utf-8",
    )

    def git_identity(_root: Path) -> tuple[str, bool]:
        return "a" * 40, False

    monkeypatch.setitem(
        _REFRESH["run_refresh"].__globals__, "_git_identity", git_identity
    )
    _write_json(
        input_campaign,
        {
            "scientific_claims_authorized": False,
            "results": [{"case_id": "case", "status": "success"}],
        },
    )
    _write_json(
        reference_campaign,
        {
            "scientific_claims_authorized": False,
            "results": [
                {"case_id": "case", "status": "success"},
                {"case_id": "case", "status": "success"},
            ],
        },
    )

    _REFRESH["run_refresh"](
        repository_root=tmp_path,
        input_campaign_path=input_campaign,
        reference_campaign_path=reference_campaign,
        history_root=tmp_path / "history",
        label="test",
        resume=False,
        preflight_only=True,
    )

    preflight = json.loads(capsys.readouterr().out)
    assert preflight["configuration_sha256"] == expected
    assert not (tmp_path / "history").exists()


def test_preflight_never_republishes_an_existing_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    """Read-only admission cannot relabel or repoint a sealed refresh."""
    run = _REFRESH["run_refresh"]
    input_path = tmp_path / "input.json"
    reference_path = tmp_path / "reference.json"
    _write_json(
        input_path,
        {
            "scientific_claims_authorized": False,
            "results": [{"case_id": "case"}],
        },
    )
    _write_json(
        reference_path,
        {
            "scientific_claims_authorized": False,
            "results": [{"status": "success"}, {"status": "success"}],
        },
    )

    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("read-only preflight must not publish or execute")

    def public_runner(_root: Path) -> tuple[str, Any]:
        return "c" * 64, forbidden

    def source_sha256(_root: Path) -> str:
        return "b" * 64

    def file_sha256(_path: Path) -> str:
        return "d" * 64

    def git_identity(_root: Path) -> tuple[str, bool]:
        return "a" * 40, False

    monkeypatch.setitem(run.__globals__, "_load_hebog_runner", public_runner)
    monkeypatch.setitem(run.__globals__, "source_tree_sha256", source_sha256)
    monkeypatch.setitem(run.__globals__, "_sha256", file_sha256)
    monkeypatch.setitem(run.__globals__, "_git_identity", git_identity)
    monkeypatch.setitem(run.__globals__, "_publish_history", forbidden)
    history = tmp_path / "history"
    output = history / "aaaaaaa-bbbbbbbbbbbb-dddddddd"
    output.mkdir(parents=True)
    _write_json(output / "campaign.json", {"sealed": True})
    _write_json(history / "index.json", {"label": "original"})
    (history / "latest").symlink_to(output.name)
    before = {
        path.relative_to(history): path.read_bytes()
        for path in history.rglob("*.json")
    }
    run(
        repository_root=tmp_path,
        input_campaign_path=input_path,
        reference_campaign_path=reference_path,
        history_root=history,
        label="must not replace the original",
        resume=False,
        preflight_only=True,
    )
    assert json.loads(capsys.readouterr().out)["status"] == "preflight-passed"
    assert before == {
        path.relative_to(history): path.read_bytes()
        for path in history.rglob("*.json")
    }
    assert (history / "latest").readlink() == Path(output.name)
