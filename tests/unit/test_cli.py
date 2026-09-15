"""Tests for the command-line interface."""

import re
import subprocess
import sys

import pytest

from hebog.cli import main


def test_version_option(capsys: pytest.CaptureFixture[str]) -> None:
    """The CLI exposes the installed package version."""
    with pytest.raises(SystemExit) as error:
        main(["--version"])

    assert error.value.code == 0
    assert re.search(r"hebog \d+\.\d+\.\d+", capsys.readouterr().out)


def test_version_without_package_metadata_is_explicitly_unknown() -> None:
    """A source tree without metadata never reports a stale release number."""
    script = (
        "import importlib.metadata as metadata\n"
        "def missing(name):\n"
        "    raise metadata.PackageNotFoundError(name)\n"
        "metadata.version = missing\n"
        "import hebog\n"
        "print(hebog.__version__)\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        check=True,
        text=True,
    )

    assert completed.stdout.strip() == "0+unknown"
