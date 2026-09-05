#!/usr/bin/env python3
"""Refresh all public notebook Hebog results from the current source tree.

Each distinct Git revision and source-tree hash receives an immutable campaign
directory. Sealed PyBDSF and Aegean products are reused as references, while
only Hebog is rerun over the frozen SDC1, Hydra, and LoTSS inputs. A mutable
registry and ``latest`` symlink provide convenient notebook discovery without
overwriting scientific products.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import runpy
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from hebog.validation.external_runners import source_tree_sha256

_ROOT = Path(__file__).parents[2]
_INPUT_CAMPAIGN = Path(
    "benchmark-results/phase-5/current-public-plus-lotss-comparison/"
    "input-campaign/campaign.json"
)
_REFERENCE_CAMPAIGN = Path(
    "benchmark-results/phase-5/current-public-plus-lotss-comparison/"
    "reference-campaign/campaign.json"
)
_HISTORY_ROOT = Path("benchmark-results/phase-5/hebog-notebook-refreshes")
_HEBOG_RUNNER = Path("scripts/benchmark/run_phase5_public_finder_hebog.py")
_INPUT_HELPERS = Path(
    "scripts/benchmark/run_phase5_current_public_hebog_campaign.py"
)
_RUNNER_PATH = Path("scripts/benchmark/refresh_public_notebook_hebog.py")
_BOOTSTRAP_CAMPAIGNS = (
    (
        "SDC1/Hydra baseline (2026-08-27)",
        Path("benchmark-results/phase-5/current-public-hebog-comparison"),
    ),
    (
        "LoTSS baseline (2026-08-28)",
        Path("benchmark-results/phase-5/lotss-public-comparison"),
    ),
)
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _parse_args() -> argparse.Namespace:
    """Parse one reusable notebook-refresh invocation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=_ROOT)
    parser.add_argument("--input-campaign", type=Path, default=_INPUT_CAMPAIGN)
    parser.add_argument(
        "--reference-campaign",
        type=Path,
        default=_REFERENCE_CAMPAIGN,
    )
    parser.add_argument("--history-root", type=Path, default=_HISTORY_ROOT)
    parser.add_argument(
        "--label",
        help="Optional human label; identity still comes from source hashes",
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    return parser.parse_args()


def _read_json(path: Path) -> dict[str, Any]:
    """Read one required JSON object."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return cast(dict[str, Any], value)


def _write_json(path: Path, value: object) -> None:
    """Write one canonical JSON document."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_once(path: Path, value: object) -> None:
    """Write immutable state once or require an identical resume value."""
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != value:
            raise ValueError(f"refresh resume identity changed: {path}")
        return
    _write_json(path, value)


def _sha256(path: Path) -> str:
    """Return one file's SHA-256 digest."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _repository_path(repository_root: Path, path: Path) -> Path:
    """Resolve one path and require it to remain in the repository."""
    resolved = path if path.is_absolute() else repository_root / path
    resolved = resolved.resolve()
    if not resolved.is_relative_to(repository_root):
        raise ValueError(f"path escapes repository: {resolved}")
    return resolved


def _repository_relative(repository_root: Path, path: Path) -> str:
    """Return a resolved repository-relative path."""
    return str(path.resolve().relative_to(repository_root))


def _git_identity(repository_root: Path) -> tuple[str, bool]:
    """Return HEAD and whether tracked or untracked work is present."""
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return commit, bool(status.strip())


def _append_progress(path: Path, message: str) -> None:
    """Durably append one completed-case marker."""
    with path.open("a", encoding="utf-8") as handle:
        handle.write(message + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _load_public_runner(
    repository_root: Path,
) -> tuple[str, Callable[..., dict[str, object]]]:
    """Load the exact runner and return its authoritative configuration."""
    runner = runpy.run_path(str(repository_root / _HEBOG_RUNNER))
    configuration_sha256 = cast(
        Callable[[], str], runner["public_hebog_configuration_sha256"]
    )()
    run_public_hebog = cast(
        Callable[..., dict[str, object]], runner["run_public_hebog"]
    )
    return configuration_sha256, run_public_hebog


def _campaign_record(
    repository_root: Path,
    campaign_root: Path,
    *,
    label: str,
    commit: str | None = None,
    dirty: bool | None = None,
) -> dict[str, object]:
    """Build one notebook-history record from a sealed campaign."""
    campaign = _read_json(campaign_root / "campaign.json")
    return {
        "label": label,
        "campaign_repository_path": _repository_relative(
            repository_root, campaign_root
        ),
        "commit": commit,
        "dirty_worktree": dirty,
        "source_tree_sha256": campaign.get("source_tree_sha256"),
        "configuration_sha256": campaign.get("configuration_sha256"),
        "hebog_runner_sha256": campaign.get("hebog_runner_sha256"),
        "completed_at": campaign.get("completed_at"),
        "case_count": campaign.get("case_count"),
        "successful_case_count": campaign.get("successful_case_count"),
        "status": campaign.get("status"),
    }


def _publish_history(  # noqa: PLR0913
    *,
    repository_root: Path,
    history_root: Path,
    output: Path,
    label: str,
    commit: str,
    dirty: bool,
) -> None:
    """Register a sealed refresh and update the stable latest pointer."""
    index_path = history_root / "index.json"
    records_by_path: dict[str, dict[str, object]] = {}
    if index_path.is_file():
        index = _read_json(index_path)
        for item in cast(list[object], index.get("refreshes", [])):
            if isinstance(item, dict) and "campaign_repository_path" in item:
                records_by_path[str(item["campaign_repository_path"])] = item
    for baseline_label, relative in _BOOTSTRAP_CAMPAIGNS:
        campaign_root = repository_root / relative
        if (campaign_root / "campaign.json").is_file():
            record = _campaign_record(
                repository_root,
                campaign_root,
                label=baseline_label,
            )
            records_by_path[str(record["campaign_repository_path"])] = record
    current = _campaign_record(
        repository_root,
        output,
        label=label,
        commit=commit,
        dirty=dirty,
    )
    current_path = str(current["campaign_repository_path"])
    records_by_path[current_path] = current
    refreshes = sorted(
        records_by_path.values(),
        key=lambda item: str(item.get("completed_at") or ""),
    )
    index = {
        "schema_version": 1,
        "latest_campaign_repository_path": current_path,
        "refresh_count": len(refreshes),
        "refreshes": refreshes,
    }
    temporary = history_root / ".index.json.tmp"
    _write_json(temporary, index)
    temporary.replace(index_path)
    latest = history_root / "latest"
    if latest.is_symlink():
        latest.unlink()
    elif latest.exists():
        raise FileExistsError(f"latest pointer is not a symlink: {latest}")
    latest.symlink_to(output.name, target_is_directory=True)


def run_refresh(  # noqa: C901, PLR0912, PLR0913, PLR0915
    *,
    repository_root: Path,
    input_campaign_path: Path,
    reference_campaign_path: Path,
    history_root: Path,
    label: str | None,
    resume: bool,
    preflight_only: bool,
) -> None:
    """Run or reuse one source-identified all-public Hebog refresh."""
    input_campaign = _read_json(input_campaign_path)
    reference_campaign = _read_json(reference_campaign_path)
    raw_cases = input_campaign.get("results")
    raw_references = reference_campaign.get("results")
    if (
        not isinstance(raw_cases, list)
        or not raw_cases
        or input_campaign.get("scientific_claims_authorized") is not False
    ):
        raise ValueError(
            "input campaign is not a usable sealed diagnostic base"
        )
    if (
        not isinstance(raw_references, list)
        or len(raw_references) != 2 * len(raw_cases)
        or reference_campaign.get("scientific_claims_authorized") is not False
        or any(item.get("status") != "success" for item in raw_references)
    ):
        raise ValueError(
            "reference campaign does not contain two successful runs per case"
        )

    configuration_sha256, run_public_hebog = _load_public_runner(
        repository_root
    )
    source_sha256 = source_tree_sha256(repository_root)
    hebog_runner_sha256 = _sha256(repository_root / _HEBOG_RUNNER)
    commit, dirty = _git_identity(repository_root)
    identifier = f"{commit[:7]}-{source_sha256[:12]}-{hebog_runner_sha256[:8]}"
    if not _SAFE_IDENTIFIER.fullmatch(identifier):
        raise ValueError(f"unsafe refresh identifier: {identifier}")
    output = history_root / identifier
    display_label = label or (
        f"{commit[:7]}{' + working tree' if dirty else ''} | "
        f"{source_sha256[:8]} | runner {hebog_runner_sha256[:8]}"
    )
    if output.is_dir():
        _publish_history(
            repository_root=repository_root,
            history_root=history_root,
            output=output,
            label=display_label,
            commit=commit,
            dirty=dirty,
        )
        print(
            json.dumps(
                {"output": str(output), "status": "reused"}, sort_keys=True
            )
        )
        return

    staging = history_root / f".{identifier}.staging"
    if staging.exists() and not resume:
        raise FileExistsError(
            f"refresh staging exists; pass --resume: {staging}"
        )
    if preflight_only:
        print(
            json.dumps(
                {
                    "case_count": len(raw_cases),
                    "commit": commit,
                    "configuration_sha256": configuration_sha256,
                    "dirty_worktree": dirty,
                    "identifier": identifier,
                    "hebog_runner_sha256": hebog_runner_sha256,
                    "source_tree_sha256": source_sha256,
                    "status": "preflight-passed",
                },
                sort_keys=True,
            )
        )
        return

    staging.mkdir(parents=True, exist_ok=resume)
    request = {
        "schema_version": 1,
        "request_id": f"public-notebook-hebog-refresh-{identifier}",
        "status": "derived-current-source-staging",
        "commit": commit,
        "dirty_worktree": dirty,
        "source_tree_sha256": source_sha256,
        "configuration_sha256": configuration_sha256,
        "hebog_runner_repository_path": str(_HEBOG_RUNNER),
        "hebog_runner_sha256": hebog_runner_sha256,
        "base_campaign_repository_path": _repository_relative(
            repository_root, reference_campaign_path
        ),
        "base_campaign_sha256": _sha256(reference_campaign_path),
        "input_campaign_repository_path": _repository_relative(
            repository_root, input_campaign_path
        ),
        "input_campaign_sha256": _sha256(input_campaign_path),
        "runner_repository_path": str(_RUNNER_PATH),
        "runner_sha256": _sha256(repository_root / _RUNNER_PATH),
        "case_count": len(raw_cases),
        "scientific_claims_authorized": False,
    }
    _write_once(staging / "request.json", request)

    input_helpers = runpy.run_path(str(repository_root / _INPUT_HELPERS))
    resolve_input = cast(
        Callable[..., tuple[Path, object, dict[str, Any]]],
        input_helpers["_resolve_input"],
    )
    input_root = input_campaign_path.parent
    terminal_results: list[dict[str, object]] = []
    progress_path = staging / "progress.log"
    for item in raw_cases:
        if not isinstance(item, dict) or item.get("status") != "success":
            raise ValueError("input campaign contains a non-successful case")
        case_id = str(item.get("case_id", ""))
        if not case_id:
            raise ValueError(
                "input campaign contains an empty case identifier"
            )
        result_directory = (
            staging / "results" / case_id / "hebog" / "operational"
        )
        result_path = result_directory / "result.json"
        if result_path.is_file():
            result = _read_json(result_path)
            if result.get("status") != "success":
                raise ValueError(
                    f"resume found failed Hebog result: {case_id}"
                )
        else:
            input_path, core, _ = resolve_input(
                repository_root, input_root, case_id
            )
            print(f"running current Hebog: {case_id}", flush=True)
            result = run_public_hebog(
                input_path=input_path,
                output=result_directory,
                case_id=case_id,
                core=core,
                configuration_sha256=configuration_sha256,
            )
            _append_progress(progress_path, f"completed {case_id}")
        terminal_results.append(
            {
                "case_id": case_id,
                "finder_id": "hebog",
                "mode": "operational",
                "result_path": str(result_path.relative_to(staging)),
                "result_sha256": _sha256(result_path),
                "status": result["status"],
            }
        )
    if source_tree_sha256(repository_root) != source_sha256:
        raise RuntimeError("Hebog source tree changed during notebook refresh")
    if _sha256(repository_root / _HEBOG_RUNNER) != hebog_runner_sha256:
        raise RuntimeError(
            "Hebog public runner changed during notebook refresh"
        )
    terminal = {
        **request,
        "campaign_id": f"public-notebook-hebog-refresh-{identifier}",
        "status": "terminal-derived-results-sealed",
        "completed_at": datetime.now(UTC).isoformat(),
        "successful_case_count": sum(
            item["status"] == "success" for item in terminal_results
        ),
        "results": terminal_results,
    }
    _write_once(staging / "campaign.json", terminal)
    staging.rename(output)
    _publish_history(
        repository_root=repository_root,
        history_root=history_root,
        output=output,
        label=display_label,
        commit=commit,
        dirty=dirty,
    )
    print(
        json.dumps(
            {
                "case_count": len(terminal_results),
                "identifier": identifier,
                "output": str(output),
                "hebog_runner_sha256": hebog_runner_sha256,
                "source_tree_sha256": source_sha256,
                "status": terminal["status"],
            },
            sort_keys=True,
        ),
        flush=True,
    )


def main() -> None:
    """Run the public notebook refresh from command-line arguments."""
    arguments = _parse_args()
    repository_root = cast(Path, arguments.repository_root).resolve()
    run_refresh(
        repository_root=repository_root,
        input_campaign_path=_repository_path(
            repository_root, cast(Path, arguments.input_campaign)
        ),
        reference_campaign_path=_repository_path(
            repository_root, cast(Path, arguments.reference_campaign)
        ),
        history_root=_repository_path(
            repository_root, cast(Path, arguments.history_root)
        ),
        label=cast(str | None, arguments.label),
        resume=bool(arguments.resume),
        preflight_only=bool(arguments.preflight_only),
    )


if __name__ == "__main__":
    main()
