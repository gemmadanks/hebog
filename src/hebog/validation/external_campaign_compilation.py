# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Result-neutral acceleration seams for external campaign compilation."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

import numpy as np
import numpy.typing as npt
from astropy.io import fits

from hebog.validation.external_successor_compiler import (
    ContinuumSupportObject,
)

_IMAGE_DIMENSIONS = 2


def linear_native_support_objects(
    label_plane: npt.ArrayLike,
) -> tuple[ContinuumSupportObject, ...]:
    """Measure every positive support centroid with one grouped plane pass."""
    labels = np.asarray(label_plane)
    if labels.ndim != _IMAGE_DIMENSIONS or not np.issubdtype(
        labels.dtype,
        np.integer,
    ):
        raise ValueError(
            "candidate label plane must be a two-dimensional integer array"
        )
    if np.any(labels < 0):
        raise ValueError(
            "candidate label plane must contain non-negative labels"
        )
    y_pixels, x_pixels = np.nonzero(labels > 0)
    if not y_pixels.size:
        return ()
    positive_labels = np.asarray(
        labels[y_pixels, x_pixels],
        dtype=np.int64,
    )
    unique_labels, inverse = np.unique(
        positive_labels,
        return_inverse=True,
    )
    counts = np.bincount(inverse)
    sum_x = np.bincount(inverse, weights=x_pixels)
    sum_y = np.bincount(inverse, weights=y_pixels)
    return tuple(
        ContinuumSupportObject(
            identifier=f"support-{int(label)}",
            support_label=int(label),
            centre_xy=(
                float(sum_x[index] / counts[index]),
                float(sum_y[index] / counts[index]),
            ),
        )
        for index, label in enumerate(unique_labels)
    )


def install_continuum_accelerators(
    terminal_globals: dict[str, Any],
) -> None:
    """Install result-equivalent seams into one prospective compiler view."""
    terminal_globals["_continuum_image_observations"] = (
        SharedContinuumImageCompiler(terminal_globals)
    )
    successor_globals = terminal_globals["measure_continuum_image"].__globals__
    successor_globals["native_support_objects"] = linear_native_support_objects


class SharedContinuumImageCompiler:
    """Reuse finder-invariant input planes and truth for one image at a time.

    The terminal compiler visits the three continuum finders consecutively
    for each input. This callable preserves its exact per-finder calculation
    while retaining only that input's immutable truth, labels, and WCS header.
    The next input replaces the bounded cache.
    """

    def __init__(self, terminal_globals: dict[str, Any]) -> None:
        self._terminal = terminal_globals
        self._image_key: str | None = None
        self._common: tuple[Any, npt.NDArray[Any], fits.Header] | None = None

    def _prepare_common(
        self,
        verified: Any,
        campaign_input: Any,
        dataset: Any,
        recipe: Any,
        review: Any,
    ) -> tuple[Any, npt.NDArray[Any], fits.Header]:
        """Load and derive finder-invariant state exactly once per image."""
        bundle, input_path = verified.inputs[campaign_input.input_id]
        artifact_path = self._terminal["_input_artifact_path"]
        load_plane = self._terminal["load_fits_plane"]
        image_path = artifact_path(bundle, input_path, "image")
        image = load_plane(image_path)
        mean = load_plane(artifact_path(bundle, input_path, "mean"))
        rms = load_plane(artifact_path(bundle, input_path, "rms"))
        valid = np.isfinite(image) & np.isfinite(mean) & np.isfinite(rms)
        truth, truth_labels = self._terminal["_truth_objects"](
            dataset,
            recipe,
            valid,
            review,
        )
        header = cast(fits.Header, fits.getheader(image_path))
        return truth, truth_labels, header

    def __call__(  # noqa: PLR0913, PLR0917
        self,
        verified: Any,
        campaign_input: Any,
        run: Any,
        dataset: Any,
        recipe: Any,
        review: Any,
        specifications: Sequence[Any],
    ) -> dict[str, Any]:
        """Compile one finder while sharing only immutable common inputs."""
        image_key = campaign_input.input_id
        if run.result.status != "success":
            failure = run.result.failure
            return cast(
                dict[str, Any],
                self._terminal["_failed_endpoint_observations"](
                    specifications,
                    image_key=image_key,
                    reason=(
                        failure.message
                        if failure is not None
                        else "finder failed"
                    ),
                ),
            )
        if self._image_key != image_key or self._common is None:
            common = self._prepare_common(
                verified,
                campaign_input,
                dataset,
                recipe,
                review,
            )
            self._common = common
            self._image_key = image_key
        truth, truth_labels, header = self._common
        catalogue, candidate_labels = self._terminal["_catalogue_and_labels"](
            run
        )
        candidates = self._terminal["_candidate_objects"](
            catalogue,
            candidate_labels,
            finder_id=run.result.finder_id,
            header=header,
        )
        values = self._terminal["measure_continuum_image"](
            truth,
            candidates,
            truth_label_plane=truth_labels,
            candidate_label_plane=candidate_labels,
            beam_fwhm_pixels=dataset.beam.major_fwhm_pixels,
        )
        observation_type = self._terminal["EndpointObservation"]
        output: dict[str, Any] = {}
        for specification in specifications:
            untyped = values[specification.metric_family][
                specification.stratum
            ]
            row = untyped if isinstance(untyped, tuple) else (untyped,)
            output[specification.endpoint_id] = observation_type(
                image_key=image_key,
                values=tuple(float(item) for item in row),
            )
        return output
