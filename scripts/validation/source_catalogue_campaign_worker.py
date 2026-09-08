"""Bounded R6 finder and retained-product measurement workers."""

# pyright: reportPrivateUsage=false
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

import numpy as np
from astropy.io import fits

from hebog import public_api
from hebog.config import SourceFinderConfig
from hebog.data_models.source_finding import SourceFinderRequest
from hebog.executors import Executor
from hebog.validation.diagnostic_retention import _atomic_json
from hebog.validation.external_runners import canonical_sha256, file_sha256
from hebog.validation.external_successor_compiler import (
    _mask_metrics,
    measure_continuum_image,
)
from hebog.validation.products import write_comparison_catalogue
from hebog.validation.public_measurement_projection import (
    project_public_measurements,
)
from hebog.validation.source_catalogue_diagnostics import (
    SourceDiagnosticInput,
    compile_source_diagnostics,
)


def _plane_binding(path: Path, root: Path) -> dict[str, Any]:
    """Bind a closed plane without embedding its pixels in a worker result."""
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": file_sha256(path),
        "byte_count": path.stat().st_size,
    }


def _write_plane(
    root: Path,
    name: str,
    plane: np.ndarray,
    header: fits.Header,
) -> dict[str, Any]:
    """Retain a lossless, compressed FITS diagnostic, never a new store."""
    path = root / f"{name}.fits.gz"
    values = plane.astype(np.uint8) if plane.dtype == np.bool_ else plane
    fits.PrimaryHDU(values, header).writeto(path)
    return _plane_binding(path, root)


def capture_current_image(
    input_path: Path,
    output: Path,
    *,
    input_id: str,
    config: SourceFinderConfig,
    executor: Executor,
) -> dict[str, Any]:
    """Preserve exact public science before any truth-based evaluation."""
    output.mkdir(parents=True, exist_ok=False)
    captured: dict[str, Any] = {}
    original = public_api._analyse_image

    def analyse(*args: Any, **kwargs: Any) -> Any:
        scientific = original(*args, **kwargs)
        captured.update(
            scientific=scientific, metadata=args[2], header=kwargs["header"]
        )
        return scientific

    # This validation-only hook observes the actual public execution. Each
    # campaign worker calls it serially; it is always restored on failure.
    public_api._analyse_image = analyse
    try:
        result = public_api.find_sources(
            SourceFinderRequest(input_path, output / "public", input_id),
            config,
            executor,
        )
    finally:
        public_api._analyse_image = original
    scientific = captured["scientific"]
    header = captured["header"]
    catalogue, publication = public_api._public_catalogue(
        scientific,
        captured["metadata"],
        run_id=input_id,
        profile=config.profile,
    )
    if (
        len(catalogue.sources) != result.source_count
        or len(catalogue.gaussian_components)
        != result.gaussian_component_count
        or not np.array_equal(
            publication, cast(np.ndarray, fits.getdata(result.mask.path))
        )
    ):
        raise ValueError("captured science differs from the public bundle")
    terminal = scientific.terminal
    projection = project_public_measurements(
        terminal, catalogue, publication, header
    )
    catalogues = {}
    published_component_ids = {row.identifier for row in projection.components}
    for name, rows in (
        ("all-sources", projection.measured_sources),
        ("all-components", projection.measured_components),
        (
            "published-components",
            tuple(
                row
                for row in projection.measured_components
                if row.identifier in published_component_ids
            ),
        ),
    ):
        path = output / f"{name}.json"
        write_comparison_catalogue(path, rows)
        catalogues[name] = _plane_binding(path, output)
    planes = {
        "publication": _plane_binding(result.mask.path, output),
        "rms": _plane_binding(result.rms.path, output),
        "background": _write_plane(
            output, "background", scientific.background, header
        ),
        "source-union": _write_plane(
            output, "source-union", projection.source_union_labels, header
        ),
    }
    if terminal is not None:
        planes["component-ownership"] = _write_plane(
            output,
            "component-ownership",
            terminal.measurement_component_labels,
            header,
        )
        for name, mask in terminal.support_stages:
            planes[f"stage-{name}"] = _write_plane(
                output, f"stage-{name}", mask, header
            )
    record = {
        "schema_version": 1,
        "input_id": input_id,
        "finder_id": "current-hebog",
        "input_sha256": file_sha256(input_path),
        "configuration_sha256": canonical_sha256(asdict(config)),
        "source_count": result.source_count,
        "component_count": result.gaussian_component_count,
        "sources": [asdict(row) for row in projection.sources],
        "components": [asdict(row) for row in projection.components],
        "measured_sources": [
            asdict(row) for row in projection.measured_sources
        ],
        "measured_components": [
            asdict(row) for row in projection.measured_components
        ],
        "source_association": asdict(terminal.source_association)
        if terminal is not None
        else None,
        "measurement_dispositions": [
            row.model_dump(mode="json") for row in projection.dispositions
        ],
        "public_catalogue": catalogue.model_dump(mode="json"),
        "public_result": result.model_dump(mode="json"),
        "catalogues": catalogues,
        "planes": planes,
    }
    record = json.loads(json.dumps(record, allow_nan=False))
    record["record_sha256"] = canonical_sha256(record)
    _atomic_json(output / "capture.json", record)
    return record


def compile_continuum_record(
    diagnostic: SourceDiagnosticInput,
    publication: np.ndarray,
    specifications: Sequence[Any],
) -> dict[str, Any]:
    """Measure each finder against truth with separate mask/source domains."""
    published_stage = diagnostic.stage_masks.get("publication")
    if (
        publication.dtype != np.bool_
        or publication.shape != diagnostic.source_union_labels.shape
        or published_stage is None
        or not np.array_equal(publication, published_stage)
        or np.any((diagnostic.source_union_labels > 0) & ~publication)
    ):
        raise ValueError("continuum record publication domain changed")
    source_diagnostics = compile_source_diagnostics(diagnostic)
    measured = measure_continuum_image(
        diagnostic.truth,
        diagnostic.sources,
        truth_label_plane=diagnostic.truth_labels,
        candidate_label_plane=diagnostic.source_union_labels,
        beam_fwhm_pixels=diagnostic.beam_fwhm_pixels,
    )
    for metric, value in _mask_metrics(
        diagnostic.truth_labels, publication.astype(np.int64)
    ).items():
        measured[metric]["overall"] = value
    observations = {}
    for specification in specifications:
        value = measured[specification.metric_family][specification.stratum]
        observations[specification.endpoint_id] = {
            "image_key": diagnostic.input_id,
            "values": list(value) if isinstance(value, tuple) else [value],
            "status": "success",
            "reason": None,
        }
    record = {
        "schema_version": 1,
        "lane": "continuum",
        "input_id": diagnostic.input_id,
        "finder_id": diagnostic.finder_id,
        "source_diagnostics": source_diagnostics,
        "continuum_observations": observations,
    }
    record["record_sha256"] = canonical_sha256(record)
    return record
