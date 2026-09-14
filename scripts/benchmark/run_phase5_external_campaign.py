#!/usr/bin/env python3
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownMemberType=false
"""Run the authorized Phase 5 comparison as one sealed terminal campaign.

The launcher performs a no-write preflight before it creates a hidden durable
staging directory. Infrastructure interruption may resume only that exact
request. Finder results remain private until every frozen leg is present and
checksum-verified, at which point the staging directory is renamed atomically
to the requested campaign path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Literal, Self, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hebog.validation.contracts import (
    PhaseFiveExternalComparisonProtocol,
    PhaseFiveExternalExecutionDecision,
    load_phase_five_external_comparison_protocol,
    load_phase_five_external_execution_decision,
)
from hebog.validation.datasets import (
    iter_dataset_recipes,
    load_dataset_manifest,
    recipe_sha256,
)
from hebog.validation.external_runners import (
    ExternalFinderId,
    ExternalRunMode,
    file_sha256,
    load_external_run_result,
    source_tree_sha256,
)
from hebog.validation.materialization import load_external_input_bundle

_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_IMAGE_DIGEST_PATTERN = r"^sha256:[0-9a-f]{64}$"
_PYBDSF_NCORES: Literal[4] = 4
_IMAGE_COUNT: Literal[1400] = 1400
_RUN_COUNT: Literal[7000] = 7000
_FINDER_ORDER: tuple[ExternalFinderId, ...] = (
    "hebog",
    "released-pybdsf",
    "pinned-pybdsf-master",
    "aegean",
)
_RUNNER_PATHS: dict[ExternalFinderId, str] = {
    "hebog": "scripts/benchmark/run_phase5_external_hebog.py",
    "released-pybdsf": "scripts/benchmark/run_phase5_external_pybdsf.py",
    "pinned-pybdsf-master": (
        "scripts/benchmark/run_phase5_external_pybdsf.py"
    ),
    "aegean": "scripts/benchmark/run_phase5_external_aegean.py",
}
_MATERIALIZE_CODE = (
    "import sys; from pathlib import Path; "
    "from hebog.validation.materialization import "
    "materialize_external_realization; "
    "materialize_external_realization(Path(sys.argv[1]), Path(sys.argv[2]), "
    "sys.argv[3], int(sys.argv[4]), Path(sys.argv[5]))"
)


class _CampaignModel(BaseModel):
    """Strict immutable base for the terminal campaign records."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class CampaignLeg(_CampaignModel):
    """One finder and mode applicable to a frozen population lane."""

    finder_id: ExternalFinderId
    mode: ExternalRunMode


class CampaignContainerImage(_CampaignModel):
    """One locally resolved immutable container used by the campaign."""

    finder_id: ExternalFinderId
    image: str = Field(min_length=1)
    image_id: str = Field(pattern=_SHA256_PATTERN)
    digest: str = Field(pattern=_IMAGE_DIGEST_PATTERN)
    operating_system: str = Field(min_length=1)
    architecture: str = Field(min_length=1)


class CampaignInputRequest(_CampaignModel):
    """One exact common realization to materialize inside Hebog's image."""

    input_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    lane: Literal["continuum", "compact-blend"]
    manifest_relative_path: str = Field(
        pattern=r"^config/datasets/[a-z0-9-]+\.json$"
    )
    manifest_sha256: str = Field(pattern=_SHA256_PATTERN)
    dataset_identifier: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    seed: int = Field(ge=0)
    recipe_sha256: str = Field(pattern=_SHA256_PATTERN)
    relative_directory: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_path(self) -> Self:
        """Keep the input in its exact private campaign subtree."""
        _require_relative_path(self.relative_directory, product="input")
        expected = (
            f"inputs/{self.lane}/{self.dataset_identifier}/seed-{self.seed}"
        )
        if self.relative_directory != expected:
            raise ValueError("campaign input path is not canonical")
        return self


class CampaignRunRequest(_CampaignModel):
    """One exact isolated finder invocation within the terminal request."""

    run_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    input_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    lane: Literal["continuum", "compact-blend"]
    finder_id: ExternalFinderId
    mode: ExternalRunMode
    relative_directory: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_path(self) -> Self:
        """Keep each result in a stable finder/mode subtree."""
        _require_relative_path(self.relative_directory, product="run")
        return self


class CampaignRequest(_CampaignModel):
    """Complete deterministic request written before the one-look opens."""

    schema_version: Literal[1]
    campaign_id: Literal["phase-5-external-source-finder-comparison"]
    status: Literal["authorized-unopened-request"]
    protocol_sha256: str = Field(pattern=_SHA256_PATTERN)
    execution_decision_sha256: str = Field(pattern=_SHA256_PATTERN)
    candidate_review_sha256: str = Field(pattern=_SHA256_PATTERN)
    implementation_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_tree_sha256: str = Field(pattern=_SHA256_PATTERN)
    launcher_sha256: str = Field(pattern=_SHA256_PATTERN)
    materialization_runtime: Literal["approved-hebog-container"]
    execution_concurrency: Literal[1]
    pybdsf_ncores: Literal[4]
    containers: tuple[
        CampaignContainerImage,
        CampaignContainerImage,
        CampaignContainerImage,
        CampaignContainerImage,
    ]
    image_count: Literal[1400]
    run_count: Literal[7000]
    inputs: tuple[CampaignInputRequest, ...]
    runs: tuple[CampaignRunRequest, ...]
    one_look_opened: Literal[False]
    step_three_authorized: Literal[False]
    optimization_authorized: Literal[False]
    qualification_opened: Literal[False]

    @model_validator(mode="after")
    def validate_complete_matrix(self) -> Self:
        """Require the entire frozen population and applicable leg matrix."""
        if tuple(item.finder_id for item in self.containers) != _FINDER_ORDER:
            raise ValueError("campaign containers must be canonical")
        if len(self.inputs) != self.image_count:
            raise ValueError("campaign input count differs from declaration")
        if len(self.runs) != self.run_count:
            raise ValueError("campaign run count differs from declaration")
        _require_unique(
            (item.input_id for item in self.inputs),
            product="campaign input IDs",
        )
        _require_unique(
            (item.relative_directory for item in self.inputs),
            product="campaign input paths",
        )
        _require_unique(
            (item.run_id for item in self.runs),
            product="campaign run IDs",
        )
        _require_unique(
            (item.relative_directory for item in self.runs),
            product="campaign run paths",
        )
        inputs = {item.input_id: item for item in self.inputs}
        runs_by_input: dict[str, list[CampaignRunRequest]] = defaultdict(list)
        for run in self.runs:
            if run.input_id not in inputs:
                raise ValueError("campaign run references an unknown input")
            campaign_input = inputs[run.input_id]
            if run.lane != campaign_input.lane:
                raise ValueError("campaign run lane differs from input")
            expected_path = (
                f"results/{run.lane}/{campaign_input.dataset_identifier}/"
                f"seed-{campaign_input.seed}/{run.finder_id}/{run.mode}"
            )
            if run.relative_directory != expected_path:
                raise ValueError("campaign run path is not canonical")
            runs_by_input[run.input_id].append(run)
        for campaign_input in self.inputs:
            observed = tuple(
                (run.finder_id, run.mode)
                for run in runs_by_input[campaign_input.input_id]
            )
            expected = tuple(
                (leg.finder_id, leg.mode)
                for leg in frozen_leg_matrix(campaign_input.lane)
            )
            if observed != expected:
                raise ValueError("campaign input leg matrix is incomplete")
        return self

    def canonical_json_bytes(self) -> bytes:
        """Serialize the unopened request deterministically."""
        return _canonical_json_bytes(self.model_dump(mode="json"))


class CampaignOpenState(_CampaignModel):
    """Timestamp proving when the approved one-look execution began."""

    schema_version: Literal[1]
    status: Literal["private-staging-open"]
    request_sha256: str = Field(pattern=_SHA256_PATTERN)
    execution_decision_sha256: str = Field(pattern=_SHA256_PATTERN)
    opened_at: datetime

    @model_validator(mode="after")
    def validate_time(self) -> Self:
        """Require an unambiguous UTC-capable opening timestamp."""
        if self.opened_at.tzinfo is None or self.opened_at.utcoffset() is None:
            raise ValueError("campaign opening time must include a timezone")
        return self

    def canonical_json_bytes(self) -> bytes:
        """Serialize the private opening record deterministically."""
        return _canonical_json_bytes(self.model_dump(mode="json"))


class CampaignRunSummary(_CampaignModel):
    """One verified raw result retained in the terminal campaign."""

    run_id: str
    input_id: str
    finder_id: ExternalFinderId
    mode: ExternalRunMode
    status: Literal["success", "failure"]
    result_relative_path: str
    result_sha256: str = Field(pattern=_SHA256_PATTERN)


class TerminalCampaignResult(_CampaignModel):
    """Sealed complete raw campaign published before scientific evaluation."""

    schema_version: Literal[1]
    campaign_id: Literal["phase-5-external-source-finder-comparison"]
    status: Literal["terminal-raw-results-sealed"]
    request_sha256: str = Field(pattern=_SHA256_PATTERN)
    protocol_sha256: str = Field(pattern=_SHA256_PATTERN)
    execution_decision_sha256: str = Field(pattern=_SHA256_PATTERN)
    opened_at: datetime
    completed_at: datetime
    image_count: Literal[1400]
    run_count: Literal[7000]
    successful_run_count: int = Field(ge=0)
    failed_run_count: int = Field(ge=0)
    runs: tuple[CampaignRunSummary, ...]
    one_look_opened: Literal[True]
    scientific_review_opened: Literal[False]
    step_three_authorized: Literal[False]
    optimization_authorized: Literal[False]
    qualification_opened: Literal[False]

    @model_validator(mode="after")
    def validate_terminal_counts(self) -> Self:
        """Require every frozen run exactly once in the terminal record."""
        if len(self.runs) != self.run_count:
            raise ValueError("terminal campaign run count is incomplete")
        _require_unique(
            (item.run_id for item in self.runs),
            product="terminal campaign run IDs",
        )
        successful = sum(item.status == "success" for item in self.runs)
        if (
            self.successful_run_count != successful
            or self.failed_run_count != self.run_count - successful
        ):
            raise ValueError("terminal campaign status counts are incomplete")
        if self.completed_at < self.opened_at:
            raise ValueError("campaign completed before it opened")
        return self

    def canonical_json_bytes(self) -> bytes:
        """Serialize the terminal campaign record deterministically."""
        return _canonical_json_bytes(self.model_dump(mode="json"))


def frozen_leg_matrix(
    lane: Literal["continuum", "compact-blend"],
) -> tuple[CampaignLeg, ...]:
    """Return the exact applicable finder legs for one frozen lane."""
    if lane == "continuum":
        return (
            CampaignLeg(finder_id="hebog", mode="candidate"),
            CampaignLeg(finder_id="released-pybdsf", mode="operational"),
            CampaignLeg(
                finder_id="released-pybdsf",
                mode="controlled-background",
            ),
            CampaignLeg(
                finder_id="pinned-pybdsf-master",
                mode="operational",
            ),
            CampaignLeg(
                finder_id="pinned-pybdsf-master",
                mode="controlled-background",
            ),
        )
    return (
        CampaignLeg(finder_id="hebog", mode="candidate"),
        CampaignLeg(finder_id="released-pybdsf", mode="operational"),
        CampaignLeg(
            finder_id="pinned-pybdsf-master",
            mode="operational",
        ),
        CampaignLeg(finder_id="aegean", mode="operational"),
        CampaignLeg(finder_id="aegean", mode="controlled-background"),
    )


def _canonical_json_bytes(value: object) -> bytes:
    """Encode one strict record without host-dependent whitespace."""
    document = json.dumps(value, allow_nan=False, indent=2, sort_keys=True)
    return f"{document}\n".encode()


def _require_relative_path(value: str, *, product: str) -> None:
    """Reject paths that can escape the private campaign root."""
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{product} path must stay relative")


def _require_unique(values: Iterable[object], *, product: str) -> None:
    """Require one stable identity for every request item."""
    materialized = tuple(values)
    if len(materialized) != len(set(materialized)):
        raise ValueError(f"{product} must be unique")


def _repository_relative(repository_root: Path, path: Path) -> str:
    """Resolve a required file within the committed repository."""
    root = repository_root.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"campaign path escapes repository: {path}")
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return resolved.relative_to(root).as_posix()


def _validate_decision_bindings(
    repository_root: Path,
    protocol_path: Path,
    decision_path: Path,
    base_review_path: Path,
    launcher_path: Path,
) -> tuple[
    PhaseFiveExternalComparisonProtocol,
    PhaseFiveExternalExecutionDecision,
]:
    """Fail before staging if any approved repository identity changed."""
    protocol = load_phase_five_external_comparison_protocol(protocol_path)
    decision = load_phase_five_external_execution_decision(decision_path)
    if not decision.execution_authorized:
        raise ValueError("external comparison execution is not authorized")
    if file_sha256(protocol_path) != decision.protocol_sha256:
        raise ValueError("campaign decision does not bind the protocol")
    if file_sha256(base_review_path) != decision.candidate_review_sha256:
        raise ValueError(
            "campaign decision does not bind the candidate review"
        )
    if source_tree_sha256(repository_root) != decision.source_tree_sha256:
        raise ValueError("campaign source tree differs from the decision")
    for runner in decision.runners:
        if (
            file_sha256(repository_root / runner.relative_path)
            != runner.sha256
        ):
            raise ValueError(
                f"campaign runner changed: {runner.relative_path}"
            )
    expected_launcher = (
        repository_root / "scripts/benchmark/run_phase5_external_campaign.py"
    ).resolve()
    if launcher_path.resolve() != expected_launcher:
        raise ValueError("unexpected complete-population launcher path")
    return protocol, decision


def _validate_containers(
    protocol: PhaseFiveExternalComparisonProtocol,
    decision: PhaseFiveExternalExecutionDecision,
    containers: dict[ExternalFinderId, CampaignContainerImage],
) -> tuple[
    CampaignContainerImage,
    CampaignContainerImage,
    CampaignContainerImage,
    CampaignContainerImage,
]:
    """Bind all local tags to approved immutable digests and one platform."""
    if set(containers) != set(_FINDER_ORDER):
        raise ValueError("campaign requires exactly four container images")
    references = {item.finder_id: item for item in protocol.references}
    expected_digests = {
        "hebog": decision.hebog_container_image_digest,
        **{
            finder_id: reference.container_image_digest
            for finder_id, reference in references.items()
        },
    }
    ordered = tuple(containers[finder_id] for finder_id in _FINDER_ORDER)
    for container in ordered:
        if container.digest != expected_digests[container.finder_id]:
            raise ValueError(
                f"container digest changed for {container.finder_id}"
            )
    platforms = {
        (item.operating_system, item.architecture) for item in ordered
    }
    if len(platforms) != 1:
        raise ValueError("campaign containers do not share one platform")
    return cast(
        tuple[
            CampaignContainerImage,
            CampaignContainerImage,
            CampaignContainerImage,
            CampaignContainerImage,
        ],
        ordered,
    )


def _population_requests(
    repository_root: Path,
    protocol: PhaseFiveExternalComparisonProtocol,
) -> tuple[
    tuple[CampaignInputRequest, ...],
    tuple[CampaignRunRequest, ...],
]:
    """Expand all declared recipes into the exact terminal run matrix."""
    inputs: list[CampaignInputRequest] = []
    runs: list[CampaignRunRequest] = []
    for population in protocol.populations:
        manifest_path = repository_root / population.manifest
        if file_sha256(manifest_path) != population.manifest_sha256:
            raise ValueError(f"population manifest changed: {population.lane}")
        manifest = load_dataset_manifest(manifest_path)
        lane_inputs: list[CampaignInputRequest] = []
        for dataset in manifest.datasets:
            for recipe in iter_dataset_recipes(dataset):
                input_id = f"{dataset.identifier}-seed-{recipe.seed}"
                campaign_input = CampaignInputRequest(
                    input_id=input_id,
                    lane=population.lane,
                    manifest_relative_path=population.manifest,
                    manifest_sha256=population.manifest_sha256,
                    dataset_identifier=dataset.identifier,
                    seed=recipe.seed,
                    recipe_sha256=recipe_sha256(recipe),
                    relative_directory=(
                        f"inputs/{population.lane}/{dataset.identifier}/"
                        f"seed-{recipe.seed}"
                    ),
                )
                lane_inputs.append(campaign_input)
                inputs.append(campaign_input)
                for leg in frozen_leg_matrix(population.lane):
                    run_id = f"{input_id}-{leg.finder_id}-{leg.mode}"
                    runs.append(
                        CampaignRunRequest(
                            run_id=run_id,
                            input_id=input_id,
                            lane=population.lane,
                            finder_id=leg.finder_id,
                            mode=leg.mode,
                            relative_directory=(
                                f"results/{population.lane}/"
                                f"{dataset.identifier}/seed-{recipe.seed}/"
                                f"{leg.finder_id}/{leg.mode}"
                            ),
                        )
                    )
        if len(lane_inputs) != population.image_count:
            raise ValueError(
                f"population image count changed: {population.lane}"
            )
    return tuple(inputs), tuple(runs)


def build_campaign_request(  # noqa: PLR0913
    *,
    repository_root: Path,
    protocol_path: Path,
    decision_path: Path,
    base_review_path: Path,
    launcher_path: Path,
    containers: dict[ExternalFinderId, CampaignContainerImage],
) -> CampaignRequest:
    """Build the complete deterministic request without writing anything."""
    root = repository_root.resolve()
    _repository_relative(root, protocol_path)
    _repository_relative(root, decision_path)
    _repository_relative(root, base_review_path)
    _repository_relative(root, launcher_path)
    protocol, decision = _validate_decision_bindings(
        root,
        protocol_path,
        decision_path,
        base_review_path,
        launcher_path,
    )
    ordered_containers = _validate_containers(
        protocol,
        decision,
        containers,
    )
    inputs, runs = _population_requests(root, protocol)
    if decision.pybdsf_ncores != _PYBDSF_NCORES:
        raise ValueError("campaign decision must retain four PyBDSF cores")
    if len(inputs) != _IMAGE_COUNT or len(runs) != _RUN_COUNT:
        raise ValueError("campaign request matrix count changed")
    return CampaignRequest(
        schema_version=1,
        campaign_id="phase-5-external-source-finder-comparison",
        status="authorized-unopened-request",
        protocol_sha256=file_sha256(protocol_path),
        execution_decision_sha256=file_sha256(decision_path),
        candidate_review_sha256=file_sha256(base_review_path),
        implementation_commit=decision.implementation_commit,
        source_tree_sha256=source_tree_sha256(root),
        launcher_sha256=file_sha256(launcher_path),
        materialization_runtime="approved-hebog-container",
        execution_concurrency=1,
        pybdsf_ncores=_PYBDSF_NCORES,
        containers=ordered_containers,
        image_count=_IMAGE_COUNT,
        run_count=_RUN_COUNT,
        inputs=inputs,
        runs=runs,
        one_look_opened=False,
        step_three_authorized=False,
        optimization_authorized=False,
        qualification_opened=False,
    )


def inspect_container_image(
    image: str,
    finder_id: ExternalFinderId,
    *,
    podman_executable: str,
) -> CampaignContainerImage:
    """Resolve one local image without pulling or opening campaign data."""
    completed = subprocess.run(
        [podman_executable, "image", "inspect", image],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"cannot inspect container {image!r}: {completed.stderr.strip()}"
        )
    payload = cast(object, json.loads(completed.stdout))
    if not isinstance(payload, list):
        raise ValueError(f"unexpected container inspection for {image!r}")
    inspected_items = cast(list[object], payload)
    if len(inspected_items) != 1:
        raise ValueError(f"unexpected container inspection for {image!r}")
    document = inspected_items[0]
    if not isinstance(document, dict):
        raise ValueError(f"invalid container inspection for {image!r}")
    inspected = cast(dict[str, object], document)
    image_id = str(inspected.get("Id", "")).removeprefix("sha256:")
    return CampaignContainerImage(
        finder_id=finder_id,
        image=image,
        image_id=image_id,
        digest=str(inspected.get("Digest", "")),
        operating_system=str(inspected.get("Os", "")),
        architecture=str(inspected.get("Architecture", "")),
    )


def _request_sha256(request: CampaignRequest) -> str:
    """Hash one complete unopened request."""
    return hashlib.sha256(request.canonical_json_bytes()).hexdigest()


def _private_staging_path(
    output_directory: Path,
    request: CampaignRequest,
) -> Path:
    """Return the deterministic hidden resume location for one decision."""
    return output_directory.parent / (
        f".{output_directory.name}.phase5-external-"
        f"{request.execution_decision_sha256[:12]}.staging"
    )


def _load_campaign_request(path: Path) -> CampaignRequest:
    """Load and verify one canonical private request."""
    payload = path.read_bytes()
    request = CampaignRequest.model_validate_json(payload)
    if payload != request.canonical_json_bytes():
        raise ValueError("private campaign request is not canonical")
    return request


def _load_open_state(path: Path) -> CampaignOpenState:
    """Load and verify the private one-look opening state."""
    payload = path.read_bytes()
    state = CampaignOpenState.model_validate_json(payload)
    if payload != state.canonical_json_bytes():
        raise ValueError("private campaign state is not canonical")
    return state


def _load_terminal_result(path: Path) -> TerminalCampaignResult:
    """Load and verify one canonical sealed campaign manifest."""
    payload = path.read_bytes()
    result = TerminalCampaignResult.model_validate_json(payload)
    if payload != result.canonical_json_bytes():
        raise ValueError("terminal campaign manifest is not canonical")
    return result


def prepare_private_staging(
    output_directory: Path,
    request: CampaignRequest,
    *,
    resume: bool,
) -> Path:
    """Open or explicitly resume only one exact hidden campaign request."""
    if output_directory.exists():
        raise FileExistsError(
            f"refusing to overwrite terminal campaign: {output_directory}"
        )
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    staging = _private_staging_path(output_directory, request)
    request_path = staging / "campaign-request.json"
    state_path = staging / "campaign-open-state.json"
    if resume:
        if not staging.is_dir():
            raise FileNotFoundError(
                f"private staging does not exist for resume: {staging}"
            )
        try:
            stored_request = _load_campaign_request(request_path)
            state = _load_open_state(state_path)
        except Exception as error:
            raise ValueError(
                "private campaign request or state is invalid"
            ) from error
        if (
            stored_request.canonical_json_bytes()
            != request.canonical_json_bytes()
        ):
            raise ValueError("private campaign request differs on resume")
        if (
            state.request_sha256 != _request_sha256(request)
            or state.execution_decision_sha256
            != request.execution_decision_sha256
        ):
            raise ValueError("private campaign state differs on resume")
        return staging
    if staging.exists():
        raise FileExistsError(
            f"private staging already exists; use --resume: {staging}"
        )
    staging.mkdir()
    request_path.write_bytes(request.canonical_json_bytes())
    state = CampaignOpenState(
        schema_version=1,
        status="private-staging-open",
        request_sha256=_request_sha256(request),
        execution_decision_sha256=request.execution_decision_sha256,
        opened_at=datetime.now(UTC),
    )
    state_path.write_bytes(state.canonical_json_bytes())
    return staging


def _container_by_finder(
    request: CampaignRequest,
    finder_id: ExternalFinderId,
) -> CampaignContainerImage:
    """Resolve one canonical container from the complete request."""
    return next(
        item for item in request.containers if item.finder_id == finder_id
    )


def _container_prefix(
    container: CampaignContainerImage,
    *,
    repository_root: Path,
    staging_root: Path,
    podman_executable: str,
    expose_source: bool,
) -> list[str]:
    """Build a network-isolated container command over two bounded mounts."""
    command = [
        podman_executable,
        "run",
        "--rm",
        "--network=none",
        "--volume",
        f"{repository_root.resolve()}:/repository:ro",
        "--volume",
        f"{staging_root.resolve()}:/campaign:rw",
        "--workdir",
        "/repository",
        "--entrypoint",
        "python3",
    ]
    if expose_source:
        command.extend(("--env", "PYTHONPATH=/repository/src"))
    # Execute the inspected immutable local image ID. The human-friendly tag
    # is provenance only and may not select runtime bytes after preflight.
    command.append(f"sha256:{container.image_id}")
    return command


def materializer_container_command(
    request: CampaignRequest,
    campaign_input: CampaignInputRequest,
    *,
    repository_root: Path,
    staging_root: Path,
    podman_executable: str,
) -> tuple[str, ...]:
    """Run common-input generation inside the approved Hebog image."""
    container = _container_by_finder(request, "hebog")
    command = _container_prefix(
        container,
        repository_root=repository_root,
        staging_root=staging_root,
        podman_executable=podman_executable,
        expose_source=False,
    )
    command.extend(
        (
            "-c",
            _MATERIALIZE_CODE,
            "/repository/config/contracts/phase-5-external-comparison.json",
            f"/repository/{campaign_input.manifest_relative_path}",
            campaign_input.dataset_identifier,
            str(campaign_input.seed),
            f"/campaign/{campaign_input.relative_directory}",
        )
    )
    return tuple(command)


def runner_container_command(
    request: CampaignRequest,
    run: CampaignRunRequest,
    *,
    repository_root: Path,
    staging_root: Path,
    podman_executable: str,
) -> tuple[str, ...]:
    """Build one exact isolated runner command from the frozen request."""
    inputs = {item.input_id: item for item in request.inputs}
    campaign_input = inputs[run.input_id]
    container = _container_by_finder(request, run.finder_id)
    command = _container_prefix(
        container,
        repository_root=repository_root,
        staging_root=staging_root,
        podman_executable=podman_executable,
        expose_source=run.finder_id != "hebog",
    )
    command.extend(
        (
            f"/repository/{_RUNNER_PATHS[run.finder_id]}",
            "--protocol",
            "/repository/config/contracts/phase-5-external-comparison.json",
            "--execution-decision",
            "/repository/config/contracts/"
            "phase-5-external-execution-decision.json",
            "--input",
            f"/campaign/{campaign_input.relative_directory}/input.json",
        )
    )
    if run.finder_id == "hebog":
        command.extend(
            (
                "--base-review",
                "/repository/config/contracts/phase-5-corrective-a-review.json",
                "--manifest",
                f"/repository/{campaign_input.manifest_relative_path}",
            )
        )
    elif run.finder_id in {
        "released-pybdsf",
        "pinned-pybdsf-master",
    }:
        command.extend(
            (
                "--finder-id",
                run.finder_id,
                "--mode",
                run.mode,
                "--ncores",
                str(request.pybdsf_ncores),
            )
        )
    else:
        command.extend(("--mode", run.mode))
    command.extend(
        (
            "--container-image-digest",
            container.digest,
            "--output",
            f"/campaign/{run.relative_directory}",
        )
    )
    return tuple(command)


def _write_infrastructure_log(
    staging_root: Path,
    identity: str,
    command: tuple[str, ...],
    completed: subprocess.CompletedProcess[str],
) -> Path:
    """Retain a non-scientific failure log without overwriting an attempt."""
    log_directory = staging_root / "infrastructure-logs"
    log_directory.mkdir(exist_ok=True)
    attempt = 1
    while True:
        path = log_directory / f"{identity}-attempt-{attempt:03d}.json"
        if not path.exists():
            break
        attempt += 1
    path.write_bytes(
        _canonical_json_bytes(
            {
                "command": list(command),
                "returncode": completed.returncode,
                "stderr": completed.stderr,
                "stdout": completed.stdout,
            }
        )
    )
    return path


def _invoke_container(
    command: tuple[str, ...],
    *,
    staging_root: Path,
    identity: str,
) -> None:
    """Execute one container and stop only for infrastructure failure."""
    completed = subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode == 0:
        return
    log_path = _write_infrastructure_log(
        staging_root,
        identity,
        command,
        completed,
    )
    raise RuntimeError(
        f"campaign infrastructure failed for {identity}; see {log_path}"
    )


def _verify_input(
    request: CampaignRequest,
    campaign_input: CampaignInputRequest,
    staging_root: Path,
) -> Path:
    """Verify one common input against its complete unopened request."""
    input_path = (
        staging_root / campaign_input.relative_directory / "input.json"
    )
    bundle = load_external_input_bundle(input_path, verify_artifacts=True)
    if (
        bundle.protocol_sha256 != request.protocol_sha256
        or bundle.manifest_sha256 != campaign_input.manifest_sha256
        or bundle.dataset_identifier != campaign_input.dataset_identifier
        or bundle.seed != campaign_input.seed
        or bundle.recipe_sha256 != campaign_input.recipe_sha256
    ):
        raise ValueError(
            f"campaign input identity changed: {campaign_input.input_id}"
        )
    return input_path


def materialize_campaign_inputs(
    request: CampaignRequest,
    *,
    repository_root: Path,
    staging_root: Path,
    podman_executable: str,
) -> None:
    """Materialize or verify every common input in deterministic order."""
    for index, campaign_input in enumerate(request.inputs, start=1):
        directory = staging_root / campaign_input.relative_directory
        input_path = directory / "input.json"
        if input_path.exists():
            _verify_input(request, campaign_input, staging_root)
        else:
            if directory.exists():
                raise ValueError(
                    f"incomplete campaign input directory: {directory}"
                )
            command = materializer_container_command(
                request,
                campaign_input,
                repository_root=repository_root,
                staging_root=staging_root,
                podman_executable=podman_executable,
            )
            _invoke_container(
                command,
                staging_root=staging_root,
                identity=f"materialize-{campaign_input.input_id}",
            )
            _verify_input(request, campaign_input, staging_root)
        if index % 25 == 0 or index == request.image_count:
            print(f"verified {index}/{request.image_count} common inputs")


def _expected_runtime(
    run: CampaignRunRequest,
    protocol: PhaseFiveExternalComparisonProtocol,
    decision: PhaseFiveExternalExecutionDecision,
) -> tuple[str, str, str]:
    """Return expected source, container, and dependency identities."""
    if run.finder_id == "hebog":
        return (
            decision.implementation_commit,
            decision.hebog_container_image_digest,
            decision.hebog_dependency_inventory_sha256,
        )
    reference = next(
        item for item in protocol.references if item.finder_id == run.finder_id
    )
    return (
        reference.source_revision,
        reference.container_image_digest,
        reference.dependency_inventory_sha256,
    )


def _verify_run(
    request: CampaignRequest,
    run: CampaignRunRequest,
    *,
    protocol: PhaseFiveExternalComparisonProtocol,
    decision: PhaseFiveExternalExecutionDecision,
    staging_root: Path,
) -> CampaignRunSummary:
    """Verify one raw result, its common input, and isolated runtime."""
    result_path = staging_root / run.relative_directory / "result.json"
    result = load_external_run_result(result_path, verify_artifacts=True)
    inputs = {item.input_id: item for item in request.inputs}
    input_path = (
        staging_root / inputs[run.input_id].relative_directory / "input.json"
    )
    expected_source, expected_container, expected_inventory = (
        _expected_runtime(
            run,
            protocol,
            decision,
        )
    )
    if (
        result.protocol_sha256 != request.protocol_sha256
        or result.execution_decision_sha256
        != request.execution_decision_sha256
        or result.input_bundle_sha256 != file_sha256(input_path)
        or result.finder_id != run.finder_id
        or result.mode != run.mode
        or result.runtime.source_revision != expected_source
        or result.runtime.container_image_digest != expected_container
        or result.runtime.dependency_inventory_sha256 != expected_inventory
    ):
        raise ValueError(f"campaign run identity changed: {run.run_id}")
    return CampaignRunSummary(
        run_id=run.run_id,
        input_id=run.input_id,
        finder_id=run.finder_id,
        mode=run.mode,
        status=result.status,
        result_relative_path=(f"{run.relative_directory}/result.json"),
        result_sha256=file_sha256(result_path),
    )


def execute_campaign_runs(  # noqa: PLR0913
    request: CampaignRequest,
    *,
    protocol: PhaseFiveExternalComparisonProtocol,
    decision: PhaseFiveExternalExecutionDecision,
    repository_root: Path,
    staging_root: Path,
    podman_executable: str,
) -> None:
    """Run or verify every finder leg serially without exposing results."""
    for index, run in enumerate(request.runs, start=1):
        directory = staging_root / run.relative_directory
        result_path = directory / "result.json"
        if result_path.exists():
            _verify_run(
                request,
                run,
                protocol=protocol,
                decision=decision,
                staging_root=staging_root,
            )
        else:
            if directory.exists():
                raise ValueError(
                    f"incomplete campaign run directory: {directory}"
                )
            command = runner_container_command(
                request,
                run,
                repository_root=repository_root,
                staging_root=staging_root,
                podman_executable=podman_executable,
            )
            _invoke_container(
                command,
                staging_root=staging_root,
                identity=run.run_id,
            )
            _verify_run(
                request,
                run,
                protocol=protocol,
                decision=decision,
                staging_root=staging_root,
            )
        if index % 25 == 0 or index == request.run_count:
            print(f"verified {index}/{request.run_count} finder runs")


def require_exact_path_set(
    *,
    expected: tuple[str, ...],
    observed: tuple[str, ...],
    product: str,
) -> None:
    """Reject both missing and undeclared products before publication."""
    expected_set = set(expected)
    observed_set = set(observed)
    missing = sorted(expected_set.difference(observed_set))
    unexpected = sorted(observed_set.difference(expected_set))
    if missing:
        raise ValueError(f"missing {product}: {missing[0]}")
    if unexpected:
        raise ValueError(f"unexpected {product}: {unexpected[0]}")


def require_no_private_temporary_paths(staging_root: Path) -> None:
    """Refuse to publish remnants from an interrupted atomic operation."""
    temporary_paths = sorted(
        path.relative_to(staging_root).as_posix()
        for path in staging_root.rglob("*")
        if path.name.startswith(".")
    )
    if temporary_paths:
        raise ValueError(
            "private temporary path remains from an interrupted operation: "
            f"{temporary_paths[0]}"
        )


def _seal_terminal_manifest(
    request: CampaignRequest,
    state: CampaignOpenState,
    summaries: tuple[CampaignRunSummary, ...],
    result_path: Path,
) -> TerminalCampaignResult:
    """Write once or verify the exact manifest left before a failed rename."""
    if (
        state.request_sha256 != _request_sha256(request)
        or state.execution_decision_sha256 != request.execution_decision_sha256
    ):
        raise ValueError("campaign opening state differs at publication")
    successful = sum(item.status == "success" for item in summaries)
    if result_path.exists():
        sealed = _load_terminal_result(result_path)
        expected = TerminalCampaignResult(
            schema_version=1,
            campaign_id=request.campaign_id,
            status="terminal-raw-results-sealed",
            request_sha256=_request_sha256(request),
            protocol_sha256=request.protocol_sha256,
            execution_decision_sha256=request.execution_decision_sha256,
            opened_at=state.opened_at,
            completed_at=sealed.completed_at,
            image_count=request.image_count,
            run_count=request.run_count,
            successful_run_count=successful,
            failed_run_count=request.run_count - successful,
            runs=summaries,
            one_look_opened=True,
            scientific_review_opened=False,
            step_three_authorized=False,
            optimization_authorized=False,
            qualification_opened=False,
        )
        if sealed != expected:
            raise ValueError("terminal campaign manifest differs on resume")
        return sealed
    result = TerminalCampaignResult(
        schema_version=1,
        campaign_id=request.campaign_id,
        status="terminal-raw-results-sealed",
        request_sha256=_request_sha256(request),
        protocol_sha256=request.protocol_sha256,
        execution_decision_sha256=request.execution_decision_sha256,
        opened_at=state.opened_at,
        completed_at=datetime.now(UTC),
        image_count=request.image_count,
        run_count=request.run_count,
        successful_run_count=successful,
        failed_run_count=request.run_count - successful,
        runs=summaries,
        one_look_opened=True,
        scientific_review_opened=False,
        step_three_authorized=False,
        optimization_authorized=False,
        qualification_opened=False,
    )
    temporary_path = result_path.with_name(f".{result_path.name}.tmp")
    with temporary_path.open("xb") as temporary_file:
        temporary_file.write(result.canonical_json_bytes())
    temporary_path.replace(result_path)
    return result


def finalize_terminal_campaign(
    request: CampaignRequest,
    *,
    protocol: PhaseFiveExternalComparisonProtocol,
    decision: PhaseFiveExternalExecutionDecision,
    staging_root: Path,
    output_directory: Path,
) -> Path:
    """Verify the complete matrix, seal it, and publish with one rename."""
    require_no_private_temporary_paths(staging_root)
    expected_inputs = tuple(
        f"{item.relative_directory}/input.json" for item in request.inputs
    )
    observed_inputs = tuple(
        sorted(
            path.relative_to(staging_root).as_posix()
            for path in (staging_root / "inputs").rglob("input.json")
        )
    )
    require_exact_path_set(
        expected=expected_inputs,
        observed=observed_inputs,
        product="common input",
    )
    expected_results = tuple(
        f"{item.relative_directory}/result.json" for item in request.runs
    )
    observed_results = tuple(
        sorted(
            path.relative_to(staging_root).as_posix()
            for path in (staging_root / "results").rglob("result.json")
        )
    )
    require_exact_path_set(
        expected=expected_results,
        observed=observed_results,
        product="run result",
    )
    summaries = tuple(
        _verify_run(
            request,
            run,
            protocol=protocol,
            decision=decision,
            staging_root=staging_root,
        )
        for run in request.runs
    )
    state = _load_open_state(staging_root / "campaign-open-state.json")
    result_path = staging_root / "campaign.json"
    _seal_terminal_manifest(request, state, summaries, result_path)
    if output_directory.exists():
        raise FileExistsError(
            f"refusing to overwrite terminal campaign: {output_directory}"
        )
    staging_root.rename(output_directory)
    return output_directory / "campaign.json"


def _parse_args() -> argparse.Namespace:
    """Parse one complete authorized campaign request."""
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=root)
    parser.add_argument(
        "--protocol",
        type=Path,
        default=root / "config/contracts/phase-5-external-comparison.json",
    )
    parser.add_argument(
        "--execution-decision",
        type=Path,
        default=(
            root / "config/contracts/phase-5-external-execution-decision.json"
        ),
    )
    parser.add_argument(
        "--base-review",
        type=Path,
        default=root / "config/contracts/phase-5-corrective-a-review.json",
    )
    parser.add_argument("--hebog-image", required=True)
    parser.add_argument("--released-pybdsf-image", required=True)
    parser.add_argument("--master-pybdsf-image", required=True)
    parser.add_argument("--aegean-image", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--podman-executable", default="podman")
    return parser.parse_args()


def _inspected_containers(
    arguments: argparse.Namespace,
) -> dict[
    ExternalFinderId,
    CampaignContainerImage,
]:
    """Inspect all images before any private campaign directory is created."""
    images: dict[ExternalFinderId, str] = {
        "hebog": arguments.hebog_image,
        "released-pybdsf": arguments.released_pybdsf_image,
        "pinned-pybdsf-master": arguments.master_pybdsf_image,
        "aegean": arguments.aegean_image,
    }
    return {
        finder_id: inspect_container_image(
            image,
            finder_id,
            podman_executable=arguments.podman_executable,
        )
        for finder_id, image in images.items()
    }


def _run(arguments: argparse.Namespace) -> None:
    """Preflight, privately execute, and atomically publish one campaign."""
    if arguments.resume and arguments.preflight_only:
        raise ValueError("--resume cannot be combined with --preflight-only")
    if arguments.output.exists():
        raise FileExistsError(
            f"refusing to overwrite terminal campaign: {arguments.output}"
        )
    repository_root = arguments.repository_root.resolve()
    request = build_campaign_request(
        repository_root=repository_root,
        protocol_path=arguments.protocol,
        decision_path=arguments.execution_decision,
        base_review_path=arguments.base_review,
        launcher_path=Path(__file__),
        containers=_inspected_containers(arguments),
    )
    request_sha256 = _request_sha256(request)
    if arguments.preflight_only:
        print(
            "preflight passed: "
            f"request={request_sha256} images={request.image_count} "
            f"runs={request.run_count}"
        )
        return
    staging = prepare_private_staging(
        arguments.output.resolve(),
        request,
        resume=arguments.resume,
    )
    protocol = load_phase_five_external_comparison_protocol(arguments.protocol)
    decision = load_phase_five_external_execution_decision(
        arguments.execution_decision
    )
    materialize_campaign_inputs(
        request,
        repository_root=repository_root,
        staging_root=staging,
        podman_executable=arguments.podman_executable,
    )
    execute_campaign_runs(
        request,
        protocol=protocol,
        decision=decision,
        repository_root=repository_root,
        staging_root=staging,
        podman_executable=arguments.podman_executable,
    )
    result_path = finalize_terminal_campaign(
        request,
        protocol=protocol,
        decision=decision,
        staging_root=staging,
        output_directory=arguments.output.resolve(),
    )
    print(f"terminal campaign published: {result_path}")


def main() -> None:
    """Parse and run one complete authorized campaign."""
    _run(_parse_args())


if __name__ == "__main__":
    main()
