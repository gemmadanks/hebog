"""Finder-independent truth compilation for fresh Phase 5 evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
import numpy.typing as npt

from hebog.validation.external_successor_compiler import ContinuumTruthObject
from hebog.validation.observable_truth import measure_observable_truth

_IMAGE_DIMENSIONS = 2


@dataclass(frozen=True, slots=True)
class ObservableTruthSpecification:
    """Scientific metadata for one injected truth group."""

    identifier: str
    catalogue_role: Literal["astronomical-source", "artifact"]
    strata: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ObservableTruthPlanes:
    """Noiseless signal and declared support for one truth group."""

    signal_jy_per_beam: npt.ArrayLike
    declared_support: npt.ArrayLike


@dataclass(frozen=True, slots=True)
class ObservableTruthSupport:
    """Auditable support metadata for one compiled truth group."""

    identifier: str
    support_label: int
    declared_pixel_count: int
    observable_pixel_count: int
    observable_fraction: float


@dataclass(frozen=True, slots=True)
class ObservableTruthCompilation:
    """A complete truth catalogue and its shared observable support domain."""

    objects: tuple[ContinuumTruthObject, ...]
    label_plane: npt.NDArray[np.int64]
    supports: tuple[ObservableTruthSupport, ...]


def compile_observable_truth(
    specifications: Sequence[ObservableTruthSpecification],
    planes_by_identifier: Mapping[str, ObservableTruthPlanes],
    valid_pixels: npt.ArrayLike,
    *,
    beam_major_fwhm_pixels: float,
    beam_minor_fwhm_pixels: float,
) -> ObservableTruthCompilation:
    """Compile flux, centroid, labels, and support on one valid domain.

    The specification order defines stable positive labels. Generated planes
    must have exactly the same identifiers. Finder products are deliberately
    absent from this boundary.
    """
    identifiers = tuple(item.identifier for item in specifications)
    if not identifiers:
        raise ValueError("observable truth specifications must not be empty")
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("observable truth identifiers must be unique")
    if set(identifiers) != set(planes_by_identifier):
        raise ValueError(
            "observable truth specifications and generated planes differ"
        )

    valid = np.asarray(valid_pixels)
    if valid.ndim != _IMAGE_DIMENSIONS or valid.dtype != np.bool_:
        raise ValueError(
            "valid pixels must be a two-dimensional boolean plane"
        )
    labels = np.zeros(valid.shape, dtype=np.int64)
    objects: list[ContinuumTruthObject] = []
    supports: list[ObservableTruthSupport] = []
    for label, specification in enumerate(specifications, start=1):
        planes = planes_by_identifier[specification.identifier]
        signal = np.asarray(planes.signal_jy_per_beam, dtype=np.float64)
        declared = np.asarray(planes.declared_support)
        measurement = measure_observable_truth(
            signal,
            declared,
            valid,
            beam_major_fwhm_pixels=beam_major_fwhm_pixels,
            beam_minor_fwhm_pixels=beam_minor_fwhm_pixels,
        )
        observable_support = declared & valid & np.isfinite(signal)
        if np.any(labels[observable_support] != 0):
            raise ValueError("continuum truth supports overlap")
        labels[observable_support] = label
        objects.append(
            ContinuumTruthObject(
                identifier=specification.identifier,
                support_label=label,
                centre_xy=measurement.centroid_xy,
                integrated_flux_jy=measurement.integrated_flux_jy,
                catalogue_role=specification.catalogue_role,
                strata=specification.strata,
            )
        )
        supports.append(
            ObservableTruthSupport(
                identifier=specification.identifier,
                support_label=label,
                declared_pixel_count=(
                    measurement.declared_support_pixel_count
                ),
                observable_pixel_count=(
                    measurement.observable_support_pixel_count
                ),
                observable_fraction=(measurement.observable_support_fraction),
            )
        )
    labels.flags.writeable = False
    return ObservableTruthCompilation(
        objects=tuple(objects),
        label_plane=labels,
        supports=tuple(supports),
    )
