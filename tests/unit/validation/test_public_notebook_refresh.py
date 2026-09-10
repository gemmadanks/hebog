"""Tests for the diagnostic public-notebook refresh runner."""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from hebog.validation.external_runners import canonical_sha256

_ROOT = Path(__file__).parents[3]
_REFRESH = runpy.run_path(
    str(_ROOT / "scripts/benchmark/refresh_public_notebook_hebog.py")
)
_PUBLIC_RUNNER = runpy.run_path(
    str(_ROOT / "scripts/benchmark/run_phase5_public_finder_hebog.py")
)


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_default_notebook_runner_selects_the_frozen_catalogue_repair() -> None:
    """The diagnostic entry point must select the intended repair review."""
    expected = (
        _ROOT
        / "config/contracts"
        / "phase-5-noiseless-filter-repair-identity-review.json"
    )
    assert _PUBLIC_RUNNER["_PUBLIC_IDENTITY"] == expected


@pytest.mark.parametrize(
    "mismatch", (None, "source", "composition-name", "composition-sha256")
)
def test_selected_review_still_rejects_scientific_identity_drift(
    mismatch: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use the real review with synthetic hashes, not live development files.

    Historical bytes are verified separately by the repair identity tests;
    a real no-write preflight checks live science before a notebook refresh.
    """
    review = json.loads(
        (
            _ROOT
            / "config/contracts"
            / "phase-5-noiseless-filter-repair-identity-review.json"
        ).read_bytes()
    )
    guard = _PUBLIC_RUNNER["public_hebog_configuration_sha256"]

    def source_sha256(_root: Path) -> str:
        if mismatch == "source":
            return "0" * 64
        return str(review["algorithm_candidate"]["source_tree_sha256"])

    def composition_sha256() -> str:
        if mismatch == "composition-sha256":
            return "0" * 64
        return str(review["scientific_composition_sha256"])

    monkeypatch.setitem(guard.__globals__, "source_tree_sha256", source_sha256)
    monkeypatch.setitem(
        guard.__globals__,
        "public_api",
        SimpleNamespace(
            _COMPOSITION_NAME=(
                "different-composition"
                if mismatch == "composition-name"
                else review["scientific_composition"]
            ),
            _scientific_composition_sha256=composition_sha256,
        ),
    )
    if mismatch is None:
        assert guard() == canonical_sha256(review["configuration"])
    else:
        with pytest.raises(
            ValueError, match="final public-interface identity changed"
        ):
            guard()


def test_preflight_uses_the_public_runners_exact_configuration(
    tmp_path: Path,
    capsys: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A refresh must not reconstruct an obsolete candidate identity."""
    input_campaign = tmp_path / "input.json"
    reference_campaign = tmp_path / "reference.json"
    runner_path = (
        tmp_path / "scripts/benchmark/run_phase5_public_finder_hebog.py"
    )
    runner_path.parent.mkdir(parents=True)
    expected = "e" * 64
    runner_path.write_text(
        "def public_hebog_configuration_sha256():\n"
        f"    return {expected!r}\n"
        "def run_public_hebog(**kwargs):\n"
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

    monkeypatch.setitem(run.__globals__, "_load_public_runner", public_runner)
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
