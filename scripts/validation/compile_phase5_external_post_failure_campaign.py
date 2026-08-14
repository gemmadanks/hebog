#!/usr/bin/env python3
# pyright: reportPrivateUsage=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Compile one sealed post-failure campaign through approved science seams."""

from __future__ import annotations

import argparse
import json
import runpy
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from hebog.validation.external_campaign_compilation import (
    install_continuum_accelerators,
)
from hebog.validation.post_failure_truth import (
    ObservableTruthPlanes,
    ObservableTruthSpecification,
    compile_observable_truth,
)

_ROOT = Path(__file__).parents[2]
_CONFIRMATION_COMPILER_PATH = (
    _ROOT
    / "scripts/validation/compile_phase5_external_confirmation_campaign.py"
)
_REGISTRY_PATH = (
    _ROOT
    / "config/contracts/phase-5-external-post-failure-endpoint-registry.json"
)
_PROTOCOL_PATH = (
    _ROOT / "config/contracts/phase-5-external-post-failure-comparison.json"
)
_DECISION_PATH = (
    _ROOT
    / "config/contracts/phase-5-external-post-failure-execution-decision.json"
)
_CONTINUUM_IMAGE_COUNT = 1600
_CONFIRMATION = runpy.run_path(str(_CONFIRMATION_COMPILER_PATH))
_TERMINAL_JSON_OBJECT = _CONFIRMATION["_TERMINAL_JSON_OBJECT"]
_HELPERS = runpy.run_path(
    str(_ROOT / "scripts/validation/phase5_external_post_failure_protocol.py")
)


class ObservableTruthCompiler:
    """Compile truth and retain deterministic support evidence per image."""

    def __init__(self, terminal_globals: dict[str, Any]) -> None:
        self._terminal = terminal_globals
        self.records: list[dict[str, object]] = []

    def __call__(
        self,
        dataset: Any,
        recipe: Any,
        valid_pixels: Any,
        review: Any,
    ) -> tuple[Any, Any]:
        """Adapt reviewed generated truth into the observable-domain kernel."""
        generated = self._terminal["_build_generated_truth"](dataset, review)
        strata_by_group: dict[str, set[str]] = defaultdict(set)
        for stratum in dataset.multiscale_group_strata:
            for identifier in stratum.group_identifiers:
                strata_by_group[identifier].add(stratum.identifier)
        specifications = tuple(
            ObservableTruthSpecification(
                identifier=group.identifier,
                catalogue_role=group.catalogue_role,
                strata=tuple(sorted(strata_by_group[group.identifier])),
            )
            for group in dataset.multiscale_truth_groups
        )
        planes = {
            item.identifier: ObservableTruthPlanes(
                signal_jy_per_beam=item.signal_jy_per_beam,
                declared_support=item.detection_mask,
            )
            for item in generated
        }
        compilation = compile_observable_truth(
            specifications,
            planes,
            valid_pixels,
            beam_major_fwhm_pixels=dataset.beam.major_fwhm_pixels,
            beam_minor_fwhm_pixels=dataset.beam.minor_fwhm_pixels,
        )
        self.records.append(
            {
                "dataset_identifier": dataset.identifier,
                "seed": recipe.seed,
                "groups": [asdict(item) for item in compilation.supports],
            }
        )
        return compilation.objects, compilation.label_plane


def _post_failure_json_object(path: Path) -> dict[str, Any]:
    """Return prospective views used by the closed verifier."""
    if path.resolve() == _PROTOCOL_PATH.resolve():
        protocol = _HELPERS["load_post_failure_protocol"](path)
        return cast(dict[str, Any], protocol.model_dump(mode="json"))
    document = cast(dict[str, Any], _TERMINAL_JSON_OBJECT(path))
    if path.resolve() != _DECISION_PATH.resolve():
        return document
    decision = _HELPERS["load_post_failure_execution_decision"](path)
    if decision.execution_authorized is not True:
        raise ValueError("post-failure execution decision is not approved")
    return {
        **document,
        "decision_id": "phase-5-external-execution-decision",
        "decision": "authorize-one-terminal-external-comparison",
    }


def load_post_failure_composition(
    registry_path: Path,
    compiler_path: Path,
) -> dict[str, Any]:
    """Validate prospective composition and unchanged endpoint policy."""
    registry = _HELPERS["load_post_failure_endpoint_registry"](registry_path)
    expected = (
        "scripts/validation/compile_phase5_external_post_failure_campaign.py"
    )
    if registry["compiler_path"] != expected:
        raise ValueError("post-failure compiler registry path changed")
    if registry["compiler_sha256"] != _HELPERS["file_sha256"](compiler_path):
        raise ValueError("post-failure compiler registry checksum changed")
    return cast(dict[str, Any], registry)


def _configured_terminal() -> dict[str, Any]:
    """Install approved science, population, and result-neutral seams."""
    terminal = _CONFIRMATION["_configured_terminal"]()
    globals_ = terminal["compile_terminal_analysis"].__globals__
    globals_["_json_object"] = _post_failure_json_object
    globals_["load_endpoint_registry"] = load_post_failure_composition
    globals_["CampaignRequest"] = _HELPERS[
        "post_failure_campaign_request_model"
    ](globals_["CampaignRequest"])
    globals_["TerminalCampaignResult"] = _HELPERS[
        "post_failure_terminal_result_model"
    ](globals_["TerminalCampaignResult"])
    truth_compiler = ObservableTruthCompiler(globals_)
    globals_["_truth_objects"] = truth_compiler
    install_continuum_accelerators(globals_)
    terminal["_post_failure_truth_compiler"] = truth_compiler
    return cast(dict[str, Any], terminal)


def compile_post_failure_analysis(
    campaign_path: Path,
    registry_path: Path,
    compiler_path: Path,
) -> dict[str, Any]:
    """Compile one complete fresh campaign without reopening history."""
    terminal = _configured_terminal()
    analysis = terminal["compile_terminal_analysis"](
        campaign_path,
        registry_path,
        compiler_path,
    )
    truth_compiler = cast(
        ObservableTruthCompiler,
        terminal["_post_failure_truth_compiler"],
    )
    records = truth_compiler.records
    identities = tuple(
        (item["dataset_identifier"], item["seed"]) for item in records
    )
    if len(records) != _CONTINUUM_IMAGE_COUNT or len(set(identities)) != len(
        identities
    ):
        raise ValueError("observable truth support population is incomplete")
    analysis["analysis_id"] = "phase-5-external-post-failure-terminal-science"
    analysis["closed_campaign_reuse_authorized"] = False
    analysis["observable_truth_support"] = records
    analysis["observable_measurement_sha256"] = _HELPERS["file_sha256"](
        _ROOT / "src/hebog/validation/observable_truth.py"
    )
    analysis["observable_compiler_sha256"] = _HELPERS["file_sha256"](
        _ROOT / "src/hebog/validation/post_failure_truth.py"
    )
    analysis["successor_science_kernel_sha256"] = _HELPERS["file_sha256"](
        _ROOT / "src/hebog/validation/external_successor_compiler.py"
    )
    analysis["compiler_accelerator_sha256"] = _HELPERS["file_sha256"](
        _ROOT / "src/hebog/validation/external_campaign_compilation.py"
    )
    return cast(dict[str, Any], analysis)


def _canonical_json_bytes(value: object) -> bytes:
    """Serialize one finite deterministic evidence record."""
    return (
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _parse_args() -> argparse.Namespace:
    """Parse sealed campaign, registry, and write-once output paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", required=True, type=Path)
    parser.add_argument("--registry", type=Path, default=_REGISTRY_PATH)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    """Compile the post-failure campaign exactly once."""
    arguments = _parse_args()
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite post-failure analysis: {arguments.output}"
        )
    analysis = compile_post_failure_analysis(
        arguments.campaign,
        arguments.registry,
        Path(__file__),
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open("xb") as output:
        output.write(_canonical_json_bytes(analysis))


if __name__ == "__main__":
    main()
