# pyright: reportAttributeAccessIssue=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
"""Hebog as the source finder of Rapthor's ``filter_skymodel`` step.

Rapthor's step runs PyBDSF through LSMTool on one sector's two images, the
primary-beam-corrected true-sky image and the flat-noise image, then
filters the sector's sky models with LSMTool's ``filter_sources``.
:func:`find_sector_sources` runs Hebog in its place, in-process on the
executor Rapthor builds, and writes the files Rapthor and ``filter_sources``
read, under the names Rapthor's PyBDSF step gives them. Rapthor calls it
and then ``filter_sources``; this module imports no Rapthor, Prefect,
LSMTool or scheduler objects.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, replace
from math import isfinite
from pathlib import Path
from time import monotonic
from typing import Literal
from uuid import uuid4

import numpy as np
from astropy.io import fits
from astropy.wcs.utils import proj_plane_pixel_scales

from hebog.adapters.rapthor_catalogue import write_rapthor_catalogue_fits
from hebog.config import SourceFinderConfig
from hebog.data_models import SourceFinderRequest, SourceFinderResult
from hebog.data_models.images import ImageMetadata
from hebog.executors import Executor
from hebog.io import (
    FitsImageSource,
    celestial_wcs_from_metadata,
    read_catalogue_fits_product,
)
from hebog.pipeline import InvalidSourceFinderInputError, find_sources

_SCHEMA_VERSION = 2
# PyBDSF's beam area in pixels is 1.1331 times the beam's major axis over
# the pixel width times its minor axis over the pixel height
# (``readimage.pixel_beamarea``); its default minimum island is a third of
# that, truncated, and never fewer than six pixels (``islands.py``).
_PYBDSF_BEAM_AREA_FACTOR = 1.1331
_PYBDSF_MINIMUM_ISLAND_PIXELS = 6
_BLANKED_MESSAGE = "All pixels in the image are blanked."
# Rows written at once: 128 rows of a 20,000-pixel plane hold 10 MB.
_BLOCK_ROWS = 128


class RapthorBlankedImageError(RuntimeError):
    """A sector image has no pixel to measure, as PyBDSF reports it.

    PyBDSF raises ``RuntimeError("All pixels in the image are blanked.")``
    when every pixel is NaN, and Rapthor's step recognises that message and
    writes its empty products, so this error carries the same message and
    type. Hebog also counts as blank a pixel inside a 3x3 square of one
    value, as imagers fill blanked regions, so an image of one value is
    blank too.
    """

    def __init__(self) -> None:
        """Carry PyBDSF's message."""
        super().__init__(_BLANKED_MESSAGE)


@dataclass(frozen=True, slots=True)
class RapthorCompatibilityConfig:
    """Rapthor's source-finding settings, under Rapthor's names.

    ``threshpix`` and ``threshisl`` are the detection and island thresholds
    in sigma that Rapthor's imaging strategy passes (5 and 3, or 5 and 4 in
    early self-calibration cycles). The minimum island size is not a
    setting: :func:`find_sector_sources` applies PyBDSF's rule to the
    sector's beam. ``profile`` and ``background`` choose Hebog's science
    profile and background; plan task 21 decides Rapthor's values. The other
    options LSMTool passes to PyBDSF (the RMS boxes, the bright-source
    threshold and the wavelet scales) are fixed by Hebog's reviewed science,
    and LSMTool's mask filter is LSMTool's own; the Rapthor source-finding
    contract maps each to what replaces it.
    """

    threshpix: float
    threshisl: float
    profile: Literal["continuum", "compact"] = "continuum"
    background: Literal["estimated", "zero"] = "estimated"

    def __post_init__(self) -> None:
        """Fail where the settings are made, not after the images load."""
        self.source_finder_config(_PYBDSF_MINIMUM_ISLAND_PIXELS)

    def source_finder_config(
        self, minimum_island_pixels: int
    ) -> SourceFinderConfig:
        """Return the finder's configuration for one minimum island size."""
        return SourceFinderConfig(
            detection_threshold_sigma=self.threshpix,
            island_threshold_sigma=self.threshisl,
            minimum_island_pixels=minimum_island_pixels,
            profile=self.profile,
            background=self.background,
        )


@dataclass(frozen=True, slots=True)
class RapthorSourceFindingRequest:
    """One Rapthor sector's two images, and the root its products are named by.

    ``output_root`` is Rapthor's ``<working directory>/<image name>``. The
    products are ``<root>.source_catalog.fits``, ``<root>.true_sky_rms.fits``
    and ``<root>.flat_noise_rms.fits``, the island mask is
    ``<true-sky image name>.mask.fits`` in the root's directory, and Hebog's
    own product bundle is the directory ``<root>.hebog``. ``run_id`` names
    the sector's analysis; a retried task passes the same one.
    """

    true_sky_image_path: Path
    flat_noise_image_path: Path
    output_root: Path
    run_id: str
    schema_version: Literal[2] = _SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Reject unsupported versions and empty run identifiers."""
        if self.schema_version != _SCHEMA_VERSION:
            raise ValueError("unsupported Rapthor request schema version")
        if not self.run_id:
            raise ValueError("run_id must not be empty")


@dataclass(frozen=True, slots=True)
class RapthorSourceFindingResult:
    """The files one sector's analysis wrote for Rapthor, and its counts.

    ``mask_path`` is the island mask LSMTool's ``filter_sources`` clips to
    the sector polygon, in place, and groups the sky model by. With no
    island, as with PyBDSF's ``nisl`` of zero, LSMTool writes a dummy sky
    model instead. ``products_directory`` is Hebog's own bundle, whose
    diagnostics bind the run to its inputs, configuration and science.
    """

    source_catalog_path: Path
    true_sky_rms_path: Path
    flat_noise_rms_path: Path
    mask_path: Path
    products_directory: Path
    source_count: int
    island_count: int
    wall_seconds: float
    schema_version: Literal[2] = _SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate the version and scalar result metadata."""
        if self.schema_version != _SCHEMA_VERSION:
            raise ValueError("unsupported Rapthor result schema version")
        if self.source_count < 0:
            raise ValueError("source_count cannot be negative")
        if self.island_count < 0:
            raise ValueError("island_count cannot be negative")
        if not isfinite(self.wall_seconds) or self.wall_seconds < 0:
            raise ValueError("wall_seconds must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class _ProductNames:
    """Where one sector's products go, as Rapthor's PyBDSF step names them."""

    source_catalog: Path
    true_sky_rms: Path
    flat_noise_rms: Path
    mask: Path
    products_directory: Path

    @classmethod
    def of(cls, request: RapthorSourceFindingRequest) -> _ProductNames:
        """Name the products of one request whose paths are absolute."""
        directory = request.output_root.parent
        stem = request.output_root.name
        return cls(
            source_catalog=directory / f"{stem}.source_catalog.fits",
            true_sky_rms=directory / f"{stem}.true_sky_rms.fits",
            flat_noise_rms=directory / f"{stem}.flat_noise_rms.fits",
            mask=directory / f"{request.true_sky_image_path.name}.mask.fits",
            products_directory=directory / f"{stem}.hebog",
        )

    def rapthor_files(self) -> tuple[Path, ...]:
        """Return the four files Rapthor's step reads."""
        return (
            self.source_catalog,
            self.true_sky_rms,
            self.flat_noise_rms,
            self.mask,
        )


def pybdsf_minimum_island_pixels(metadata: ImageMetadata) -> int:
    """Return the minimum island size PyBDSF would use, in pixels.

    PyBDSF's ``minpix_isl`` defaults to ``max(6, int(beam area / 3))``, with
    the beam area in pixels taken as 1.1331 times the major axis over the
    pixel width times the minor axis over the pixel height. The widths are
    the celestial WCS's pixel scales, ``|CDELT1|`` and ``|CDELT2|`` for the
    north-up images Rapthor writes, as PyBDSF reads them.
    """
    scale_x, scale_y = (
        float(scale)
        for scale in proj_plane_pixel_scales(
            celestial_wcs_from_metadata(metadata)
        )
    )
    beam_area_pixels = (
        _PYBDSF_BEAM_AREA_FACTOR
        * (metadata.beam.major_fwhm_degrees / scale_x)
        * (metadata.beam.minor_fwhm_degrees / scale_y)
    )
    return max(_PYBDSF_MINIMUM_ISLAND_PIXELS, int(beam_area_pixels / 3.0))


def find_sector_sources(
    request: RapthorSourceFindingRequest,
    config: RapthorCompatibilityConfig,
    executor: Executor,
) -> RapthorSourceFindingResult:
    """Find one sector's sources and write the files Rapthor's step reads.

    One :func:`hebog.find_sources` run analyses the true-sky image and
    estimates the flat-noise image's RMS, on the executor the caller built,
    with Rapthor's thresholds and PyBDSF's minimum island for the sector's
    beam. It publishes Hebog's bundle in ``<root>.hebog``, from which this
    function writes the eight-column catalogue, the two RMS maps and the
    island mask in PyBDSF's four-axis layout, each under Rapthor's name.

    Files an earlier run left under those four names are removed before the
    analysis starts, and a failure removes those this call wrote, so after
    a failed call none exists. A retry of a finished request reuses the
    bundle without analysing the images again; a bundle of another request
    is refused and kept.

    Raises:
        RapthorBlankedImageError: If either image has no pixel Hebog
            measures, so its RMS is unavailable. Rapthor's step handles it
            as it handles PyBDSF's error.
        hebog.pipeline.SourceFinderError: If Hebog refuses the sector, or
            ``<root>.hebog`` holds another run's products. Rapthor may fall
            back to PyBDSF on these typed failures.
    """
    started = monotonic()
    request = replace(
        request,
        true_sky_image_path=request.true_sky_image_path.absolute(),
        flat_noise_image_path=request.flat_noise_image_path.absolute(),
        output_root=request.output_root.absolute(),
    )
    names = _ProductNames.of(request)
    _remove(names.rapthor_files())
    true_sky = _image_metadata(request.true_sky_image_path)
    minimum_island_pixels = _shared_minimum_island_pixels(
        true_sky,
        _image_metadata(request.flat_noise_image_path),
        request.flat_noise_image_path,
    )
    result = find_sources(
        SourceFinderRequest(
            image_path=request.true_sky_image_path,
            output_directory=names.products_directory,
            run_id=request.run_id,
            flat_noise_image_path=request.flat_noise_image_path,
        ),
        config.source_finder_config(minimum_island_pixels),
        executor,
    )
    flat_noise_rms = _require_unblanked(result)
    try:
        write_rapthor_catalogue_fits(
            names.source_catalog, read_catalogue_fits_product(result.catalogue)
        )
        _copy(result.rms.path, names.true_sky_rms)
        _copy(flat_noise_rms, names.flat_noise_rms)
        _write_island_mask(result.mask.path, true_sky, names.mask)
    except BaseException:
        _remove(names.rapthor_files())
        raise
    return RapthorSourceFindingResult(
        source_catalog_path=names.source_catalog,
        true_sky_rms_path=names.true_sky_rms,
        flat_noise_rms_path=names.flat_noise_rms,
        mask_path=names.mask,
        products_directory=names.products_directory,
        source_count=result.source_count,
        island_count=result.island_count,
        wall_seconds=monotonic() - started,
    )


def _remove(paths: tuple[Path, ...]) -> None:
    for path in paths:
        path.unlink(missing_ok=True)


def _image_metadata(path: Path) -> ImageMetadata:
    """Read one image's metadata, failing as the finder would."""
    source = FitsImageSource(path)
    try:
        return source.metadata()
    except (OSError, ValueError) as error:
        raise InvalidSourceFinderInputError(
            f"invalid FITS source-finder input: {error}"
        ) from error
    finally:
        source.close()


def _shared_minimum_island_pixels(
    true_sky: ImageMetadata,
    flat_noise: ImageMetadata,
    flat_noise_path: Path,
) -> int:
    """Return the one minimum island both images' beams give.

    Hebog applies one configuration to both of a sector's images, while
    PyBDSF derives its minimum from each image's beam. WSClean writes both
    from one restoring beam, so the two agree; images whose beams disagree
    are refused rather than analysed under the wrong minimum.
    """
    minimum = pybdsf_minimum_island_pixels(true_sky)
    flat_noise_minimum = pybdsf_minimum_island_pixels(flat_noise)
    if flat_noise_minimum != minimum:
        raise InvalidSourceFinderInputError(
            "the true-sky and flat-noise images' beams give PyBDSF minimum "
            f"island sizes of {minimum} and {flat_noise_minimum} pixels, "
            f"and Hebog applies one to both: {flat_noise_path}"
        )
    return minimum


def _require_unblanked(result: SourceFinderResult) -> Path:
    """Raise PyBDSF's error for an image with no pixel to measure.

    An image's RMS is unavailable when no pixel is valid, finite and outside
    any 3x3 square of one value, with a positive noise estimate; even a 3x3
    patch of noise has one. Returns the flat-noise RMS product's path.
    """
    flat_noise_rms = result.flat_noise_rms
    if flat_noise_rms is None:  # pragma: no cover - the request names one
        raise AssertionError("the run published no flat-noise RMS")
    if "unavailable" in (
        result.rms.scientific_status,
        flat_noise_rms.scientific_status,
    ):
        raise RapthorBlankedImageError
    return flat_noise_rms.path


def _temporary(path: Path) -> Path:
    return path.with_name(f".{path.name}.{uuid4().hex}.tmp")


def _copy(source: Path, destination: Path) -> None:
    """Copy one published product to Rapthor's name in one rename."""
    temporary = _temporary(destination)
    try:
        shutil.copyfile(source, temporary)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def _island_mask_header(metadata: ImageMetadata) -> fits.Header:
    """Return PyBDSF's island-mask header for one image.

    PyBDSF writes the two celestial axes, then a Stokes axis and a frequency
    axis of one pixel each (``functions.make_fits_image``). Its frequency
    unit, ``HZ``, is written as the standard ``Hz``.
    """
    height, width = metadata.shape_yx
    header = fits.Header()
    header["SIMPLE"] = True
    header["BITPIX"] = -32
    header["NAXIS"] = 4
    header["NAXIS1"] = width
    header["NAXIS2"] = height
    header["NAXIS3"] = 1
    header["NAXIS4"] = 1
    celestial = fits.Header.fromstring(
        metadata.celestial_wcs.fits_header, sep="\n"
    )
    for card in celestial.cards:
        if card.keyword not in {"", "COMMENT", "HISTORY", "END", "WCSAXES"}:
            header[card.keyword] = (card.value, card.comment)
    frequency_hz = metadata.reference_frequency_hz
    header["CTYPE3"] = "STOKES"
    header["CRVAL3"] = 1.0
    header["CDELT3"] = 1.0
    header["CRPIX3"] = 1.0
    header["CUNIT3"] = ""
    header["CTYPE4"] = "FREQ"
    header["CRVAL4"] = frequency_hz
    header["CDELT4"] = 3e8
    header["CRPIX4"] = 1.0
    header["CUNIT4"] = "Hz"
    header["RESTFRQ"] = frequency_hz
    header["SPECSYS"] = "TOPOCENT"
    return header


def _write_island_mask(
    published_mask: Path, metadata: ImageMetadata, destination: Path
) -> None:
    """Write the published mask as PyBDSF exports its island mask.

    PyBDSF writes ``float32`` ones inside islands and zeros elsewhere on
    four axes, and LSMTool reads that layout: ``filter_sources`` clips
    ``data[0, 0]`` to the sector polygon in place and groups the sky model
    through casacore, which reads the first plane of the first two axes.
    The plane is streamed by row blocks, so no image-sized array is held.
    """
    temporary = _temporary(destination)
    try:
        with fits.open(published_mask, memmap=True) as published:
            plane = published[0].data
            stream = fits.StreamingHDU(
                temporary, _island_mask_header(metadata)
            )
            try:
                for start in range(0, metadata.shape_yx[0], _BLOCK_ROWS):
                    stream.write(
                        np.asarray(
                            plane[start : start + _BLOCK_ROWS],
                            dtype=np.float32,
                        )
                    )
            finally:
                stream.close()
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
