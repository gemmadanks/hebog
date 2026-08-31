"""Frozen analytic mechanism lane for terminal-cycle eligibility."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest

from hebog.algorithms.multiscale_association import ScaleDetectionPlane
from hebog.algorithms.source_association import (
    associate_components_by_multiscale_hierarchy,
    build_detection_component_records,
)
from hebog.data_models.multiscale import ScaleDetection
from hebog.data_models.source_association import (
    DetectionComponentRecord,
    SourceAssociationResult,
)
from hebog.validation.terminal_cycle_fail_fast import (
    TerminalCycleCase,
    build_terminal_cycle_fail_fast_record,
    evaluate_terminal_cycle_mechanism_lane,
    load_terminal_cycle_case_manifest,
    observe_terminal_cycle_case,
    publish_terminal_cycle_fail_fast_record,
    write_terminal_cycle_association,
)

_ROOT = Path(__file__).parents[3]
_MANIFEST = (
    _ROOT / "config/contracts/phase-5-terminal-cycle-fail-fast-cases.json"
)


def _plane(
    scale_order: int,
    entries: Sequence[tuple[str, Sequence[tuple[int, int]]]],
    *,
    shape: tuple[int, int],
) -> ScaleDetectionPlane:
    """Build one exact scale-support plane."""
    labels = np.zeros(shape, dtype=np.int32)
    detections: list[ScaleDetection] = []
    for label_value, (identifier, pixels) in enumerate(entries, start=1):
        ordered = tuple(sorted(pixels))
        for pixel in ordered:
            labels[pixel] = label_value
        ys = tuple(pixel[0] for pixel in ordered)
        xs = tuple(pixel[1] for pixel in ordered)
        detections.append(
            ScaleDetection(
                detection_id=identifier,
                parent_island_id=None,
                scale_order=scale_order,
                nominal_scale_beam_fwhm=float(2 ** (scale_order - 1)),
                support_pixel_count=len(ordered),
                valid_support_fraction=1.0,
                bounds_yx=(min(ys), max(ys) + 1, min(xs), max(xs) + 1),
                canonical_pixel_yx=(ys[0], xs[0]),
                peak_response_jy_per_beam=1.0,
                peak_signal_to_noise=5.0,
                touches_image_edge=False,
            )
        )
    return ScaleDetectionPlane(
        scale_order=scale_order,
        component_labels=labels,
        detections=tuple(detections),
    )


def _components(
    pixels: Sequence[tuple[int, int]],
    *,
    shape: tuple[int, int],
    variant: int,
) -> tuple[npt.NDArray[np.int32], tuple[DetectionComponentRecord, ...]]:
    """Build direct records with intentionally irrelevant label identities."""
    labels = np.zeros(shape, dtype=np.int32)
    label_orders = (
        (1, 2, 3, 4, 5, 6),
        (9, 2, 17, 4, 31, 7),
        (31, 7, 22, 13, 2, 41),
        (6, 5, 4, 3, 2, 1),
    )
    for value, pixel in zip(
        label_orders[variant % len(label_orders)], pixels, strict=False
    ):
        labels[pixel] = value
    records = build_detection_component_records(
        labels,
        np.asarray(labels > 0, dtype=np.float64),
        np.ones(shape, dtype=np.bool_),
    )
    if variant % 2:
        records = tuple(reversed(records))
    return labels, records


def _associate(
    labels: npt.NDArray[np.int32],
    records: tuple[DetectionComponentRecord, ...],
    planes: Sequence[ScaleDetectionPlane],
    *,
    support: npt.NDArray[np.bool_] | None = None,
) -> SourceAssociationResult:
    """Call the exact production association kernel."""
    return associate_components_by_multiscale_hierarchy(
        records,
        labels,
        tuple(planes),
        np.ones(labels.shape, dtype=np.bool_),
        significant_multiscale_support=support,
    )


def _unseeded(case: TerminalCycleCase) -> SourceAssociationResult:
    """Build accepted or rejected unseeded terminal geometry."""
    shape = (41, 41)
    pixels = ((10, 10), (10, 30), (30, 10), (30, 30))
    labels, records = _components(
        pixels[:3], shape=shape, variant=case.variant
    )
    persistent = case.family == "persistent-unseeded-geometry"
    preceding_pixels = pixels if persistent else pixels[:3]
    preceding = _plane(
        2,
        tuple(
            (f"preceding-{index}", (pixel,))
            for index, pixel in enumerate(preceding_pixels)
        ),
        shape=shape,
    )
    terminal = _plane(
        3,
        tuple(
            (f"terminal-{index}", (pixel,))
            for index, pixel in enumerate(pixels)
        ),
        shape=shape,
    )
    planes = (preceding, terminal)
    if case.variant % 2:
        planes = tuple(reversed(planes))
    return _associate(labels, records, planes)


def _bridge_pair_or_path(case: TerminalCycleCase) -> SourceAssociationResult:
    """Build conservative terminal bridge, pair, or path controls."""
    shape = (31, 31)
    if case.family == "terminal-pair":
        pixels = ((15, 8), (15, 22))
    elif case.family == "terminal-path":
        pixels = ((10, 4), (10, 14), (10, 24), (10, 34))
        shape = (21, 39)
    else:
        pixels = ((15, 6), (15, 24))
    labels, records = _components(pixels, shape=shape, variant=case.variant)
    if case.family == "terminal-bridge":
        fine = _plane(
            1,
            tuple(
                (f"bridge-fine-{index}", (pixel,))
                for index, pixel in enumerate(pixels)
            ),
            shape=shape,
        )
        terminal = _plane(
            3,
            (("bridge-terminal", tuple((15, x) for x in range(6, 25))),),
            shape=shape,
        )
        return _associate(labels, records, (fine, terminal))
    planes = tuple(
        _plane(
            scale,
            tuple(
                (f"control-{scale}-{index}", (pixel,))
                for index, pixel in enumerate(pixels)
            ),
            shape=shape,
        )
        for scale in ((2,) if case.family == "terminal-path" else (2, 3))
    )
    return _associate(labels, records, planes)


def _displaced(case: TerminalCycleCase) -> SourceAssociationResult:
    """Build disconnected or ambiguous displaced-child controls."""
    shape = (49, 49)
    terminal_pixels = ((10, 10), (10, 34), (34, 10), (34, 34))
    child_pixels = ((9, 9), (9, 35), (35, 9), (35, 35))
    labels, records = _components(
        terminal_pixels, shape=shape, variant=case.variant
    )
    children: list[tuple[str, Sequence[tuple[int, int]]]] = [
        (f"child-{index}", (pixel,))
        for index, pixel in enumerate(child_pixels)
    ]
    if case.family == "ambiguous-child":
        children.append(("child-ambiguous", ((9, 11),)))
    preceding = _plane(2, children, shape=shape)
    terminal = _plane(
        3,
        tuple(
            (f"terminal-{index}", (pixel,))
            for index, pixel in enumerate(terminal_pixels)
        ),
        shape=shape,
    )
    support = np.zeros(shape, dtype=np.bool_)
    for index, (child, parent) in enumerate(
        zip(child_pixels, terminal_pixels, strict=True)
    ):
        if case.family == "disconnected-support" and index == 0:
            continue
        support[
            min(child[0], parent[0]) : max(child[0], parent[0]) + 1,
            min(child[1], parent[1]) : max(child[1], parent[1]) + 1,
        ] = True
    if case.family == "ambiguous-child":
        support[9:11, 9:12] = True
    return _associate(labels, records, (preceding, terminal), support=support)


def _partial_group(case: TerminalCycleCase) -> SourceAssociationResult:
    """Build a three-member group that a terminal cycle may not absorb."""
    shape = (61, 61)
    terminal_pixels = ((20, 20), (20, 40), (40, 20), (40, 40))
    grouped = ((20, 20), (20, 16), (16, 20))
    labels, records = _components(
        (*terminal_pixels, *grouped[1:]), shape=shape, variant=case.variant
    )
    fine = _plane(
        1,
        tuple(
            (f"existing-fine-{index}", (pixel,))
            for index, pixel in enumerate(grouped)
        ),
        shape=shape,
    )
    preceding_pixels = (
        grouped[0],
        grouped[1],
        grouped[2],
        (19, 41),
        (41, 19),
        (41, 41),
    )
    preceding = _plane(
        2,
        tuple(
            (f"conflicting-child-{index}", (pixel,))
            for index, pixel in enumerate(preceding_pixels)
        ),
        shape=shape,
    )
    terminal = _plane(
        3,
        tuple(
            (f"conflicting-terminal-{index}", (pixel,))
            for index, pixel in enumerate(terminal_pixels)
        ),
        shape=shape,
    )
    support = np.zeros(shape, dtype=np.bool_)
    support[16:21, 16:21] = True
    for child, parent in zip(
        preceding_pixels[3:], terminal_pixels[1:], strict=True
    ):
        support[
            min(child[0], parent[0]) : max(child[0], parent[0]) + 1,
            min(child[1], parent[1]) : max(child[1], parent[1]) + 1,
        ] = True
    return _associate(
        labels, records, (fine, preceding, terminal), support=support
    )


def _run(case: TerminalCycleCase) -> SourceAssociationResult:
    """Dispatch one frozen analytic case to its production-kernel fixture."""
    if case.family.endswith("unseeded-geometry"):
        return _unseeded(case)
    if case.family in {"terminal-bridge", "terminal-pair", "terminal-path"}:
        return _bridge_pair_or_path(case)
    if case.family in {"disconnected-support", "ambiguous-child"}:
        return _displaced(case)
    return _partial_group(case)


def test_frozen_mechanism_lane_activates_and_rejects_all_controls() -> None:
    """All 25 analytic cases pass the exact bounded mechanism contract."""
    manifest = load_terminal_cycle_case_manifest(_MANIFEST)
    observations = tuple(
        observe_terminal_cycle_case(case, _run(case))
        for case in manifest.cases
    )

    evidence = evaluate_terminal_cycle_mechanism_lane(manifest, observations)

    assert evidence == {
        "schema_version": 1,
        "lane_id": "phase-5-terminal-cycle-mechanism-activation",
        "case_count": 25,
        "family_count": 8,
        "positive_activation_count": 4,
        "pre_guard_rejection_count": 4,
        "all_controls_pass": True,
        "promotion_evidence": False,
    }


def test_manifest_rejects_population_and_family_drift(tmp_path: Path) -> None:
    """The analytic population cannot silently shrink or change families."""
    document = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    document["cases"] = document["cases"][:19]
    path = tmp_path / "too-small.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="policy changed"):
        load_terminal_cycle_case_manifest(path)

    document = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    document["cases"][0]["family"] = "unknown-family"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="families changed"):
        load_terminal_cycle_case_manifest(path)


def test_mechanism_lane_rejects_missing_or_changed_observation() -> None:
    """Case omission and one changed scientific result both fail closed."""
    manifest = load_terminal_cycle_case_manifest(_MANIFEST)
    observations = tuple(
        observe_terminal_cycle_case(case, _run(case))
        for case in manifest.cases
    )
    with pytest.raises(ValueError, match="observations differ"):
        evaluate_terminal_cycle_mechanism_lane(manifest, observations[:-1])
    changed = (
        replace(observations[0], maximum_membership_size=1),
        *observations[1:],
    )
    with pytest.raises(ValueError, match="expectation failed"):
        evaluate_terminal_cycle_mechanism_lane(manifest, changed)


def test_record_builder_and_writers_fail_closed(tmp_path: Path) -> None:
    """Incomplete e2e evidence and overwrite attempts cannot publish."""
    manifest = load_terminal_cycle_case_manifest(_MANIFEST)
    association = _run(manifest.cases[0])
    sidecar = tmp_path / "association.json"
    write_terminal_cycle_association(sidecar, association)
    with pytest.raises(FileExistsError):
        write_terminal_cycle_association(sidecar, association)

    mechanism: dict[str, object] = {
        "schema_version": 1,
        "lane_id": "phase-5-terminal-cycle-mechanism-activation",
        "case_count": 25,
        "family_count": 8,
        "positive_activation_count": 4,
        "pre_guard_rejection_count": 4,
        "all_controls_pass": True,
        "promotion_evidence": False,
    }
    provenance = {
        "producer_sha256": "a" * 64,
        "writer_sha256": "b" * 64,
        "compiler_sha256": "c" * 64,
        "evaluator_sha256": "d" * 64,
    }
    with pytest.raises(ValueError, match="mechanism lane"):
        build_terminal_cycle_fail_fast_record(
            mechanism={**mechanism, "positive_activation_count": 0},
            association_paths=(sidecar,),
            compact_sha256_before="a" * 64,
            compact_sha256_after="a" * 64,
            compiled_endpoint_values={"endpoint": (1.0,)},
            provenance=provenance,
        )
    with pytest.raises(ValueError, match="compact output changed"):
        build_terminal_cycle_fail_fast_record(
            mechanism=mechanism,
            association_paths=(sidecar,),
            compact_sha256_before="a" * 64,
            compact_sha256_after="b" * 64,
            compiled_endpoint_values={"endpoint": (1.0,)},
            provenance=provenance,
        )
    with pytest.raises(ValueError, match="endpoints differ"):
        build_terminal_cycle_fail_fast_record(
            mechanism=mechanism,
            association_paths=(sidecar,),
            compact_sha256_before="a" * 64,
            compact_sha256_after="a" * 64,
            compiled_endpoint_values={},
            provenance=provenance,
        )
    endpoints = {
        "completeness-overall": (1.0,),
        "mask-precision-overall": (1.0,),
    }
    with pytest.raises(ValueError, match="provenance is incomplete"):
        build_terminal_cycle_fail_fast_record(
            mechanism=mechanism,
            association_paths=(sidecar,),
            compact_sha256_before="a" * 64,
            compact_sha256_after="a" * 64,
            compiled_endpoint_values=endpoints,
            provenance={**provenance, "writer_sha256": "not-a-digest"},
        )
    with pytest.raises(ValueError, match="association evidence is empty"):
        build_terminal_cycle_fail_fast_record(
            mechanism=mechanism,
            association_paths=(),
            compact_sha256_before="a" * 64,
            compact_sha256_after="a" * 64,
            compiled_endpoint_values=endpoints,
            provenance=provenance,
        )
    output = tmp_path / "not-publishable.json"
    with pytest.raises(ValueError, match="not publishable"):
        publish_terminal_cycle_fail_fast_record(output, {"status": "fail"})
    assert not output.exists()
