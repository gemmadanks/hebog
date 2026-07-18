"""Build and verify the pinned PyBDSF master wheel in the reference image."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path

_MASTER_COMMIT = "c70103be3ae9ae9908286f144e6ce956acc0ce5c"
_BUILD_COMMAND = (
    "cp -a /source /tmp/PyBDSF && "
    "cd /tmp/PyBDSF && "
    "python3 -m pip install --quiet "
    "setuptools==80.9.0 scikit-build==0.18.1 "
    "setuptools-scm==9.2.2 meson==1.8.3 && "
    "python3 setup.py bdist_wheel --dist-dir /output"
)


def _parse_args() -> argparse.Namespace:
    """Parse the pinned checkout, container, and expected artifact identity."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pybdsf-repo", required=True, type=Path)
    parser.add_argument("--container-image", required=True)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--expected-commit", default=_MASTER_COMMIT)
    return parser.parse_args()


def _git(repo: Path, *arguments: str) -> str:
    """Run one read-only Git query against the PyBDSF checkout."""
    return subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _sha256(path: Path) -> str:
    """Return one complete wheel digest."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    """Build exactly one wheel and verify its pinned provenance."""
    args = _parse_args()
    if _git(args.pybdsf_repo, "rev-parse", "HEAD") != args.expected_commit:
        raise ValueError("PyBDSF checkout is not at the expected commit")
    if _git(args.pybdsf_repo, "status", "--porcelain"):
        raise ValueError("PyBDSF checkout must be clean")
    args.output_directory.mkdir(parents=True, exist_ok=False)
    subprocess.run(
        [
            "podman",
            "run",
            "--rm",
            "-v",
            f"{args.pybdsf_repo.resolve()}:/source:ro",
            "-v",
            f"{args.output_directory.resolve()}:/output",
            args.container_image,
            "sh",
            "-c",
            _BUILD_COMMAND,
        ],
        check=True,
    )
    wheels = tuple(args.output_directory.glob("*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"expected one wheel, found {len(wheels)}")
    observed_sha256 = _sha256(wheels[0])
    if observed_sha256 != args.expected_sha256:
        raise ValueError(
            "wheel SHA-256 differs from the frozen platform artifact: "
            f"{observed_sha256}"
        )
    print(f"{wheels[0].name} sha256:{observed_sha256}")


if __name__ == "__main__":
    main()
