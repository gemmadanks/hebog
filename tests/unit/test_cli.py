"""Tests for the command-line interface."""

import pytest

from hebog.cli import main


def test_version_option(capsys: pytest.CaptureFixture[str]) -> None:
    """The CLI exposes the installed package version."""
    with pytest.raises(SystemExit) as error:
        main(["--version"])

    assert error.value.code == 0
    assert "hebog 0.1.0" in capsys.readouterr().out
