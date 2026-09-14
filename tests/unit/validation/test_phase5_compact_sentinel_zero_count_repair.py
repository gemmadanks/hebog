"""Regression tests for valid zero-count sentinel compilation."""

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
    "run_phase5_compact_held_out_sentinel_zero_count_repair.py"
)
_FREEZER = (
    _ROOT / "scripts/validation/"
    "freeze_phase5_compact_sentinel_zero_count_repair.py"
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


def test_runner_compiles_zero_count_result_with_usable_rms(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A source-free public result remains scientific evidence."""
    program: dict[str, Any] = runpy.run_path(str(_RUNNER))
    parent = program["_parent"]
    captured_arguments: dict[str, object] = {}

    class Capture:
        def __enter__(self) -> list[object]:
            return [
                SimpleNamespace(
                    terminal=None,
                    rms=np.ones((2, 3), dtype=np.float64),
                )
            ]

        def __exit__(self, *_arguments: object) -> None:
            return None

    def find_empty(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return _empty_result()

    def compile_summary(**arguments: object) -> dict[str, object]:
        captured_arguments.update(arguments)
        return {"status": "compiled"}

    monkeypatch.setattr(parent, "_captured_science", Capture)
    monkeypatch.setattr(parent.hebog, "find_sources", find_empty)
    monkeypatch.setattr(parent, "compile_finder_summary", compile_summary)
    input_path = tmp_path / "input.fits"
    fits.PrimaryHDU(data=np.ones((2, 3)), header=_header()).writeto(input_path)

    result = program["_run_hebog_zero_count_safe"](
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
            np.ones((2, 3)),
            "public counts are not empty",
        ),
        (
            _empty_result(),
            np.ones((3, 2)),
            "RMS shape changed",
        ),
    ),
)
def test_runner_rejects_inconsistent_zero_count_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    result: SimpleNamespace,
    rms: np.ndarray[Any, Any],
    message: str,
) -> None:
    """Missing terminals still require exact public and shape agreement."""
    program: dict[str, Any] = runpy.run_path(str(_RUNNER))
    parent = program["_parent"]

    class Capture:
        def __enter__(self) -> list[object]:
            return [SimpleNamespace(terminal=None, rms=rms)]

        def __exit__(self, *_arguments: object) -> None:
            return None

    def find_result(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return result

    monkeypatch.setattr(parent, "_captured_science", Capture)
    monkeypatch.setattr(parent.hebog, "find_sources", find_result)
    input_path = tmp_path / "input.fits"
    fits.PrimaryHDU(data=np.ones((2, 3)), header=_header()).writeto(input_path)

    with pytest.raises(ValueError, match=message):
        program["_run_hebog_zero_count_safe"](
            dataset=SimpleNamespace(identifier="fixture"),
            recipe=SimpleNamespace(seed=1, shape_yx=(2, 3)),
            input_path=input_path,
            output=tmp_path / "output",
            executor=object(),
            review=object(),
        )


def test_zero_count_repair_temporarily_replaces_both_seams() -> None:
    """Serial pairs and Dask checks must share the final adapter."""
    program: dict[str, Any] = runpy.run_path(str(_RUNNER))
    parent = program["_parent"]
    original_hebog = parent._run_hebog
    original_pair = parent._pair_worker

    with program["_configured_parent"]():
        assert parent._run_hebog is program["_run_hebog_zero_count_safe"]
        assert parent._pair_worker is program["_pair_worker_zero_count_safe"]

    assert parent._run_hebog is original_hebog
    assert parent._pair_worker is original_pair


@pytest.mark.integration
@pytest.mark.requires_data
def test_zero_count_repair_binds_all_preserved_failures() -> None:
    """The final retry cannot detach from any failed attempt."""
    program: dict[str, Any] = runpy.run_path(str(_RUNNER))

    program["_require_failed_lineage"]()


@pytest.mark.integration
@pytest.mark.requires_data
def test_zero_count_identity_preserves_science_and_population() -> None:
    """Only the evaluator adapter and write-once paths may change."""
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
        "compact-held-out-sentinel-zero-count-repair.json"
    )
    assert implementation["repair"] == {
        "empty_label_plane_only_when_public_counts_are_zero": True,
        "rms_shape_must_match_input": True,
        "rms_usability_does_not_define_source_population": True,
        "stable_component_ownership_linkage_preserved": True,
    }


def test_zero_count_freezer_refuses_existing_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A prior replacement identity cannot be overwritten."""
    freezer: dict[str, Any] = runpy.run_path(str(_FREEZER))

    def build_fixture_records(_root: Path) -> tuple[dict[str, str], ...]:
        return ({"fixture": "implementation"}, {"fixture": "identity"})

    monkeypatch.setitem(
        freezer["freeze_records"].__globals__,
        "build_records",
        build_fixture_records,
    )
    identity = tmp_path / freezer["_IDENTITY"]
    identity.parent.mkdir(parents=True)
    identity.write_text("existing\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        freezer["freeze_records"](
            argparse.Namespace(repository_root=_ROOT, output_root=tmp_path)
        )

    assert identity.read_text(encoding="utf-8") == "existing\n"
    assert not (tmp_path / freezer["_IMPLEMENTATION"]).exists()


def test_zero_count_review_records_exact_user_authority() -> None:
    """Retry authority must not broaden into source-finding change."""
    review = json.loads(
        (
            _ROOT / "config/contracts/"
            "phase-5-compact-held-out-sentinel-zero-count-repair-"
            "pre-review.json"
        ).read_text(encoding="utf-8")
    )

    assert review["authorization"]["evaluator_repair_authorized"] is True
    assert review["authorization"]["all_retries_authorized"] is True
    assert review["authorization"]["source_finding_change_authorized"] is False
    assert review["scientific_invariants"]["image_count"] == 168
