"""Launch admission must bind the full late-evaluation contract."""

from __future__ import annotations

import copy
import importlib
import sys
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).parents[3]))
admission: Any = importlib.import_module(
    "scripts.validation.source_catalogue_replacement_admission"
)


def _implementations() -> list[dict[str, Any]]:
    return [
        {
            "identifier": finder,
            "role": "candidate" if finder == "current-hebog" else "reference",
            "execution_configuration_sha256": "a" * 64,
            "software": {
                "name": "hebog",
                "commit_sha": "b" * 40,
                "source_tree_sha256": "c" * 64,
                "dependency_inventory_sha256": "d" * 64,
            },
        }
        for finder in (
            "current-hebog",
            "incumbent-hebog",
            "released-pybdsf",
            "pinned-pybdsf-master",
            "aegean",
        )
    ]


def test_late_aggregate_identities_replace_only_the_current_candidate() -> (
    None
):
    original = _implementations()
    preserved = copy.deepcopy(original)
    candidate = {
        "revision": "e" * 40,
        "source_tree_sha256": "f" * 64,
        "configuration_sha256": "1" * 64,
    }
    result = admission.replacement_implementations(
        original, candidate, "2" * 64
    )
    assert original == preserved
    assert result[1:] == original[1:]
    assert result[0]["software"]["commit_sha"] == candidate["revision"]
    assert (
        result[0]["software"]["source_tree_sha256"]
        == (candidate["source_tree_sha256"])
    )
    assert (
        result[0]["execution_configuration_sha256"]
        == (candidate["configuration_sha256"])
    )


@pytest.mark.parametrize("mutation", ("missing", "duplicate", "foreign"))
def test_late_aggregate_identity_census_is_complete(mutation: str) -> None:
    original = _implementations()
    if mutation == "missing":
        original.pop()
    elif mutation == "duplicate":
        original.append(original[0])
    else:
        original[-1]["identifier"] = "unapproved-finder"
    with pytest.raises(ValueError, match="implementation census"):
        admission.replacement_implementations(original, {}, "2" * 64)


@pytest.mark.parametrize(
    "changed", (None, "status", "plan", "count", "bool", "identity")
)
def test_exact_authority_cannot_be_reused_or_substituted(
    changed: str | None,
) -> None:
    plan = {"path": "plan.json", "sha256": "a" * 64}
    review = {"path": "review.json", "sha256": "b" * 64}
    decision = {
        "status": "authorized-for-one-current-only-replacement-replay",
        "plan_sha256": plan["sha256"],
        "identity_review_sha256": review["sha256"],
        "expected_execution_sha256": "c" * 64,
        "execution_count": 1,
    }
    if changed:
        key, value = {
            "status": ("status", "old-approval"),
            "plan": ("plan_sha256", "d" * 64),
            "count": ("execution_count", 2),
            "bool": ("execution_count", True),
            "identity": ("identity_review_sha256", "e" * 64),
        }[changed]
        decision[key] = value
        with pytest.raises(PermissionError, match="one-use"):
            admission.verify_authority(plan, review, "c" * 64, decision)
    else:
        admission.verify_authority(plan, review, "c" * 64, decision)


@pytest.mark.parametrize("occupied", (None, "scratch", "output", "symlink"))
def test_launch_paths_are_write_once(
    tmp_path: Path, occupied: str | None
) -> None:
    root = tmp_path / "checkout"
    root.mkdir()
    scratch = tmp_path / "scratch"
    output = root / "benchmark-results/terminal.json"
    if occupied == "scratch":
        scratch.mkdir()
    elif occupied == "output":
        output.parent.mkdir()
        output.write_text("preserve")
    elif occupied == "symlink":
        scratch.symlink_to(tmp_path / "absent")
    plan: dict[str, Any] = {
        "execution_root": str(root),
        "scratch": str(scratch),
        "output": str(output),
        "protected_roots": [],
    }
    if occupied:
        with pytest.raises((ValueError, FileExistsError)):
            admission.verify_namespace(plan)
    else:
        admission.verify_namespace(plan)
        assert not scratch.exists() and not output.exists()


@pytest.mark.parametrize("path", ("checkout", "checkout/nested", "outside"))
def test_launch_rejects_namespace_overlap(tmp_path: Path, path: str) -> None:
    root = tmp_path / "checkout"
    plan: dict[str, Any] = {
        "execution_root": str(root),
        "scratch": str(tmp_path / path),
        "output": str(root / "benchmark-results/out.json"),
        "protected_roots": [],
    }
    if path == "outside":
        plan["output"] = str(tmp_path / "out.json")
    with pytest.raises(ValueError, match="namespace"):
        admission.verify_namespace(plan)


@pytest.mark.parametrize(
    "field",
    (
        None,
        "root",
        "source",
        "program",
        "revision",
        "import",
        "runtime",
        "python",
        "platform",
        *admission.THREAD_VARIABLES,
    ),
)
def test_code_runtime_and_imports_must_be_immutable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str | None
) -> None:
    for name, value in (
        ("repository_revision", "revision"),
        ("source_tree_sha256", "source"),
        ("program_hashes", {"file": "hash"}),
        ("dependency_inventory_sha256", "runtime"),
    ):
        monkeypatch.setattr(
            admission, name, Mock(return_value=value), raising=False
        )
    monkeypatch.setattr(
        admission.hebog, "__file__", str(tmp_path / "src/hebog/__init__.py")
    )
    for name in admission.THREAD_VARIABLES:
        monkeypatch.setenv(name, "1")
    plan: dict[str, Any] = {
        "execution_root": str(tmp_path),
        "execution_revision": "revision",
        "candidate": {"source_tree_sha256": "source"},
        "program_sha256": {"file": "hash"},
        "runtime": {
            "python": admission.platform.python_version(),
            "platform": admission.platform.platform(),
            "dependency_inventory_sha256": "runtime",
        },
    }
    locations: dict[str, tuple[str, Any]] = {
        "root": ("execution_root", str(tmp_path / "foreign")),
        "program": ("program_sha256", {}),
        "revision": ("execution_revision", "other"),
    }
    if field in locations:
        key, value = locations[field]
        plan[key] = value
    elif field == "source":
        plan["candidate"]["source_tree_sha256"] = "other"
    elif field == "import":
        monkeypatch.setattr(
            admission.hebog, "__file__", "/wrong/hebog/__init__.py"
        )
    elif field == "runtime":
        plan["runtime"]["dependency_inventory_sha256"] = "other"
    elif field in {"python", "platform"}:
        plan["runtime"][field] = "other"
    elif field in admission.THREAD_VARIABLES:
        assert field is not None
        monkeypatch.delenv(field)
    if field:
        with pytest.raises(ValueError, match=r"immutable|runtime"):
            admission.verify_execution_code(plan, tmp_path)
    else:
        admission.verify_execution_code(plan, tmp_path)


@pytest.mark.parametrize(
    "boundary",
    (
        "scratch-relative",
        "output-relative",
        "root-relative",
        "ancestor",
        "root-symlink",
        "output-symlink",
        "parent-symlink",
        "protected-root",
        "protected-scratch",
        "protected-ancestor",
    ),
)
def test_namespaces_reject_aliases_and_preserve_original_stores(
    tmp_path: Path,
    boundary: str,
) -> None:
    root = tmp_path / "checkout"
    root.mkdir()
    scratch = tmp_path / "scratch"
    output = root / "benchmark-results/terminal.json"
    protected: list[str] = []
    if boundary == "scratch-relative":
        scratch = Path("relative")
    elif boundary == "output-relative":
        output = Path("relative.json")
    elif boundary == "root-relative":
        root = Path("relative")
    elif boundary == "ancestor":
        scratch = root.parent
    elif boundary == "root-symlink":
        alias = tmp_path / "alias"
        alias.symlink_to(root)
        root = alias
    elif boundary == "output-symlink":
        output.parent.mkdir()
        output.symlink_to(tmp_path / "absent")
    elif boundary == "parent-symlink":
        alias = tmp_path / "alias"
        alias.symlink_to(tmp_path)
        scratch = alias / "scratch"
    else:
        protected = [
            str(
                {
                    "protected-root": root,
                    "protected-scratch": scratch,
                    "protected-ancestor": root / "historical",
                }[boundary]
            )
        ]
    with pytest.raises((ValueError, FileExistsError)):
        admission.verify_namespace(
            {
                "execution_root": str(root),
                "scratch": str(scratch),
                "output": str(output),
                "protected_roots": protected,
            }
        )
