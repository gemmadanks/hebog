"""Tests for deterministic serial background and RMS window statistics."""

from __future__ import annotations

import warnings
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from hebog.algorithms.background import estimate_rms_window_statistics
from hebog.config import RmsWindowStatisticsConfig
from hebog.data_models import ImageBounds
from hebog.io.pixel_validity import valid_input_pixels


def _config(*, minimum_samples: int = 6) -> RmsWindowStatisticsConfig:
    """Return one explicit robust-statistics policy for bounded windows."""
    return RmsWindowStatisticsConfig(
        clipping_sigma=3.0,
        maximum_iterations=10,
        minimum_samples=minimum_samples,
    )


def test_estimates_known_background_and_rms_for_a_window_batch() -> None:
    """Symmetric noise has analytic statistics; a constant level has none.

    A window of one repeated value has a spread of exactly zero, which is no
    noise estimate, so it is unavailable rather than a measured zero.
    """
    noise = np.tile(np.array([-1.0, 1.0]), 8).reshape(4, 4)
    windows = np.stack((4.0 + noise, np.full((4, 4), -3.0)))

    statistics = estimate_rms_window_statistics(
        windows,
        np.ones_like(windows, dtype=np.bool_),
        _config(),
    )

    np.testing.assert_allclose(statistics.background[0], 4.0)
    np.testing.assert_allclose(statistics.rms[0], 1.0)
    np.testing.assert_array_equal(statistics.available, (True, False))
    assert np.isnan(statistics.background[1])
    assert np.isnan(statistics.rms[1])
    np.testing.assert_array_equal(statistics.valid_sample_count, (16, 16))
    np.testing.assert_array_equal(
        statistics.retained_sample_count,
        (16, 16),
    )
    with pytest.raises(ValueError, match="read-only"):
        statistics.rms[0] = 2.0


def test_clips_a_bright_outlier_without_biasing_symmetric_noise() -> None:
    """One source-like sample does not inflate its window's noise estimate."""
    window = np.concatenate(
        (np.tile(np.array([-2.0, 2.0]), 12), np.array([100.0]))
    ).reshape(1, 5, 5)

    statistics = estimate_rms_window_statistics(
        window,
        np.ones_like(window, dtype=np.bool_),
        _config(),
    )

    np.testing.assert_allclose(statistics.background, (0.0,))
    np.testing.assert_allclose(statistics.rms, (2.0,))
    np.testing.assert_array_equal(statistics.valid_sample_count, (25,))
    np.testing.assert_array_equal(statistics.retained_sample_count, (24,))


def test_excludes_masks_and_nonfinite_pixels_but_accepts_negative_values() -> (
    None
):
    """Validity is explicit; a negative sky level remains scientific data."""
    windows = np.array([[[-5.0, -3.0, -1.0], [999.0, np.nan, np.inf]]])
    valid_pixels = np.array(
        [[[True, True, True], [False, True, True]]],
        dtype=np.bool_,
    )

    statistics = estimate_rms_window_statistics(
        windows,
        valid_pixels,
        _config(minimum_samples=3),
    )

    np.testing.assert_allclose(statistics.background, (-3.0,))
    np.testing.assert_allclose(statistics.rms, (np.sqrt(8.0 / 3.0),))
    np.testing.assert_array_equal(statistics.valid_sample_count, (3,))
    np.testing.assert_array_equal(statistics.retained_sample_count, (3,))
    np.testing.assert_array_equal(statistics.available, (True,))


def test_marks_sparse_windows_unavailable_with_explicit_counts() -> None:
    """Interpolation can distinguish absent estimates from zero-valued RMS."""
    windows = np.array(
        [
            [[np.nan, np.nan], [np.nan, np.nan]],
            [[1.0, 2.0], [3.0, 4.0]],
        ]
    )
    valid_pixels = np.array(
        [
            [[True, True], [True, True]],
            [[True, True], [False, False]],
        ],
        dtype=np.bool_,
    )

    statistics = estimate_rms_window_statistics(
        windows,
        valid_pixels,
        _config(minimum_samples=3),
    )

    assert np.isnan(statistics.background).all()
    assert np.isnan(statistics.rms).all()
    np.testing.assert_array_equal(statistics.available, (False, False))
    np.testing.assert_array_equal(statistics.valid_sample_count, (0, 2))
    np.testing.assert_array_equal(statistics.retained_sample_count, (0, 2))


@given(
    offset=st.floats(
        min_value=-1e4,
        max_value=1e4,
        allow_nan=False,
        allow_infinity=False,
    ),
    scale=st.floats(
        min_value=1e-3,
        max_value=1e3,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_positive_affine_transform_preserves_window_statistics(
    offset: float,
    scale: float,
) -> None:
    """Offsets shift background and positive scaling scales RMS."""
    base = np.tile(np.array([-2.0, -1.0, 1.0, 2.0]), 4).reshape(1, 4, 4)
    valid_pixels = np.ones_like(base, dtype=np.bool_)
    reference = estimate_rms_window_statistics(
        base,
        valid_pixels,
        _config(),
    )

    transformed = estimate_rms_window_statistics(
        offset + scale * base,
        valid_pixels,
        _config(),
    )

    np.testing.assert_allclose(
        transformed.background,
        offset + scale * reference.background,
        rtol=1e-12,
        atol=1e-10,
    )
    np.testing.assert_allclose(
        transformed.rms,
        scale * reference.rms,
        rtol=1e-12,
        atol=1e-10,
    )
    np.testing.assert_array_equal(
        transformed.retained_sample_count,
        reference.retained_sample_count,
    )


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"clipping_sigma": 0.0}, "clipping_sigma"),
        ({"clipping_sigma": float("nan")}, "clipping_sigma"),
        ({"maximum_iterations": True}, "maximum_iterations.*integer"),
        ({"maximum_iterations": 1.5}, "maximum_iterations.*integer"),
        ({"maximum_iterations": 0}, "maximum_iterations"),
        ({"minimum_samples": False}, "minimum_samples.*integer"),
        ({"minimum_samples": 2.5}, "minimum_samples.*integer"),
        ({"minimum_samples": 1}, "minimum_samples"),
    ],
)
def test_rejects_invalid_window_statistics_configuration(
    updates: dict[str, float | int],
    message: str,
) -> None:
    """Invalid clipping policies fail before any image work begins."""
    values: dict[str, float | int] = {
        "clipping_sigma": 3.0,
        "maximum_iterations": 10,
        "minimum_samples": 6,
    }
    values.update(updates)

    with pytest.raises(ValueError, match=message):
        RmsWindowStatisticsConfig(**values)  # type: ignore[arg-type]


def test_rejects_non_batched_or_misaligned_windows() -> None:
    """Window batches and their validity arrays must align exactly."""
    with pytest.raises(ValueError, match="three-dimensional"):
        estimate_rms_window_statistics(
            np.ones((3, 3)),
            np.ones((3, 3), dtype=np.bool_),
            _config(),
        )

    with pytest.raises(ValueError, match="same shape"):
        estimate_rms_window_statistics(
            np.ones((2, 3, 3)),
            np.ones((1, 3, 3), dtype=np.bool_),
            _config(),
        )


@pytest.mark.parametrize("shape", [(0, 2, 2), (1, 0, 2), (1, 2, 0)])
def test_rejects_empty_batches_or_windows(shape: tuple[int, int, int]) -> None:
    """Every submitted batch must contain non-empty scientific windows."""
    with pytest.raises(ValueError, match="non-empty"):
        estimate_rms_window_statistics(
            np.empty(shape),
            np.empty(shape, dtype=np.bool_),
            _config(),
        )


def test_a_fully_invalid_window_is_unavailable_and_silent(
    recwarn: pytest.WarningsRecorder,
) -> None:
    """Blanked regions are ordinary input, not something to warn about.

    Window statistics run once per grid cell over a whole image, so a
    warning per blanked cell would bury real ones.
    """
    windows = np.zeros((2, 4, 4), dtype=np.float64)
    windows[0] = np.nan
    windows[1] = np.arange(16.0).reshape(4, 4)
    valid = np.ones(windows.shape, dtype=np.bool_)

    statistics = estimate_rms_window_statistics(
        windows, valid, _config(minimum_samples=4)
    )

    assert not bool(statistics.available[0])
    assert bool(statistics.available[1])
    assert np.isnan(statistics.background[0])
    assert np.isnan(statistics.rms[0])
    assert int(statistics.valid_sample_count[0]) == 0
    assert int(statistics.retained_sample_count[0]) == 0
    assert [warning.category.__name__ for warning in recwarn] == []


def _blanked_windows() -> tuple[np.ndarray, np.ndarray]:
    """Return windows holding every kind of excluded sample.

    One window is all NaN, one is excluded as a whole, one has a NaN pixel
    and an excluded pixel, and one has a single valid sample: each made
    NumPy or Astropy warn.
    """
    windows = np.random.default_rng(46).normal(size=(6, 9, 9))
    valid = np.ones(windows.shape, dtype=np.bool_)
    windows[0] = np.nan
    valid[1] = False
    windows[2, 4, 4] = np.nan
    valid[2, 0, 0] = False
    valid[3] = False
    valid[3, 2, 2] = True
    return windows, valid


def test_the_kernel_warns_about_no_excluded_sample() -> None:
    """Excluded samples are ordinary input, under the strictest filter."""
    windows, valid = _blanked_windows()

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        statistics = estimate_rms_window_statistics(windows, valid, _config())

    np.testing.assert_array_equal(
        statistics.available, (False, False, True, False, True, True)
    )
    np.testing.assert_array_equal(
        statistics.valid_sample_count, (0, 0, 79, 1, 81, 81)
    )
    assert np.isnan(statistics.rms[[0, 1, 3]]).all()
    assert np.isfinite(statistics.rms[[2, 4, 5]]).all()


def test_the_kernel_never_changes_the_process_warning_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Executor threads share one warning-filter list, so none is changed.

    ``warnings.catch_warnings`` saves the list on entry and restores it on
    exit. Two threads inside it at once restore each other's list, which
    let warnings escape and left ``ignore`` filters in the process for good.
    Any attempt to change the filters fails the call here, and four threads
    run the kernel under a filter that turns any warning into an error.
    """
    windows, valid = _blanked_windows()
    expected = estimate_rms_window_statistics(windows, valid, _config())

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the RMS kernel changed the warning filters")

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        filters = list(warnings.filters)
        for name in ("catch_warnings", "filterwarnings", "simplefilter"):
            monkeypatch.setattr(warnings, name, refuse)
        try:
            with ThreadPoolExecutor(max_workers=4) as pool:
                calls = [
                    pool.submit(
                        estimate_rms_window_statistics,
                        windows,
                        valid,
                        _config(),
                    )
                    for _ in range(64)
                ]
                results = [call.result() for call in calls]
        finally:
            # pytest reports a failure through these functions.
            monkeypatch.undo()
        assert warnings.filters == filters

    for result in results:
        np.testing.assert_array_equal(result.rms, expected.rms)
        np.testing.assert_array_equal(result.background, expected.background)


def test_a_window_whose_samples_all_hold_one_value_is_unavailable() -> None:
    """A spread of exactly zero is no noise, however the window got there.

    Three windows reach it differently: every sample is one value; only the
    eight equal samples around a NaN pixel are valid; and clipping removes
    the one outlier and leaves equal samples. A fourth, of noise, is
    available. Each unavailable window keeps its sample counts and has NaN
    estimates, so an interpolation stage takes its documented fallback.
    """
    generator = np.random.default_rng(46)
    windows = np.zeros((4, 9, 9))
    valid = np.ones(windows.shape, dtype=np.bool_)
    windows[0] = 2.5
    windows[1, 4, 4] = np.nan
    valid[1] = False
    valid[1, 3:6, 3:6] = True
    windows[2, 4, 4] = 100.0
    windows[3] = generator.normal(size=(9, 9))

    statistics = estimate_rms_window_statistics(windows, valid, _config())

    np.testing.assert_array_equal(
        statistics.available, (False, False, False, True)
    )
    np.testing.assert_array_equal(
        statistics.valid_sample_count, (81, 8, 81, 81)
    )
    np.testing.assert_array_equal(
        statistics.retained_sample_count, (81, 8, 80, 81)
    )
    assert np.isnan(statistics.rms[:3]).all()
    assert np.isnan(statistics.background[:3]).all()
    assert statistics.rms[3] > 0.0


def _noise_beside_a_peak(
    noise_rms: float, peak: float, offset: float = 0.0
) -> np.ndarray:
    """Return one 15-by-15 window of noise about an offset, and one peak."""
    window = offset + np.random.default_rng(46).normal(
        0.0, noise_rms, (15, 15)
    )
    window[7, 7] = peak
    return window


def test_a_spread_under_single_precision_is_unavailable() -> None:
    """The floor is the largest absolute valid value times 2**-23.

    The scale is taken before clipping: the peak, which clipping removes,
    sets it as much as an offset the samples share. Noise a millionth of
    the peak beside it is measured; noise a hundred-millionth is not, nor is
    a spread finer than single precision resolves about an offset of one.
    """
    windows = np.stack(
        (
            _noise_beside_a_peak(1e-6, 1.0),
            _noise_beside_a_peak(1e-8, 1.0),
            _noise_beside_a_peak(1e-6, 1.0, offset=1.0),
            _noise_beside_a_peak(1e-9, 1.0, offset=1.0),
            _noise_beside_a_peak(5e-8, -1.0),
            _noise_beside_a_peak(2.5e-7, -1.0),
        )
    )

    statistics = estimate_rms_window_statistics(
        windows, np.ones(windows.shape, dtype=np.bool_), _config()
    )

    np.testing.assert_array_equal(
        statistics.available, (True, False, True, False, False, True)
    )
    np.testing.assert_allclose(
        statistics.rms[[0, 2, 5]], (1e-6, 1e-6, 2.5e-7), rtol=0.15
    )
    assert np.isnan(statistics.rms[[1, 3, 4]]).all()
    # Every window keeps enough samples: the floor alone decides.
    assert (statistics.retained_sample_count > 200).all()


@pytest.mark.parametrize("exponent", (-250, -30, 0, 30, 250))
def test_the_noise_floor_does_not_depend_on_the_units(exponent: int) -> None:
    """Scaling the values scales the estimates and keeps the decisions.

    Powers of two scale every value exactly, from noise of 1e-85 Jy/beam to
    1e+69 and noise of 1e-10 beside a peak of 1e-4.
    """
    windows = np.stack(
        (
            _noise_beside_a_peak(1e-6, 1.0),
            _noise_beside_a_peak(1e-8, 1.0),
            _noise_beside_a_peak(1e-10, 1e-4),
        )
    )
    valid = np.ones(windows.shape, dtype=np.bool_)
    reference = estimate_rms_window_statistics(windows, valid, _config())

    statistics = estimate_rms_window_statistics(
        windows * 2.0**exponent, valid, _config()
    )

    np.testing.assert_array_equal(statistics.available, (True, False, True))
    np.testing.assert_array_equal(statistics.available, reference.available)
    np.testing.assert_array_equal(
        statistics.rms, reference.rms * 2.0**exponent
    )


def test_a_window_of_subnormal_tails_warns_about_nothing() -> None:
    """The tails of noise-free sources reach subnormal values silently.

    Astropy's compiled clipping reports an invalid value for windows such as
    this one, a corner of two Gaussians' tails 98 pixels from the origin,
    where values fall from 4e-188 into the subnormals; the zeros beyond are
    a block, which the rule invalidates. The warning is silenced for the
    call alone, not for the process, and the window, whose spread is no
    noise, is unavailable.
    """
    yy, xx = np.mgrid[:512, :512].astype(np.float64)
    image = np.zeros((512, 512))
    rotation = np.deg2rad(31.0)
    for member in range(2):
        east = xx - (38.0 + 7.0 * member)
        north = yy - (45.0 + 1.5 * member)
        major = east * np.cos(rotation) + north * np.sin(rotation)
        minor = north * np.cos(rotation) - east * np.sin(rotation)
        image += 0.004 * np.exp(
            -0.5 * ((major / 2.3) ** 2 + (minor / 1.6) ** 2)
        )
    valid = valid_input_pixels(image, ImageBounds(0, 512, 0, 512), (512, 512))
    window = image[np.newaxis, :35, 98:133]
    window_valid = valid[np.newaxis, :35, 98:133]
    assert window[window_valid].min() > 0.0
    assert window[window_valid].max() < 1e-187

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        statistics = estimate_rms_window_statistics(
            window, window_valid, _config()
        )

    assert not bool(statistics.available[0])
    assert np.isnan(statistics.rms[0])
    assert int(statistics.valid_sample_count[0]) == 280
    assert int(statistics.retained_sample_count[0]) == 280
