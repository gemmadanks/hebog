# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Prospective compiler composition for Phase 5 recovery evidence."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, cast

import numpy as np
import numpy.typing as npt
from astropy.io import fits

from hebog.validation.evidence import (
    CampaignFailure,
    CampaignRealizationDiagnostic,
)
from hebog.validation.post_campaign_science import (
    diagnose_compact_component_realization,
)

_IMAGE_DIMENSIONS = 2
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _label_plane(
    values: npt.ArrayLike,
    *,
    name: str,
) -> npt.NDArray[np.int64]:
    """Require one non-negative two-dimensional integer label plane."""
    labels = np.asarray(values)
    if labels.ndim != _IMAGE_DIMENSIONS or not np.issubdtype(
        labels.dtype,
        np.integer,
    ):
        raise ValueError(
            f"{name} must be a two-dimensional integer label plane"
        )
    if np.any(labels < 0):
        raise ValueError(f"{name} must contain non-negative labels")
    return np.asarray(labels, dtype=np.int64)


def label_planes_on_valid_domain(
    truth_label_plane: npt.ArrayLike,
    candidate_label_plane: npt.ArrayLike,
    valid_pixels: npt.ArrayLike,
) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.int64]]:
    """Return truth and finder labels on one symmetric valid domain."""
    truth = _label_plane(truth_label_plane, name="truth label plane")
    candidate = _label_plane(
        candidate_label_plane,
        name="candidate label plane",
    )
    valid = np.asarray(valid_pixels)
    if valid.ndim != _IMAGE_DIMENSIONS or valid.dtype != np.bool_:
        raise ValueError(
            "valid pixels must be a two-dimensional boolean valid mask"
        )
    if truth.shape != candidate.shape or truth.shape != valid.shape:
        raise ValueError("truth, candidate, and valid planes must be aligned")
    observable_truth = np.where(valid, truth, 0).astype(np.int64, copy=False)
    observable_candidate = np.where(valid, candidate, 0).astype(
        np.int64,
        copy=False,
    )
    observable_truth.setflags(write=False)
    observable_candidate.setflags(write=False)
    return observable_truth, observable_candidate


def require_candidate_configuration(
    verified: Any,
    expected_sha256: str,
) -> None:
    """Require every Hebog candidate run to match its approved identity."""
    if _SHA256_PATTERN.fullmatch(expected_sha256) is None:
        raise ValueError(
            "expected candidate configuration SHA-256 is malformed"
        )
    inputs = tuple(verified.request.inputs)
    if not inputs:
        raise ValueError("candidate configuration population is empty")
    for campaign_input in inputs:
        key = (campaign_input.input_id, "hebog", "candidate")
        try:
            run = verified.runs[key]
        except KeyError:
            raise ValueError(
                f"Hebog candidate run is absent: {campaign_input.input_id}"
            ) from None
        if run.result.configuration_sha256 != expected_sha256:
            raise ValueError(
                "Hebog candidate configuration differs from the approved "
                f"identity: {campaign_input.input_id}"
            )


def compact_component_realization(  # noqa: PLR0913
    original: Callable[..., Any],
    catalogue_loader: Callable[[Any], Sequence[Any]],
    run: Any,
    dataset: Any,
    recipe: Any,
    *,
    implementation_identifier: str,
    outlier_thresholds: Any,
    position_angle_minimum_axis_ratio: float,
) -> Any:
    """Compile one compact result using fitted-component semantics."""
    if run.result.status != "success":
        return original(
            run,
            dataset,
            recipe,
            implementation_identifier=implementation_identifier,
            outlier_thresholds=outlier_thresholds,
            position_angle_minimum_axis_ratio=(
                position_angle_minimum_axis_ratio
            ),
        )
    try:
        return diagnose_compact_component_realization(
            dataset,
            recipe,
            catalogue_loader(run),
            implementation_identifier=implementation_identifier,
            outlier_thresholds=outlier_thresholds,
            position_angle_minimum_axis_ratio=(
                position_angle_minimum_axis_ratio
            ),
        )
    except Exception as error:
        return CampaignRealizationDiagnostic(
            implementation_identifier=implementation_identifier,
            seed=recipe.seed,
            status="failure",
            failure=CampaignFailure(
                stage="campaign-comparison",
                exception_type=type(error).__name__,
                message=str(error) or repr(error),
                traceback_sha256=hashlib.sha256(
                    repr(error).encode()
                ).hexdigest(),
            ),
        )


@dataclass(frozen=True, slots=True)
class _ContinuumCommon:
    """Finder-invariant state retained for only one Continuum image."""

    truth: Any
    truth_labels: npt.NDArray[np.int64]
    valid_pixels: npt.NDArray[np.bool_]
    header: fits.Header


class RecoveryContinuumImageCompiler:
    """Compile every finder on shared valid-domain Continuum inputs."""

    def __init__(self, terminal_globals: dict[str, Any]) -> None:
        self._terminal = terminal_globals
        self._image_key: str | None = None
        self._common: _ContinuumCommon | None = None

    def _prepare_common(
        self,
        verified: Any,
        campaign_input: Any,
        dataset: Any,
        recipe: Any,
        review: Any,
    ) -> _ContinuumCommon:
        """Load finder-invariant inputs and derive one observable domain."""
        bundle, input_path = verified.inputs[campaign_input.input_id]
        artifact_path = self._terminal["_input_artifact_path"]
        load_plane = self._terminal["load_fits_plane"]
        image_path = artifact_path(bundle, input_path, "image")
        image = load_plane(image_path)
        mean = load_plane(artifact_path(bundle, input_path, "mean"))
        rms = load_plane(artifact_path(bundle, input_path, "rms"))
        valid = np.isfinite(image) & np.isfinite(mean) & np.isfinite(rms)
        if np.any(np.isfinite(image) != valid):
            raise ValueError("compiler mean/RMS validity differs from image")
        truth, truth_labels = self._terminal["_truth_objects"](
            dataset,
            recipe,
            valid,
            review,
        )
        header = cast(fits.Header, fits.getheader(image_path))
        return _ContinuumCommon(
            truth=truth,
            truth_labels=np.asarray(truth_labels, dtype=np.int64),
            valid_pixels=np.asarray(valid, dtype=np.bool_),
            header=header,
        )

    def __call__(  # noqa: PLR0913
        self,
        verified: Any,
        campaign_input: Any,
        run: Any,
        dataset: Any,
        recipe: Any,
        review: Any,
        specifications: Sequence[Any],
    ) -> dict[str, Any]:
        """Compile one finder without changing endpoint policy."""
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
        common = self._common
        catalogue, candidate_labels = self._terminal["_catalogue_and_labels"](
            run
        )
        truth_labels, candidate_labels = label_planes_on_valid_domain(
            common.truth_labels,
            candidate_labels,
            common.valid_pixels,
        )
        candidates = self._terminal["_candidate_objects"](
            catalogue,
            candidate_labels,
            finder_id=run.result.finder_id,
            header=common.header,
        )
        values = self._terminal["measure_continuum_image"](
            common.truth,
            candidates,
            truth_label_plane=truth_labels,
            candidate_label_plane=candidate_labels,
            beam_fwhm_pixels=dataset.beam.major_fwhm_pixels,
        )
        observation_type = self._terminal["EndpointObservation"]
        output: dict[str, Any] = {}
        for specification in specifications:
            untyped = cast(
                float | tuple[float, ...],
                values[specification.metric_family][specification.stratum],
            )
            row = untyped if isinstance(untyped, tuple) else (untyped,)
            output[specification.endpoint_id] = observation_type(
                image_key=image_key,
                values=tuple(float(item) for item in row),
            )
        return output


def install_recovery_compiler_seams(
    terminal_globals: dict[str, Any],
    *,
    expected_candidate_configuration_sha256: str,
) -> None:
    """Install only reviewed prospective measurement and identity seams."""
    original_verify = terminal_globals["verify_terminal_campaign"]
    original_compact = terminal_globals["_compact_realization"]
    catalogue_loader = terminal_globals["_compact_catalogue"]

    def verified_campaign(*args: object, **kwargs: object) -> Any:
        verified = original_verify(*args, **kwargs)
        require_candidate_configuration(
            verified,
            expected_candidate_configuration_sha256,
        )
        return verified

    def component_view(*args: object, **kwargs: object) -> Any:
        return compact_component_realization(
            original_compact,
            catalogue_loader,
            *args,
            **kwargs,
        )

    terminal_globals["verify_terminal_campaign"] = verified_campaign
    terminal_globals["_continuum_image_observations"] = (
        RecoveryContinuumImageCompiler(terminal_globals)
    )
    terminal_globals["_compact_realization"] = component_view
