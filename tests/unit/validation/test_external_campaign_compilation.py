# pyright: reportPrivateUsage=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownLambdaType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Tests for result-neutral external-campaign compiler acceleration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import FunctionType, SimpleNamespace

import numpy as np
import pytest
from astropy.io import fits

from hebog.validation.external_campaign_compilation import (
    SharedContinuumImageCompiler,
    install_continuum_accelerators,
    linear_native_support_objects,
)
from hebog.validation.external_successor_compiler import native_support_objects


@pytest.mark.parametrize(
    "labels",
    (
        np.zeros((3, 4), dtype=np.int16),
        np.asarray(((0, 8, 8), (2, 0, 8)), dtype=np.int32),
        np.asarray(((100_000, 0), (0, 7)), dtype=np.int64),
    ),
)
def test_linear_support_measurement_is_exactly_equivalent(
    labels: np.ndarray,
) -> None:
    """One grouped plane pass preserves every support record exactly."""
    assert linear_native_support_objects(labels) == native_support_objects(
        labels
    )


def test_linear_support_measurement_matches_random_sparse_planes() -> None:
    """Grouped centroids retain exact results across bounded label layouts."""
    random = np.random.default_rng(20260813)
    for _ in range(20):
        labels = random.integers(0, 12, size=(37, 53), dtype=np.int32)
        labels[random.random(labels.shape) < 0.8] = 0
        assert linear_native_support_objects(labels) == (
            native_support_objects(labels)
        )


@pytest.mark.parametrize(
    "labels",
    (
        np.asarray((0, 1), dtype=np.int64),
        np.asarray(((0.0, 1.0),), dtype=np.float64),
        np.asarray(((0, -1),), dtype=np.int64),
    ),
)
def test_linear_support_measurement_preserves_validation(
    labels: np.ndarray,
) -> None:
    """The accelerator rejects the same malformed label-plane classes."""
    with pytest.raises(ValueError):
        native_support_objects(labels)
    with pytest.raises(ValueError):
        linear_native_support_objects(labels)


def test_accelerator_installation_updates_only_prospective_seams() -> None:
    """Installation binds shared compilation and the grouped support kernel."""
    successor_globals: dict[str, object] = {}
    measure_continuum_image = FunctionType(
        (lambda: None).__code__,
        successor_globals,
    )
    terminal = {
        "measure_continuum_image": measure_continuum_image,
    }

    install_continuum_accelerators(terminal)

    assert isinstance(
        terminal["_continuum_image_observations"],
        SharedContinuumImageCompiler,
    )
    assert (
        successor_globals["native_support_objects"]
        is linear_native_support_objects
    )


@pytest.mark.parametrize(
    ("failure", "expected_reason"),
    (
        (SimpleNamespace(message="container failed"), "container failed"),
        (None, "finder failed"),
    ),
)
def test_shared_compiler_preserves_failed_endpoint_observations(
    failure: object,
    expected_reason: str,
) -> None:
    """Failed runs bypass image I/O and preserve their governed reason."""
    calls: list[tuple[str, str]] = []

    def failed(
        _specifications: object,
        *,
        image_key: str,
        reason: str,
    ) -> dict[str, str]:
        calls.append((image_key, reason))
        return {"reason": reason}

    compiler = SharedContinuumImageCompiler(
        {
            "_failed_endpoint_observations": failed,
        }
    )

    output = compiler(
        SimpleNamespace(),
        SimpleNamespace(input_id="input-failed"),
        SimpleNamespace(
            result=SimpleNamespace(status="failed", failure=failure)
        ),
        SimpleNamespace(),
        SimpleNamespace(),
        SimpleNamespace(),
        (),
    )

    assert output == {"reason": expected_reason}
    assert calls == [("input-failed", expected_reason)]


def test_shared_compiler_reuses_finder_invariant_continuum_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Three finder legs load common planes and truth only once per image."""

    @dataclass(frozen=True)
    class Observation:
        image_key: str
        values: tuple[float, ...]

    loads: list[str] = []
    truth_calls: list[str] = []
    plane = np.ones((2, 2), dtype=np.float64)

    def load_plane(path: Path) -> np.ndarray:
        loads.append(path.name)
        return plane

    def truth_objects(*_args: object) -> tuple[tuple[str, ...], np.ndarray]:
        truth_calls.append("truth")
        return ("truth",), np.ones((2, 2), dtype=np.int64)

    terminal = {
        "_input_artifact_path": (
            lambda _bundle, _input, role: Path(f"{role}.fits")
        ),
        "load_fits_plane": load_plane,
        "_truth_objects": truth_objects,
        "_catalogue_and_labels": (
            lambda _run: (("catalogue",), np.ones((2, 2), dtype=np.int64))
        ),
        "_candidate_objects": lambda *_args, **_kwargs: ("candidate",),
        "measure_continuum_image": lambda *_args, **_kwargs: {
            "completeness": {"overall": 0.75}
        },
        "EndpointObservation": Observation,
        "_failed_endpoint_observations": lambda *_args, **_kwargs: {},
    }
    monkeypatch.setattr(
        "hebog.validation.external_campaign_compilation.fits.getheader",
        lambda _path: {},
    )
    compiler = SharedContinuumImageCompiler(terminal)
    verified = SimpleNamespace(
        inputs={"input-1": (SimpleNamespace(), Path("input.json"))}
    )
    campaign_input = SimpleNamespace(input_id="input-1")
    dataset = SimpleNamespace(beam=SimpleNamespace(major_fwhm_pixels=5.0))
    specification = SimpleNamespace(
        metric_family="completeness",
        stratum="overall",
        endpoint_id="completeness-overall",
    )

    outputs = tuple(
        compiler(
            verified,
            campaign_input,
            SimpleNamespace(
                result=SimpleNamespace(
                    status="success",
                    failure=None,
                    finder_id=finder,
                )
            ),
            dataset,
            SimpleNamespace(),
            SimpleNamespace(),
            (specification,),
        )
        for finder in (
            "hebog",
            "released-pybdsf",
            "pinned-pybdsf-master",
        )
    )

    expected = {
        "completeness-overall": Observation(
            image_key="input-1", values=(0.75,)
        )
    }
    assert loads == ["image.fits", "mean.fits", "rms.fits"]
    assert truth_calls == ["truth"]
    assert outputs == (expected, expected, expected)


def test_shared_compiler_replaces_its_bounded_cache_for_the_next_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only one image's common arrays remain retained at any time."""
    prepared: list[str] = []
    plane = np.ones((1, 1), dtype=np.float64)
    terminal = {
        "_input_artifact_path": (
            lambda _bundle, input_path, role: (
                input_path.parent / f"{role}.fits"
            )
        ),
        "load_fits_plane": lambda path: prepared.append(str(path)) or plane,
        "_truth_objects": lambda *_args: (("truth",), plane.astype(np.int64)),
        "_catalogue_and_labels": lambda _run: ((), plane.astype(np.int64)),
        "_candidate_objects": lambda *_args, **_kwargs: (),
        "measure_continuum_image": lambda *_args, **_kwargs: {
            "completeness": {"overall": 1.0}
        },
        "EndpointObservation": lambda **kwargs: kwargs,
        "_failed_endpoint_observations": lambda *_args, **_kwargs: {},
    }
    monkeypatch.setattr(
        "hebog.validation.external_campaign_compilation.fits.getheader",
        lambda _path: {},
    )
    compiler = SharedContinuumImageCompiler(terminal)
    verified = SimpleNamespace(
        inputs={
            "input-1": (SimpleNamespace(), Path("one/input.json")),
            "input-2": (SimpleNamespace(), Path("two/input.json")),
        }
    )
    run = SimpleNamespace(
        result=SimpleNamespace(
            status="success", failure=None, finder_id="hebog"
        )
    )
    dataset = SimpleNamespace(beam=SimpleNamespace(major_fwhm_pixels=5.0))
    specification = SimpleNamespace(
        metric_family="completeness",
        stratum="overall",
        endpoint_id="completeness-overall",
    )

    for input_id in ("input-1", "input-2"):
        compiler(
            verified,
            SimpleNamespace(input_id=input_id),
            run,
            dataset,
            SimpleNamespace(),
            SimpleNamespace(),
            (specification,),
        )

    assert prepared == [
        "one/image.fits",
        "one/mean.fits",
        "one/rms.fits",
        "two/image.fits",
        "two/mean.fits",
        "two/rms.fits",
    ]


def test_shared_compiler_cache_replacement_is_atomic_on_prepare_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed new-image load cannot associate old arrays with its key."""
    terminal = {
        "_catalogue_and_labels": lambda _run: ((), np.ones((1, 1))),
        "_candidate_objects": lambda *_args, **_kwargs: (),
        "measure_continuum_image": lambda *_args, **_kwargs: {
            "completeness": {"overall": 1.0}
        },
        "EndpointObservation": lambda **kwargs: kwargs,
    }
    compiler = SharedContinuumImageCompiler(terminal)
    old_common = (("old-truth",), np.ones((1, 1)), fits.Header())
    compiler._image_key = "input-old"
    compiler._common = old_common
    attempts: list[str] = []

    def prepare(
        *_args: object,
    ) -> tuple[object, np.ndarray, fits.Header]:
        attempts.append("input-new")
        if len(attempts) == 1:
            raise OSError("transient read failure")
        return ("new-truth",), np.ones((1, 1)), fits.Header()

    monkeypatch.setattr(compiler, "_prepare_common", prepare)
    arguments = (
        SimpleNamespace(),
        SimpleNamespace(input_id="input-new"),
        SimpleNamespace(
            result=SimpleNamespace(
                status="success", failure=None, finder_id="hebog"
            )
        ),
        SimpleNamespace(beam=SimpleNamespace(major_fwhm_pixels=5.0)),
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

    with pytest.raises(OSError, match="transient read failure"):
        compiler(*arguments)
    compiler(*arguments)

    assert attempts == ["input-new", "input-new"]
    assert compiler._image_key == "input-new"
    assert compiler._common is not old_common
