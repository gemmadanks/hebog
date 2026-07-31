"""Orchestrate isolated release or master PyBDSF baseline repetitions."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

_RELEASE_COMMIT = "1b6e0a04ba6327bc1ce3f576928fe58b81d8c1cc"
_MASTER_COMMIT = "c70103be3ae9ae9908286f144e6ce956acc0ce5c"
_RAPTHOR_COMMIT = "b1a64674b1022476cf052fc2d06ee3b16f031ecd"
_LSMTOOL_COMMIT = "3adf3d6f1f8c03db34e13a45a752f6f6dd7d7f4a"
_LSMTOOL_MODULE_SHA256 = (
    "eccb93f128f7be0659e0bb8a433a49e80291661d38f6f4002b5c75fe50dc35d2"
)
_MASTER_WHEEL_SHA256 = (
    "2f1fdfbecd39de93bad53e2a85258959e5114e1f049787ac15c763e8fc8f4d8d"
)
_REFERENCE_VERSIONS = {
    "release": "1.14.1",
    "master": "1.14.2.dev40+gc70103be3",
}


def _parse_args() -> argparse.Namespace:
    """Parse a matched baseline campaign."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container-image", required=True)
    parser.add_argument(
        "--reference", choices=("release", "master"), required=True
    )
    parser.add_argument("--master-wheel", type=Path)
    parser.add_argument("--rapthor-repo", required=True, type=Path)
    parser.add_argument("--lsmtool-repo", required=True, type=Path)
    parser.add_argument("--flat-noise-image", required=True, type=Path)
    parser.add_argument("--true-sky-image", required=True, type=Path)
    parser.add_argument("--true-skymodel", type=Path)
    parser.add_argument("--apparent-skymodel", type=Path)
    parser.add_argument("--vertices", type=Path)
    parser.add_argument("--beam-ms", action="append", default=[], type=Path)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument(
        "--detection-threshold-sigma", required=True, type=float
    )
    parser.add_argument("--island-threshold-sigma", required=True, type=float)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--warmups", default=1, type=int)
    parser.add_argument("--repetitions", default=5, type=int)
    parser.add_argument("--ncores", default=4, type=int)
    parser.add_argument("--finalize-existing", action="store_true")
    return parser.parse_args()


def _require_path(path: Path | None, description: str) -> None:
    """Fail before starting containers when a requested input is absent."""
    if path is not None and not path.exists():
        raise FileNotFoundError(f"{description} does not exist: {path}")


def _container_digest(image: str) -> str:
    """Resolve the immutable local digest used for every repetition."""
    result = subprocess.run(
        ["podman", "image", "inspect", "--format", "{{.Digest}}", image],
        check=True,
        capture_output=True,
        text=True,
    )
    digest = result.stdout.strip()
    if not digest.startswith("sha256:"):
        raise ValueError(f"container image has no immutable digest: {image}")
    return digest


def _mount(command: list[str], source: Path, target: str) -> None:
    """Append one read-only absolute bind mount."""
    command.extend(["-v", f"{source.resolve()}:{target}:ro"])


def _path_sha256(path: Path) -> str:
    """Hash one file or stable directory contents and relative names."""
    digest = hashlib.sha256()
    if path.is_file():
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    paths = sorted(
        item
        for item in path.rglob("*")
        if item.is_file() and item.name != "table.lock"
    )
    for item in paths:
        relative = item.relative_to(path)
        digest.update(str(relative).encode("utf-8"))
        digest.update(b"\0")
        with item.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        digest.update(b"\0")
    return digest.hexdigest()


def _verify_git_checkout(
    repository: Path, expected_commit: str, name: str
) -> dict[str, str]:
    """Verify one clean checkout and return its observed identity."""
    commit = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if commit != expected_commit:
        raise ValueError(
            f"{name} checkout is not the pinned commit: "
            f"expected {expected_commit}, observed {commit}"
        )
    status = subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "status",
            "--porcelain",
            "--untracked-files=all",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if status:
        raise ValueError(f"{name} checkout contains uncommitted changes")
    branch = subprocess.run(
        ["git", "-C", str(repository), "branch", "--show-current"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return {"branch": branch, "commit": commit, "working_tree": "clean"}


def _tool_sha256() -> dict[str, str]:
    """Bind a campaign to the exact scripts that generated and compile it."""
    script_directory = Path(__file__).parent
    return {
        "campaign_runner": _path_sha256(Path(__file__)),
        "evidence_compiler": _path_sha256(
            script_directory / "compile_phase0_pybdsf_evidence.py"
        ),
        "reference_runner": _path_sha256(
            script_directory / "pybdsf_reference_run.py"
        ),
    }


def _input_sha256(args: argparse.Namespace) -> dict[str, str]:
    """Bind every scientific input without recording host-specific paths."""
    inputs = {
        "flat_noise_image": args.flat_noise_image,
        "true_sky_image": args.true_sky_image,
        "true_skymodel": args.true_skymodel,
        "apparent_skymodel": args.apparent_skymodel,
        "vertices": args.vertices,
    }
    identities = {
        name: _path_sha256(path)
        for name, path in inputs.items()
        if path is not None
    }
    identities.update(
        {
            f"beam_ms_{index}": _path_sha256(path)
            for index, path in enumerate(args.beam_ms)
        }
    )
    return identities


def _run_command(
    args: argparse.Namespace, digest: str, index: int
) -> list[str]:
    """Build one isolated container command without host-path leakage."""
    runner = Path(__file__).with_name("pybdsf_reference_run.py")
    output_directory = args.output_directory.resolve()
    command = ["podman", "run", "--rm"]
    _mount(command, runner, "/runner.py")
    _mount(command, args.rapthor_repo, "/rapthor")
    _mount(command, args.lsmtool_repo, "/lsmtool")
    _mount(command, args.flat_noise_image, "/inputs/flat_noise.fits")
    _mount(command, args.true_sky_image, "/inputs/true_sky.fits")
    command.extend(["-v", f"{output_directory}:/output"])
    optional_arguments: list[str] = []
    for value, target, option in (
        (args.true_skymodel, "/inputs/true_sky.txt", "--true-skymodel"),
        (
            args.apparent_skymodel,
            "/inputs/apparent_sky.txt",
            "--apparent-skymodel",
        ),
        (args.vertices, "/inputs/vertices.npy", "--vertices"),
    ):
        if value is not None:
            _mount(command, value, target)
            optional_arguments.extend([option, target])
    for beam_index, beam_ms in enumerate(args.beam_ms):
        target = f"/inputs/beam-{beam_index}.ms"
        _mount(command, beam_ms, target)
        optional_arguments.extend(["--beam-ms", target])

    reference_commit = (
        _RELEASE_COMMIT if args.reference == "release" else _MASTER_COMMIT
    )
    runner_arguments = [
        "--flat-noise-image",
        "/inputs/flat_noise.fits",
        "--true-sky-image",
        "/inputs/true_sky.fits",
        "--output-directory",
        f"/output/rep-{index:02d}",
        "--reference",
        args.reference,
        "--reference-commit",
        reference_commit,
        "--rapthor-commit",
        _RAPTHOR_COMMIT,
        "--lsmtool-commit",
        _LSMTOOL_COMMIT,
        "--container-image-digest",
        digest,
        "--dataset-id",
        args.dataset_id,
        "--detection-threshold-sigma",
        str(args.detection_threshold_sigma),
        "--island-threshold-sigma",
        str(args.island_threshold_sigma),
        "--repetition-index",
        str(index),
        "--ncores",
        str(args.ncores),
        "--reference-version",
        _REFERENCE_VERSIONS[args.reference],
        "--lsmtool-module-sha256",
        _LSMTOOL_MODULE_SHA256,
        *optional_arguments,
    ]
    if index < args.warmups:
        runner_arguments.append("--warmup")

    if args.reference == "master":
        if args.master_wheel is None:
            raise ValueError(
                "--master-wheel is required for the master reference"
            )
        master_wheel_target = f"/wheels/{args.master_wheel.name}"
        if _path_sha256(args.master_wheel) != _MASTER_WHEEL_SHA256:
            raise ValueError("master wheel does not match the pinned SHA-256")
        _mount(command, args.master_wheel, master_wheel_target)
    else:
        master_wheel_target = ""

    command.append(args.container_image)
    if args.reference == "release":
        command.extend(
            [
                "env",
                "PYTHONPATH=/lsmtool:/rapthor",
                "python3",
                "/runner.py",
            ]
        )
        command.extend(runner_arguments)
        return command

    command.extend(
        [
            "sh",
            "-c",
            (
                "wheel=$1; shift; "
                "python3 -m pip install --quiet --no-deps --target "
                '/tmp/master-site "$wheel" && '
                "PYTHONPATH=/tmp/master-site:/lsmtool:/rapthor "
                'python3 /runner.py "$@"'
            ),
            "runner",
            master_wheel_target,
            *runner_arguments,
        ]
    )
    return command


def _load_run(path: Path) -> dict[str, object]:
    """Load one raw repetition document."""
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise TypeError(f"run document is not an object: {path}")
    return document


def _artifact_identity(run_path: Path, name: str) -> str:
    """Return a repeatability identity, excluding LSMTool history times."""
    artifact_path = run_path.parent / name
    if name not in {"apparent_sky.txt", "true_sky.txt"}:
        return hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    scientific_lines = [
        line
        for line in artifact_path.read_text(encoding="utf-8").splitlines()
        if not line.startswith("#")
    ]
    payload = "\n".join(scientific_lines).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_campaign(run_paths: list[Path]) -> None:
    """Reject drift between supposedly matched isolated repetitions."""
    documents = [_load_run(path) for path in run_paths]
    stable_fields = (
        "configuration_sha256",
        "container_image_digest",
        "dataset",
        "dependency_inventory_sha256",
        "environment_sha256",
        "ncores",
        "reference",
        "software",
    )
    reference = documents[0]
    for document in documents[1:]:
        for field in stable_fields:
            if document.get(field) != reference.get(field):
                raise RuntimeError(
                    f"campaign field {field!r} changed between repetitions"
                )
    artifact_names = set(reference["artifacts"])
    for document in documents[1:]:
        if set(document["artifacts"]) != artifact_names:
            raise RuntimeError("campaign artifact names changed")
    for name in artifact_names:
        identities = {
            _artifact_identity(run_path, name) for run_path in run_paths
        }
        if len(identities) != 1:
            raise RuntimeError(
                f"campaign artifact {name!r} changed between repetitions"
            )


def _campaign_run_paths(
    output_directory: Path, total: int
) -> tuple[list[str], list[Path]]:
    """Return ordered relative and absolute raw run paths."""
    relative = [f"rep-{index:02d}/run.json" for index in range(total)]
    absolute = [output_directory / path for path in relative]
    return relative, absolute


def main() -> None:
    """Run one warm-up and the requested measured repetitions."""
    args = _parse_args()
    if args.warmups < 1 or args.repetitions < 1:
        raise ValueError("warmups and repetitions must be positive")
    if not (
        args.detection_threshold_sigma > 0
        and 0 < args.island_threshold_sigma <= args.detection_threshold_sigma
    ):
        raise ValueError("thresholds must satisfy 0 < island <= detection")
    for path, description in (
        (args.rapthor_repo, "Rapthor repository"),
        (args.lsmtool_repo, "LSMTool repository"),
        (args.flat_noise_image, "flat-noise image"),
        (args.true_sky_image, "true-sky image"),
        (args.true_skymodel, "true-sky model"),
        (args.apparent_skymodel, "apparent-sky model"),
        (args.vertices, "vertices"),
        (args.master_wheel, "master wheel"),
    ):
        _require_path(path, description)
    for beam_ms in args.beam_ms:
        _require_path(beam_ms, "beam Measurement Set")
    rapthor_checkout = _verify_git_checkout(
        args.rapthor_repo, _RAPTHOR_COMMIT, "Rapthor"
    )
    lsmtool_checkout = _verify_git_checkout(
        args.lsmtool_repo, _LSMTOOL_COMMIT, "LSMTool"
    )
    if args.finalize_existing:
        if not args.output_directory.is_dir():
            raise FileNotFoundError(
                "cannot finalize an absent campaign directory: "
                f"{args.output_directory}"
            )
    else:
        args.output_directory.mkdir(parents=True, exist_ok=False)
    digest = _container_digest(args.container_image)
    total = args.warmups + args.repetitions
    relative_run_paths, absolute_run_paths = _campaign_run_paths(
        args.output_directory,
        total,
    )
    if not args.finalize_existing:
        for index in range(total):
            kind = "warm-up" if index < args.warmups else "measured"
            print(
                f"[{index + 1}/{total}] {args.reference} {kind} repetition",
                flush=True,
            )
            subprocess.run(_run_command(args, digest, index), check=True)
    _validate_campaign(absolute_run_paths)
    index_document = {
        "container_image": args.container_image,
        "container_image_digest": digest,
        "dataset_id": args.dataset_id,
        "input_sha256": _input_sha256(args),
        "lsmtool_checkout": lsmtool_checkout,
        "ncores": args.ncores,
        "rapthor_checkout": rapthor_checkout,
        "reference": args.reference,
        "repetitions": args.repetitions,
        "runs": relative_run_paths,
        "schema_version": 1,
        "scientific_identity_normalization": {
            "apparent_sky.txt": "LSMTool history comments excluded",
            "true_sky.txt": "LSMTool history comments excluded",
        },
        "tool_sha256": _tool_sha256(),
        "tree_hash_exclusions": ["table.lock"],
        "warmups": args.warmups,
    }
    (args.output_directory / "baseline-index.json").write_text(
        json.dumps(index_document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
