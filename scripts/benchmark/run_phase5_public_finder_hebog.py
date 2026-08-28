#!/usr/bin/env python3
# pyright: reportMissingTypeStubs=false
# pyright: reportPrivateUsage=false
# pyright: reportUnknownMemberType=false
"""Run one authorized Hebog public-comparison case."""

from __future__ import annotations

import argparse
import runpy
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from typing import Any, cast

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

from hebog.algorithms.multiscale import BeamShapePixels
from hebog.algorithms.partitioning import plan_image_partitions
from hebog.data_models import ImageBounds
from hebog.executors import SerialExecutor
from hebog.io import FitsImageSource, ZarrProductSink
from hebog.stages.detection import run_detection_stage
from hebog.validation.contracts import load_phase_five_corrective_a_review
from hebog.validation.hebog_campaign import (
    _ArrayImageSource,
    phase_five_corrected_candidate_configs,
)
from hebog.validation.post_correction_recovery import (
    build_post_correction_continuum_products,
    post_correction_candidate_configuration_sha256,
)
from hebog.validation.products import (
    load_fits_plane,
    write_comparison_catalogue,
)

_ROOT = Path(__file__).parents[2]
_PROTOCOL = runpy.run_path(
    str(_ROOT / "scripts/validation/phase5_public_finder_protocol.py")
)
_BASE_REVIEW = _ROOT / "config/contracts/phase-5-corrective-a-review.json"


def _estimate_background_rms(
    image: np.ndarray,
    output: Path,
    *,
    generation_id: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Run only the qualified candidate-owned background/RMS stage."""
    source = _ArrayImageSource(image)
    manifest = plan_image_partitions(
        image_shape_yx=tuple(image.shape),
        tile_core_shape_yx=(128, 128),
        halo_yx=(0, 0),
    )
    sink = ZarrProductSink(
        output / "products.zarr",
        manifest,
        generation_id=generation_id,
    )
    run_detection_stage(
        source,
        manifest,
        phase_five_corrected_candidate_configs()[0],
        SerialExecutor(),
        sink,
    )
    bounds = ImageBounds(0, image.shape[0], 0, image.shape[1])
    return (
        np.asarray(
            sink.read_completed_window("background", bounds),
            dtype=np.float64,
        ),
        np.asarray(
            sink.read_completed_window("rms", bounds),
            dtype=np.float64,
        ),
    )


def _beam_pixels(header: fits.Header) -> BeamShapePixels:
    """Translate standard FITS beam cards to qualified pixel units."""
    try:
        major = float(cast(Any, header["BMAJ"])) / abs(
            float(cast(Any, header["CDELT2"]))
        )
        minor = float(cast(Any, header["BMIN"])) / abs(
            float(cast(Any, header["CDELT1"]))
        )
        angle = float(cast(Any, header.get("BPA", 0.0)) or 0.0)
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        raise ValueError(
            "public FITS beam or pixel scale is invalid"
        ) from error
    # Celestial WCS serialization can round equal axis scales in opposite
    # directions. Preserve an exactly circular sky beam without allowing a
    # materially inverted FITS beam to pass the domain invariant.
    if minor > major and minor - major <= 1e-12 * max(major, minor):
        major = minor = (major + minor) / 2.0
    return BeamShapePixels(major, minor, angle)


def _core_catalogue(
    catalogue: tuple[Any, ...],
    header: fits.Header,
    core: ImageBounds,
) -> tuple[Any, ...]:
    """Admit candidates whose fitted centroid lies in the half-open core."""
    celestial = WCS(header, relax=True).celestial
    retained: list[Any] = []
    for source in catalogue:
        x_pixel, y_pixel = cast(
            tuple[float, float],
            celestial.all_world2pix(
                source.right_ascension_degrees,
                source.declination_degrees,
                0,
            ),
        )
        if (
            core.x_start <= float(x_pixel) < core.x_stop
            and core.y_start <= float(y_pixel) < core.y_stop
        ):
            retained.append(source)
    return tuple(retained)


def _core_header(header: fits.Header, core: ImageBounds) -> fits.Header:
    """Shift the haloed input WCS onto the selected output core."""
    shifted = header.copy()
    shifted["CRPIX1"] = float(cast(Any, shifted["CRPIX1"])) - core.x_start
    shifted["CRPIX2"] = float(cast(Any, shifted["CRPIX2"])) - core.y_start
    return shifted


def _write_plane(
    path: Path,
    values: np.ndarray,
    header: fits.Header,
) -> None:
    """Write one core plane with the input's singleton leading axes."""
    fits.PrimaryHDU(
        data=values[np.newaxis, np.newaxis, :, :],
        header=header,
    ).writeto(path)


def _build_public_bundle(  # noqa: PLR0913
    *,
    input_path: Path,
    output: Path,
    work_directory: Path,
    case_id: str,
    core: ImageBounds | None,
    configuration_sha256: str,
) -> dict[str, object]:
    """Build one complete bundle inside an unpublished private directory."""
    observed_configuration = post_correction_candidate_configuration_sha256(
        _BASE_REVIEW
    )
    if observed_configuration != configuration_sha256:
        raise ValueError("qualified Hebog configuration checksum changed")
    metadata = FitsImageSource(input_path).metadata()
    image = load_fits_plane(input_path)
    if tuple(image.shape) != metadata.shape_yx:
        raise ValueError("public FITS pixels and metadata shapes differ")
    output.mkdir(parents=True)
    started = monotonic()
    background, rms = _estimate_background_rms(
        image,
        work_directory,
        generation_id=case_id,
    )
    header = cast(fits.Header, fits.getheader(input_path))
    review = load_phase_five_corrective_a_review(_BASE_REVIEW)
    products = build_post_correction_continuum_products(
        image,
        background,
        rms,
        header,
        beam=_beam_pixels(header),
        review=review,
    )
    selected_core = core or ImageBounds(
        y_start=0,
        y_stop=metadata.shape_yx[0],
        x_start=0,
        x_stop=metadata.shape_yx[1],
    )
    selected_core.require_inside(metadata.shape_yx)
    slices = (
        slice(selected_core.y_start, selected_core.y_stop),
        slice(selected_core.x_start, selected_core.x_stop),
    )
    core_header = _core_header(header, selected_core)
    catalogue_path = output / "segment_catalogue.json"
    labels_path = output / "segment_labels.fits"
    mask_path = output / "segment_mask.fits"
    background_path = output / "background.fits"
    rms_path = output / "rms.fits"
    write_comparison_catalogue(
        catalogue_path,
        _core_catalogue(products.catalogue, header, selected_core),
    )
    _write_plane(
        labels_path,
        np.asarray(
            products.detection.component_labels[slices], dtype=np.int32
        ),
        core_header,
    )
    _write_plane(
        mask_path,
        np.asarray(products.detection.retained_mask[slices], dtype=np.uint8),
        core_header,
    )
    _write_plane(
        background_path,
        np.asarray(background[slices], dtype=np.float64),
        core_header,
    )
    _write_plane(
        rms_path,
        np.asarray(rms[slices], dtype=np.float64),
        core_header,
    )
    artifacts = {
        "background-fits": background_path,
        "rms-fits": rms_path,
        "segment-catalogue-json": catalogue_path,
        "segment-labels-fits": labels_path,
        "segment-mask-fits": mask_path,
    }
    result: dict[str, object] = {
        "schema_version": 1,
        "result_id": f"phase-5-public-finder-{case_id}",
        "status": "success",
        "case_id": case_id,
        "configuration_sha256": observed_configuration,
        "input_sha256": _PROTOCOL["file_sha256"](input_path),
        "core_bounds_yx_half_open": [
            selected_core.y_start,
            selected_core.y_stop,
            selected_core.x_start,
            selected_core.x_stop,
        ],
        "elapsed_seconds": monotonic() - started,
        "artifacts": {
            role: {
                "path": path.name,
                "sha256": _PROTOCOL["file_sha256"](path),
                "byte_size": path.stat().st_size,
            }
            for role, path in sorted(artifacts.items())
        },
    }
    _PROTOCOL["write_once_json"](output / "result.json", result)
    return result


def run_public_hebog(
    *,
    input_path: Path,
    output: Path,
    case_id: str,
    core: ImageBounds | None,
    configuration_sha256: str,
) -> dict[str, object]:
    """Produce and atomically publish one restartable public result bundle."""
    if output.exists():
        raise FileExistsError(f"public finder output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix=f".{output.name}.",
        dir=output.parent,
    ) as temporary_directory:
        temporary = Path(temporary_directory)
        unpublished = temporary / "bundle"
        result = _build_public_bundle(
            input_path=input_path,
            output=unpublished,
            work_directory=temporary / "background-work",
            case_id=case_id,
            core=core,
            configuration_sha256=configuration_sha256,
        )
        if output.exists():
            raise FileExistsError(
                f"public finder output appeared during execution: {output}"
            )
        unpublished.rename(output)
    return result


def _parse_core(value: str | None) -> ImageBounds | None:
    """Parse one optional local ``y0,y1,x0,x1`` core."""
    if value is None:
        return None
    try:
        y_start, y_stop, x_start, x_stop = (
            int(item) for item in value.split(",")
        )
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "core bounds must be y0,y1,x0,x1"
        ) from error
    return ImageBounds(y_start, y_stop, x_start, x_stop)


def _parse_args() -> argparse.Namespace:
    """Parse one authorized public Hebog invocation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorization", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--core")
    return parser.parse_args()


def _validate_invocation(
    *,
    protocol: dict[str, Any],
    input_path: Path,
    output: Path,
    case_id: str,
    core: ImageBounds | None,
) -> None:
    """Bind the internal runner to one reviewed campaign case and mount."""
    sdc1_cases = {
        f"sdc1-{item['stratum']}-{item['tile_id']}": item
        for item in protocol["sdc1"]["strata"]
    }
    hydra_cases = {
        item["case_id"]: item for item in protocol["hydra"]["cases"]
    }
    if case_id not in sdc1_cases and case_id not in hydra_cases:
        raise ValueError("public finder case identity changed")
    expected_output = Path("/campaign/results") / case_id
    if output != expected_output:
        raise ValueError("public finder case output path changed")
    if case_id in sdc1_cases:
        halo = int(protocol["sdc1"]["halo_pixels_yx"][0])
        x_start, x_stop, y_start, y_stop = sdc1_cases[case_id][
            "bounds_xy_half_open"
        ]
        expected_input = Path("/campaign/inputs") / case_id / "input.fits"
        expected_core = ImageBounds(
            y_start=halo,
            y_stop=halo + y_stop - y_start,
            x_start=halo,
            x_stop=halo + x_stop - x_start,
        )
        if input_path != expected_input or core != expected_core:
            raise ValueError("public SDC1 invocation changed")
        return
    acquisition = _PROTOCOL["json_object"](
        _ROOT / "benchmark-results/phase-5/public-comparison-acquisition/"
        "acquisition.json"
    )
    filenames = {
        item["identifier"]: item["filename"]
        for item in acquisition["artifacts"]
    }
    expected_input = (
        Path("/repository/benchmark-results/phase-5/")
        / "public-comparison-acquisition/raw"
        / filenames[hydra_cases[case_id]["source_identifier"]]
    )
    if input_path != expected_input or core is not None:
        raise ValueError("public Hydra invocation changed")


def main() -> None:
    """Reject pending authority before reading one public image."""
    arguments = _parse_args()
    decision = _PROTOCOL["load_public_finder_execution_decision"](
        arguments.authorization
    )
    if not decision["execution_authorized"]:
        raise ValueError("public finder execution is not authorized")
    protocol = _PROTOCOL["load_public_finder_protocol"](
        _ROOT / cast(str, decision["protocol"]["path"])
    )
    core = _parse_core(arguments.core)
    _validate_invocation(
        protocol=protocol,
        input_path=arguments.input,
        output=arguments.output,
        case_id=arguments.case_id,
        core=core,
    )
    run_public_hebog(
        input_path=arguments.input,
        output=arguments.output,
        case_id=arguments.case_id,
        core=core,
        configuration_sha256=protocol["candidate"]["configuration_sha256"],
    )


if __name__ == "__main__":
    main()
