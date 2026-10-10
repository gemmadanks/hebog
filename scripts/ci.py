"""Small, scheduler-independent helpers for the GitHub Actions checks."""

import argparse
import json
import math
import os
import subprocess
from collections.abc import Iterable, Mapping
from pathlib import Path, PurePosixPath
from typing import cast


def docs_only(paths: Iterable[str]) -> bool:
    """Return whether every changed path is documentation."""
    changed = tuple(paths)
    return bool(changed) and all(
        path in {"README.md", "LOG.md"}
        or (
            path.startswith("docs/")
            and PurePosixPath(path).suffix
            in {".md", ".png", ".jpg", ".jpeg", ".svg", ".gif"}
        )
        or (path.startswith("plans/") and path.endswith(".md"))
        for path in changed
    )


def check_results(
    results: Mapping[str, str],
    *,
    full: bool,
    required: Iterable[str],
    conditional: Iterable[str],
) -> None:
    """Fail when a required check did not succeed."""
    for name in required:
        if results.get(name) != "success":
            raise ValueError(f"{name}: {results.get(name, 'missing')}")
    for name in conditional:
        allowed = {"success"} if full else {"success", "skipped"}
        if results.get(name) not in allowed:
            raise ValueError(f"{name}: {results.get(name, 'missing')}")


def merge_durations(paths: Iterable[Path]) -> dict[str, float]:
    """Keep the slowest observed time per test across the runner matrix.

    pytest-split writes only the shard's measured tests with
    ``--clean-durations``. The cache is a scheduling hint, never evidence of
    scientific performance, and every shard reads the same frozen snapshot.
    """
    merged: dict[str, float] = {}
    for path in paths:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"{path.name}: expected a duration mapping")
        # JSON object keys are strings; values are validated below.
        durations = cast(dict[str, object], payload)
        for node_id, seconds in durations.items():
            if (
                not node_id
                or isinstance(seconds, bool)
                or not isinstance(seconds, int | float)
                or not math.isfinite(seconds)
                or seconds < 0
            ):
                message = f"{path.name}: invalid duration for {node_id}"
                raise ValueError(message)
            merged[node_id] = max(merged.get(node_id, 0.0), seconds)
    if not merged:
        raise ValueError("no measured test durations")
    return merged


def main() -> None:
    """Route a PR, check prerequisite results, or merge shard timings."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    changes = commands.add_parser("changes")
    changes.add_argument("--event", required=True)
    changes.add_argument("--base", default="")
    changes.add_argument("--output", type=Path, required=True)
    gate = commands.add_parser("gate")
    gate.add_argument("--required", nargs="+", required=True)
    gate.add_argument("--conditional", nargs="*", default=())
    durations = commands.add_parser("durations")
    durations.add_argument("--input", type=Path, required=True)
    durations.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.command == "changes":
        full = True
        if arguments.event == "pull_request":
            if not arguments.base:
                parser.error("a pull request requires --base")
            changed = (
                subprocess.check_output(
                    [
                        "git",
                        "diff",
                        "--name-only",
                        "--no-renames",
                        "-z",
                        arguments.base,
                        "HEAD",
                    ]
                )
                .decode("utf-8", errors="surrogateescape")
                .split("\0")
            )
            full = not docs_only(path for path in changed if path)
        with arguments.output.open("a", encoding="utf-8") as output:
            output.write(f"full={str(full).lower()}\n")
        print("Full CI" if full else "Documentation-only CI")
    elif arguments.command == "gate":
        # An absent or malformed routing output must never waive a check.
        full_value = os.environ["FULL_CI"]
        if full_value not in {"true", "false"}:
            raise ValueError("FULL_CI must be true or false")
        needs = json.loads(os.environ["NEEDS_JSON"])
        check_results(
            {name: job["result"] for name, job in needs.items()},
            full=full_value == "true",
            required=arguments.required,
            conditional=arguments.conditional,
        )
    else:
        merged = merge_durations(arguments.input.rglob("durations.json"))
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(
            json.dumps(merged, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
