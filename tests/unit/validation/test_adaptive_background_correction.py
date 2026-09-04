"""Mechanism fixtures for the approved adaptive-background correction."""

from __future__ import annotations

import numpy as np
import pytest

from hebog.validation.adaptive_background_diagnostics import (
    attribute_truth_support,
)


def test_mixed_core_halo_loss_is_attributed_before_publication() -> None:
    """A fixed aperture halo loss is not blamed on adaptive background."""
    y, x = np.indices((31, 31))
    truth = (y - 15) ** 2 + (x - 15) ** 2 <= 10**2
    fixed_aperture = (y - 15) ** 2 + (x - 15) ** 2 <= 5**2

    diagnostic = attribute_truth_support(
        truth,
        truth,
        truth,
        fixed_aperture,
        fixed_aperture,
    )

    assert diagnostic.adaptive_background_rejected_count == 0
    assert diagnostic.measurement_rejected_count > 0
    assert diagnostic.publication_rejected_count == 0
    assert diagnostic.measurement_support_count < diagnostic.truth_pixel_count


def test_shell_fragmentation_is_attributed_at_publication() -> None:
    """A fragmented shell remains distinct from background self-absorption."""
    y, x = np.indices((31, 31))
    radius_squared = (y - 15) ** 2 + (x - 15) ** 2
    shell = (radius_squared >= 8**2) & (radius_squared <= 10**2)
    publication = shell.copy()
    publication[:, 14:17] = False

    diagnostic = attribute_truth_support(
        shell,
        shell,
        shell,
        shell,
        publication,
    )

    assert diagnostic.adaptive_component_count == 1
    assert diagnostic.measurement_component_count == 1
    assert diagnostic.publication_component_count == 2
    assert diagnostic.publication_rejected_count > 0
    assert diagnostic.to_record()["truth_pixel_count"] == np.count_nonzero(
        shell
    )


@pytest.mark.parametrize(
    "replacement",
    [np.ones((4, 4), dtype=np.int8), np.ones((3, 4), dtype=np.bool_)],
)
def test_support_attribution_rejects_nonboolean_or_misaligned_planes(
    replacement: np.ndarray,
) -> None:
    """Diagnostic reductions fail closed rather than coercing evidence."""
    truth = np.ones((4, 4), dtype=np.bool_)

    with pytest.raises(ValueError, match="aligned boolean plane"):
        attribute_truth_support(
            truth,
            truth,
            replacement,
            truth,
            truth,
        )


def test_support_attribution_rejects_empty_truth() -> None:
    """An empty truth region cannot support causal attribution."""
    empty = np.zeros((4, 4), dtype=np.bool_)

    with pytest.raises(ValueError, match="truth must not be empty"):
        attribute_truth_support(empty, empty, empty, empty, empty)
