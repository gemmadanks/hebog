# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
"""Compact association, sharding, and complete-catalogue contracts."""

from __future__ import annotations

from dataclasses import replace
from typing import Literal

import pytest
from astropy.wcs import WCS

from hebog.algorithms.catalogue import (
    IncompleteCompactCatalogueError,
    build_compact_catalogue_shard,
    complete_compact_catalogue,
    reduce_compact_catalogue_shards,
)
from hebog.config import CompactCatalogueConfig
from hebog.data_models.catalogue_construction import CompactCatalogueOmission
from hebog.data_models.fitting import (
    CompactIslandFitResult,
    FailedCompactGaussianFit,
    FittedGaussianPixelParameters,
    GaussianFitDiagnostics,
    ValidCompactGaussianFit,
)
from hebog.data_models.images import CelestialWcs, ImageMetadata, RestoringBeam
from hebog.data_models.measurement import (
    GaussianMomentInitializer,
    MomentTarget,
    OwnedPixelPhotometry,
    ShapeUnavailableMomentMeasurement,
    UnavailableMomentMeasurement,
    ValidMomentMeasurement,
)


def _metadata() -> ImageMetadata:
    """Return one flat local ICRS WCS with an explicit MFS frequency."""
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.cunit = ["deg", "deg"]
    wcs.wcs.crpix = [32.0, 32.0]
    wcs.wcs.crval = [180.0, -30.0]
    wcs.wcs.cdelt = [-0.001, 0.001]
    return ImageMetadata(
        shape_yx=(64, 64),
        unit="Jy/beam",
        beam=RestoringBeam(0.003, 0.002, 0.0),
        celestial_wcs=CelestialWcs(
            fits_header=wcs.to_header().tostring(
                sep="\n", endcard=False, padding=False
            ),
            coordinate_frame="icrs",
        ),
        reference_frequency_hz=150_000_000.0,
    )


def _moment(
    object_kind: Literal["island", "deblended-region"],
    object_id: str,
    island_id: str,
    *,
    centroid_xy: tuple[float, float],
) -> ValidMomentMeasurement:
    """Build one valid governed compact moment record."""
    return ValidMomentMeasurement(
        target=MomentTarget(
            object_kind=object_kind,
            object_id=object_id,
            island_id=island_id,
            pixel_count=20,
        ),
        photometry=OwnedPixelPhotometry(
            peak_brightness_jy_per_beam=0.01,
            peak_position_xy=(round(centroid_xy[0]), round(centroid_xy[1])),
            owned_pixel_integrated_flux_jy=0.03,
            local_rms_jy_per_beam=0.001,
            mean_brightness_jy_per_beam=0.003,
        ),
        initializer=GaussianMomentInitializer(
            amplitude_jy_per_beam=0.01,
            centroid_xy=centroid_xy,
            covariance_xx_pixels_squared=4.0,
            covariance_xy_pixels_squared=0.0,
            covariance_yy_pixels_squared=2.0,
            major_sigma_pixels=2.0,
            minor_sigma_pixels=2**0.5,
            major_axis_angle_degrees=0.0,
        ),
    )


def _fit(
    region_id: str,
    island_id: str,
    centroid_xy: tuple[float, float],
) -> ValidCompactGaussianFit:
    """Build one valid fitted region record."""
    return ValidCompactGaussianFit(
        moment=_moment(
            "deblended-region",
            region_id,
            island_id,
            centroid_xy=centroid_xy,
        ),
        parameters=FittedGaussianPixelParameters(
            amplitude_jy_per_beam=0.01,
            centroid_xy=centroid_xy,
            major_sigma_pixels=2.0,
            minor_sigma_pixels=1.5,
            major_axis_angle_degrees=0.0,
            integrated_flux_jy=0.02,
            local_rms_jy_per_beam=0.0011,
        ),
        uncertainty=None,
        diagnostics=GaussianFitDiagnostics(True, 8, 1.0, 14, 1.0 / 14, False),
        quality_flags=(),
    )


def _island_fit(island_number: int = 1) -> CompactIslandFitResult:
    island_id = f"island-{island_number:05d}"
    return CompactIslandFitResult(
        island_measurement=_moment(
            "island", island_id, island_id, centroid_xy=(31.0, 31.0)
        ),
        region_fits=(
            _fit(
                f"{island_id}-region-00002",
                island_id,
                (33.0, 31.0),
            ),
            _fit(
                f"{island_id}-region-00001",
                island_id,
                (29.0, 31.0),
            ),
        ),
    )


def _config(maximum_records: int = 100) -> CompactCatalogueConfig:
    return CompactCatalogueConfig(
        maximum_catalogue_records=maximum_records,
        deconvolution_relative_tolerance=1e-10,
    )


def test_shard_keeps_island_source_and_component_records_distinct() -> None:
    """The reviewed compact policy creates explicit one-to-one associations."""
    shard = build_compact_catalogue_shard(
        (_island_fit(),),
        _metadata(),
        deconvolution_relative_tolerance=1e-10,
    )

    assert [item.island_id for item in shard.islands] == ["island-00001"]
    assert [item.source_id for item in shard.sources] == [
        "source-island-00001-region-00001",
        "source-island-00001-region-00002",
    ]
    assert [
        item.gaussian_component_id for item in shard.gaussian_components
    ] == [
        "gaussian-island-00001-region-00001",
        "gaussian-island-00001-region-00002",
    ]
    for source, component in zip(
        shard.sources, shard.gaussian_components, strict=True
    ):
        assert component.source_id == source.source_id
        assert component.island_id == source.island_id
        assert component.flux == source.flux
        assert component.fitted_shape == source.fitted_shape
        assert source.spectral_model.kind == "reference-frequency-only"
        assert source.spectral_model.reference_frequency_hz == 150_000_000.0


def test_island_flux_is_recomputed_with_local_wcs_geometry() -> None:
    """Catalogue island flux does not retain provisional worker geometry."""
    shard = build_compact_catalogue_shard(
        (_island_fit(),),
        _metadata(),
        deconvolution_relative_tolerance=1e-10,
    )

    island = shard.islands[0]
    assert island.integrated_flux_jy != 0.03
    assert island.mean_brightness_jy_per_beam == 0.003
    assert island.local_rms_jy_per_beam == 0.001


def test_canonical_catalogue_is_invariant_to_shard_and_record_order() -> None:
    """Global IDs and values never depend on task completion order."""
    metadata = _metadata()
    first = build_compact_catalogue_shard(
        (_island_fit(),),
        metadata,
        deconvolution_relative_tolerance=1e-10,
    )
    reversed_shard = replace(
        first,
        sources=tuple(reversed(first.sources)),
        gaussian_components=tuple(reversed(first.gaussian_components)),
    )

    catalogue = complete_compact_catalogue(
        catalogue_id="compact-reference",
        metadata=metadata,
        shards=(reversed_shard,),
        deferred_island_ids=(),
        config=_config(),
    )

    assert catalogue.source_count == 2
    assert catalogue.catalogue.sources == tuple(
        sorted(first.sources, key=lambda x: x.source_id)
    )
    assert catalogue.reduction_depth == 0
    assert catalogue.maximum_shard_record_count == 2


def test_shards_are_combined_by_a_bounded_canonical_tree() -> None:
    """Catalogue reduction has pairwise fan-in and logarithmic depth."""
    metadata = _metadata()
    shards = tuple(
        build_compact_catalogue_shard(
            (_island_fit(island_number),),
            metadata,
            deconvolution_relative_tolerance=1e-10,
        )
        for island_number in range(1, 6)
    )

    forward = reduce_compact_catalogue_shards(shards)
    reversed_result = reduce_compact_catalogue_shards(tuple(reversed(shards)))

    assert forward == reversed_result
    assert forward.input_shard_count == 5
    assert forward.reduction_depth == 3
    assert forward.maximum_input_shard_record_count == 2
    assert len(forward.shard.islands) == 5
    assert len(forward.shard.sources) == 10
    assert forward.shard.sources == tuple(
        sorted(forward.shard.sources, key=lambda item: item.source_id)
    )


def test_empty_shard_reduction_has_zero_depth_and_records() -> None:
    """A scientifically empty catalogue remains structurally reducible."""
    reduction = reduce_compact_catalogue_shards(())

    assert reduction.input_shard_count == 0
    assert reduction.reduction_depth == 0
    assert reduction.maximum_input_shard_record_count == 0
    assert reduction.shard.record_count == 0


def test_complete_catalogue_rejects_fit_omission_and_phase_five_deferral() -> (
    None
):
    """Incomplete compact results cannot masquerade as normal catalogues."""
    island_fit = _island_fit()
    valid = island_fit.region_fits[0]
    assert isinstance(valid, ValidCompactGaussianFit)
    failed = FailedCompactGaussianFit(
        moment=valid.moment,
        reason="fit-non-convergence",
        diagnostics=valid.diagnostics,
        quality_flags=("fit-non-convergence",),
    )
    shard = build_compact_catalogue_shard(
        (replace(island_fit, region_fits=(failed,)),),
        _metadata(),
        deconvolution_relative_tolerance=1e-10,
    )
    assert shard.omissions == (
        CompactCatalogueOmission(
            object_id=failed.moment.target.object_id,
            reason="fit-non-convergence",
        ),
    )

    with pytest.raises(
        IncompleteCompactCatalogueError, match="1 fit omission"
    ):
        complete_compact_catalogue(
            catalogue_id="compact-reference",
            metadata=_metadata(),
            shards=(shard,),
            deferred_island_ids=(),
            config=_config(),
        )
    with pytest.raises(IncompleteCompactCatalogueError, match="1 deferred"):
        complete_compact_catalogue(
            catalogue_id="compact-reference",
            metadata=_metadata(),
            shards=(),
            deferred_island_ids=("island-00002",),
            config=_config(),
        )


def test_invalid_island_measurement_is_an_explicit_shard_omission() -> None:
    """Missing island photometry cannot become a fabricated catalogue row."""
    island_fit = _island_fit()
    target = island_fit.island_measurement.target
    unavailable = UnavailableMomentMeasurement(
        target=target,
        reason="non-positive-measurement",
    )

    shard = build_compact_catalogue_shard(
        (replace(island_fit, island_measurement=unavailable),),
        _metadata(),
        deconvolution_relative_tolerance=1e-10,
    )

    assert not shard.islands
    assert shard.omissions[0] == CompactCatalogueOmission(
        object_id=target.object_id,
        reason="non-positive-measurement",
    )


def test_shape_unavailable_island_retains_valid_pixel_photometry() -> None:
    """An island ellipse is unnecessary when finite flux remains available."""
    island_fit = _island_fit()
    valid = island_fit.island_measurement
    assert isinstance(valid, ValidMomentMeasurement)
    shape_unavailable = ShapeUnavailableMomentMeasurement(
        target=valid.target,
        photometry=valid.photometry,
        reason="singular-covariance",
    )

    shard = build_compact_catalogue_shard(
        (replace(island_fit, island_measurement=shape_unavailable),),
        _metadata(),
        deconvolution_relative_tolerance=1e-10,
    )

    assert len(shard.islands) == 1
    assert not shard.omissions


def test_in_memory_catalogue_assembly_has_an_explicit_record_cap() -> None:
    """The convenience object cannot gather an unbounded source population."""
    shard = build_compact_catalogue_shard(
        (_island_fit(),),
        _metadata(),
        deconvolution_relative_tolerance=1e-10,
    )

    with pytest.raises(IncompleteCompactCatalogueError, match="record limit"):
        complete_compact_catalogue(
            catalogue_id="compact-reference",
            metadata=_metadata(),
            shards=(shard,),
            deferred_island_ids=(),
            config=_config(maximum_records=1),
        )


@pytest.mark.parametrize(
    ("maximum_records", "tolerance", "message"),
    [
        (0, 1e-10, "maximum_catalogue_records"),
        (True, 1e-10, "maximum_catalogue_records"),
        (10, 0.0, "deconvolution_relative_tolerance"),
        (10, 1.0, "deconvolution_relative_tolerance"),
    ],
)
def test_catalogue_policy_rejects_invalid_bounds(
    maximum_records: int,
    tolerance: float,
    message: str,
) -> None:
    """Catalogue memory and deconvolution policies are explicit."""
    with pytest.raises(ValueError, match=message):
        CompactCatalogueConfig(
            maximum_catalogue_records=maximum_records,
            deconvolution_relative_tolerance=tolerance,
        )
