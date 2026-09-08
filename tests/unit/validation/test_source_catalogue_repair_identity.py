"""Verify the repaired candidate without private campaign directories."""

from __future__ import annotations

import ast
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

from hebog.validation.external_runners import canonical_sha256

_ROOT = Path(__file__).parents[3]
_REVIEW = (
    _ROOT
    / "config/contracts/phase-5-source-catalogue-repair-identity-review.json"
)


def test_repair_identity_binds_committed_science_without_outputs() -> None:
    """Later science cannot invalidate or silently rewrite this identity."""
    review = json.loads(_REVIEW.read_bytes())
    assert review["status"] == "frozen-non-executable"
    assert review["finder_execution_started"] is False
    assert review["execution_identity"] is None
    assert not any(review["authorizations"].values())
    candidate = review["algorithm_candidate"]
    archive = subprocess.run(
        ("git", "archive", candidate["revision"]),
        cwd=_ROOT,
        check=True,
        capture_output=True,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as historical:
        records: dict[str, bytes] = {}
        for member in historical.getmembers():
            stream = (
                historical.extractfile(member) if member.isfile() else None
            )
            if stream is not None:
                records[member.name] = stream.read()
    source = hashlib.sha256()
    for name in sorted(records):
        if name.startswith("src/hebog/") and name.endswith(".py"):
            source.update(name.encode() + b"\0" + records[name] + b"\0")
    assert source.hexdigest() == candidate["source_tree_sha256"]
    assert (
        canonical_sha256(review["configuration"])
        == candidate["configuration_sha256"]
    )
    tree = ast.parse(records["src/hebog/public_api.py"])
    constants = {
        target.id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
        and target.id in {"_COMPOSITION_NAME", "_SCIENTIFIC_MODULES"}
    }
    assert constants["_COMPOSITION_NAME"] == review["scientific_composition"]
    composition = hashlib.sha256()
    for module in constants["_SCIENTIFIC_MODULES"]:
        name = "src/" + module.replace(".", "/") + ".py"
        composition.update(module.encode() + b"\0" + records[name] + b"\0")
    assert composition.hexdigest() == review["scientific_composition_sha256"]
    for record in review["frozen_documents"].values():
        assert (
            hashlib.sha256(records[record["path"]]).hexdigest()
            == record["sha256"]
        )
