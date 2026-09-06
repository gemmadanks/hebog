"""Regression tests for compact-sentinel empty-result compilation."""

# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false

from __future__ import annotations

import argparse
import json
import runpy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from astropy.io import fits

_ROOT = Path(__file__).parents[3]
_RUNNER = (
    _ROOT / "scripts/benchmark/"
    "run_phase5_compact_held_out_sentinel_empty_result_repair.py"
)
_FREEZER = (
    _ROOT / "scripts/validation/"
    "freeze_phase5_compact_sentinel_empty_result_repair.py"
)


def _header() -> fits.Header:
    """Return a small valid celestial WCS."""
    header = fits.Header()
    header["CTYPE1"] = "RA---SIN"
    header["CTYPE2"] = "DEC--SIN"
    header["CRPIX1"] = 1.0
    header["CRPIX2"] = 1.0
    header["CRVAL1"] = 10.0
    header["CRVAL2"] = -30.0
    header["CDELT1"] = -1.0 / 3600.0
    header["CDELT2"] = 1.0 / 3600.0
    return header


def _empty_result() -> SimpleNamespace:
    """Return the public facade's canonical empty result counts."""
    return SimpleNamespace(
        source_count=0,
        gaussian_component_count=0,
        island_count=0,
    )


def test_runner_compiles_valid_public_empty_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unavailable-RMS empty science is evidence, not an operational error."""
    program: dict[str, Any] = runpy.run_path(str(_RUNNER))
    parent = program["_parent"]
    captured_arguments: dict[str, object] = {}

    class Capture:
        def __enter__(self) -> list[object]:
            return [
                SimpleNamespace(
                    terminal=None,
                    rms=np.full((2, 3), np.nan, dtype=np.float64),
                )
            ]

        def __exit__(self, *_arguments: object) -> None:
            return None

    monkeypatch.setattr(parent, "_captured_science", Capture)

    def find_empty(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return _empty_result()

    monkeypatch.setattr(parent.hebog, "find_sources", find_empty)

    def compile_summary(**arguments: object) -> dict[str, object]:
        captured_arguments.update(arguments)
        return {"status": "compiled"}

    monkeypatch.setattr(parent, "compile_finder_summary", compile_summary)
    input_path = tmp_path / "input.fits"
    fits.PrimaryHDU(data=np.ones((2, 3)), header=_header()).writeto(input_path)

    result = program["_run_hebog_empty_safe"](
        dataset=SimpleNamespace(identifier="fixture"),
        recipe=SimpleNamespace(seed=1, shape_yx=(2, 3)),
        input_path=input_path,
        output=tmp_path / "output",
        executor=object(),
        review=object(),
    )

    assert result == {"status": "compiled"}
    assert captured_arguments["catalogue"] == ()
    np.testing.assert_array_equal(
        captured_arguments["label_plane"],
        np.zeros((2, 3), dtype=np.int32),
    )


@pytest.mark.parametrize(
    ("result", "rms", "message"),
    (
        (
            SimpleNamespace(
                source_count=0,
                gaussian_component_count=1,
                island_count=1,
            ),
            np.full((2, 3), np.nan),
            "public counts are not empty",
        ),
        (
            _empty_result(),
            np.ones((2, 3)),
            "RMS remains scientifically usable",
        ),
        (
            _empty_result(),
            np.full((3, 2), np.nan),
            "RMS shape changed",
        ),
    ),
)
def test_runner_rejects_inconsistent_missing_terminal_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    result: SimpleNamespace,
    rms: np.ndarray[Any, Any],
    message: str,
) -> None:
    """Only the documented empty public outcome may omit terminal data."""
    program: dict[str, Any] = runpy.run_path(str(_RUNNER))
    parent = program["_parent"]

    class Capture:
        def __enter__(self) -> list[object]:
            return [SimpleNamespace(terminal=None, rms=rms)]

        def __exit__(self, *_arguments: object) -> None:
            return None

    monkeypatch.setattr(parent, "_captured_science", Capture)

    def find_inconsistent(
        *_args: object, **_kwargs: object
    ) -> SimpleNamespace:
        return result

    monkeypatch.setattr(parent.hebog, "find_sources", find_inconsistent)
    input_path = tmp_path / "input.fits"
    fits.PrimaryHDU(data=np.ones((2, 3)), header=_header()).writeto(input_path)

    with pytest.raises(ValueError, match=message):
        program["_run_hebog_empty_safe"](
            dataset=SimpleNamespace(identifier="fixture"),
            recipe=SimpleNamespace(seed=1, shape_yx=(2, 3)),
            input_path=input_path,
            output=tmp_path / "output",
            executor=object(),
            review=object(),
        )


def test_runner_preserves_nonempty_stable_ownership_linkage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The empty seam must not change nonempty component compilation."""
    program: dict[str, Any] = runpy.run_path(str(_RUNNER))
    parent = program["_parent"]
    prior = program["_prior"]
    labels = np.asarray(((1, 0), (0, 0)), dtype=np.int32)
    terminal = SimpleNamespace(
        component_catalogue=("stable-row",),
        measurement_component_labels=labels,
        source_association=SimpleNamespace(components=("record",)),
    )
    captured_arguments: dict[str, object] = {}

    class Capture:
        def __enter__(self) -> list[object]:
            return [SimpleNamespace(terminal=terminal, rms=np.ones((2, 2)))]

        def __exit__(self, *_arguments: object) -> None:
            return None

    monkeypatch.setattr(parent, "_captured_science", Capture)

    def find_nonempty(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            source_count=1,
            gaussian_component_count=1,
            island_count=1,
        )

    monkeypatch.setattr(parent.hebog, "find_sources", find_nonempty)

    def link_stable(*_args: object) -> tuple[str, ...]:
        return ("linked-row",)

    monkeypatch.setattr(
        prior._repair, "link_stable_component_ownership", link_stable
    )

    def compile_summary(**arguments: object) -> dict[str, object]:
        captured_arguments.update(arguments)
        return {"status": "compiled"}

    monkeypatch.setattr(parent, "compile_finder_summary", compile_summary)
    input_path = tmp_path / "input.fits"
    fits.PrimaryHDU(data=np.ones((2, 2)), header=_header()).writeto(input_path)

    program["_run_hebog_empty_safe"](
        dataset=SimpleNamespace(identifier="fixture"),
        recipe=SimpleNamespace(seed=1, shape_yx=(2, 2)),
        input_path=input_path,
        output=tmp_path / "output",
        executor=object(),
        review=object(),
    )

    assert captured_arguments["catalogue"] == ("linked-row",)
    assert captured_arguments["label_plane"] is labels


def test_empty_repair_temporarily_replaces_both_execution_seams() -> None:
    """Serial pairs and Dask checks must share the complete repair."""
    program: dict[str, Any] = runpy.run_path(str(_RUNNER))
    parent = program["_parent"]
    original_hebog = parent._run_hebog
    original_pair = parent._pair_worker

    with program["_configured_parent"]():
        assert parent._run_hebog is program["_run_hebog_empty_safe"]
        assert parent._pair_worker is program["_pair_worker_empty_safe"]

    assert parent._run_hebog is original_hebog
    assert parent._pair_worker is original_pair


def test_empty_repair_binds_preserved_second_failure() -> None:
    """The next retry cannot detach from either failed attempt."""
    program: dict[str, Any] = runpy.run_path(str(_RUNNER))

    program["_require_failed_lineage"]()


def test_empty_repair_identity_preserves_science_and_population() -> None:
    """The replacement identity changes only evaluator and run ownership."""
    freezer: dict[str, Any] = runpy.run_path(str(_FREEZER))
    implementation, identity = freezer["build_records"](_ROOT)

    assert identity["status"] == "frozen-non-executable"
    assert set(identity["authorization"].values()) == {False}
    assert identity["candidate"]["source_tree_sha256"] == (
        "8da21e86afc5035da0704724a9d29104ea8b0e4d55fa4a98f0c5f3efca9a75a5"
    )
    assert identity["execution_contract"]["total_finder_executions"] == 348
    assert identity["population"]["image_count"] == 168
    assert identity["expected_execution"]["output"].endswith(
        "compact-held-out-sentinel-empty-result-repair.json"
    )
    assert implementation["repair"] == {
        "empty_label_plane_only_when_public_counts_are_zero": True,
        "empty_label_plane_only_when_rms_is_unavailable": True,
        "stable_component_ownership_linkage_preserved": True,
    }


def test_empty_repair_freezer_refuses_existing_target(tmp_path: Path) -> None:
    """A prior replacement identity cannot be overwritten."""
    freezer: dict[str, Any] = runpy.run_path(str(_FREEZER))
    identity = tmp_path / freezer["_IDENTITY"]
    identity.parent.mkdir(parents=True)
    identity.write_text("existing\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        freezer["freeze_records"](
            argparse.Namespace(repository_root=_ROOT, output_root=tmp_path)
        )

    assert identity.read_text(encoding="utf-8") == "existing\n"
    assert not (tmp_path / freezer["_IMPLEMENTATION"]).exists()


def test_empty_repair_review_records_exact_user_authority() -> None:
    """Retry permission must not broaden into a science change."""
    review = json.loads(
        (
            _ROOT / "config/contracts/"
            "phase-5-compact-held-out-sentinel-empty-result-repair-"
            "pre-review.json"
        ).read_text(encoding="utf-8")
    )

    assert review["authorization"]["evaluator_repair_authorized"] is True
    assert review["authorization"]["all_retries_authorized"] is True
    assert review["authorization"]["source_finding_change_authorized"] is False
    assert review["scientific_invariants"]["image_count"] == 168
