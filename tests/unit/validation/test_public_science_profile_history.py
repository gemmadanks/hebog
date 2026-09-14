"""Historical identity checks for the immutable public science profile."""

from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
from pathlib import Path

_ROOT = Path(__file__).parents[3]


def test_public_interface_identity_binds_its_historical_file_set() -> None:
    """An immutable interface review remains verifiable after later science."""
    relative_review = Path(
        "config/contracts/"
        "phase-5-configurable-public-interface-identity-review.json"
    )
    review = json.loads((_ROOT / relative_review).read_text(encoding="utf-8"))
    creation_revision = subprocess.run(
        (
            "git",
            "log",
            "--diff-filter=A",
            "--format=%H",
            "--",
            str(relative_review),
        ),
        cwd=_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()[0]

    def historical_bytes(relative_path: str) -> bytes:
        return subprocess.run(
            ("git", "show", f"{creation_revision}:{relative_path}"),
            cwd=_ROOT,
            check=True,
            capture_output=True,
        ).stdout

    assert review["status"] == "frozen-non-executable"
    assert not any(review["authorizations"].values())
    for relative_path, expected in review["interface_file_sha256"].items():
        assert hashlib.sha256(historical_bytes(relative_path)).hexdigest() == (
            expected
        )
    composition = hashlib.sha256()
    for module_name, expected in review["scientific_module_sha256"].items():
        module = importlib.import_module(module_name)
        module_path = Path(module.__file__ or "").relative_to(_ROOT)
        contents = historical_bytes(module_path.as_posix())
        assert hashlib.sha256(contents).hexdigest() == expected
        composition.update(module_name.encode())
        composition.update(b"\0")
        composition.update(contents)
        composition.update(b"\0")

    assert composition.hexdigest() == review["scientific_composition_sha256"]


def test_source_protected_public_identity_binds_historical_science() -> None:
    """The superseded review remains bound to its exact candidate commit."""
    review_path = (
        _ROOT / "config/contracts/"
        "phase-5-adaptive-background-source-protection-"
        "public-interface-identity-review.json"
    )
    contents = review_path.read_bytes()
    review = json.loads(contents)

    assert hashlib.sha256(contents).hexdigest() == (
        "4f8c110fb45ffa151d54bc9c9dfdad1385306101a1e8397718f82a0b43388b81"
    )
    assert review["status"] == "frozen-non-executable"
    assert not any(review["authorizations"].values())
    assert review["algorithm_candidate"] == {
        "configuration_sha256": (
            "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
        ),
        "revision": "7ebde589c82e153e0f7d475a8469c120138be4da",
        "source_tree_sha256": (
            "c83ee5a90c33f9c915b69402710835a5a094d08df83e003f8e2fd0799f23ae2d"
        ),
    }
    candidate_revision = review["algorithm_candidate"]["revision"]

    def historical_bytes(relative_path: str) -> bytes:
        return subprocess.run(
            ("git", "show", f"{candidate_revision}:{relative_path}"),
            cwd=_ROOT,
            check=True,
            capture_output=True,
        ).stdout

    for relative_path, expected in review["interface_file_sha256"].items():
        assert hashlib.sha256(historical_bytes(relative_path)).hexdigest() == (
            expected
        )
    composition = hashlib.sha256()
    for module_name, expected in review["scientific_module_sha256"].items():
        module = importlib.import_module(module_name)
        module_path = Path(module.__file__ or "").relative_to(_ROOT)
        module_contents = historical_bytes(module_path.as_posix())
        assert hashlib.sha256(module_contents).hexdigest() == expected
        composition.update(module_name.encode())
        composition.update(b"\0")
        composition.update(module_contents)
        composition.update(b"\0")

    assert review["scientific_composition"] == (
        "phase-5-configurable-source-protected-adaptive-background-v3"
    )
    assert composition.hexdigest() == review["scientific_composition_sha256"]
