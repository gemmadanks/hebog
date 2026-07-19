"""Tests for the command-line interface."""

import re

import pytest

from hebog.cli import main


def test_version_option(capsys: pytest.CaptureFixture[str]) -> None:
    """The CLI exposes the installed package version."""
    with pytest.raises(SystemExit) as error:
        main(["--version"])

    assert error.value.code == 0
    assert re.search(r"hebog \d+\.\d+\.\d+", capsys.readouterr().out)
