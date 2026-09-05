#!/usr/bin/env python3
"""Verify and evaluate the sealed version-8 cumulative products."""

# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnusedFunction=false

from __future__ import annotations

import argparse
import importlib
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, cast

from hebog.validation.external_runners import file_sha256

_ROOT = Path(__file__).parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_BASE_COMPLETION = (
    _ROOT / "scripts/validation/complete_phase5_final_cumulative_evaluation.py"
)
_BASE_COMPLETION_SHA256 = (
    "1fcbc321258414bb6eb27a07ce2f36cacf7c6d9f4e61da1e2fb5525deacace6c"
)
_EVALUATOR = (
    _ROOT
    / "scripts/validation/evaluate_phase5_public_owner_domain_cumulative.py"
)
_REFERENCE_RECONSTRUCTION = Path(
    "benchmark-results/phase-5/"
    "viewed-reference-reconstruction-public-finder-correction"
)
_SOURCE_REQUEST = Path(
    "benchmark-results/phase-5/external-post-failure-comparison/"
    "campaign-request.json"
)
_POPULATION = Path(
    "config/contracts/phase-5-prospective-paired-population.json"
)
_CURRENT_SCRATCH = Path(
    "/private/tmp/hebog-phase5-public-owner-domain-cumulative-95cfc76"
)
_INCUMBENT_SCRATCH = Path(
    "/private/tmp/hebog-phase5-prospective-paired-incumbent-authentic-85d5807"
)
_RECONSTRUCTION_RECORD = Path(
    "benchmark-results/phase-5/"
    "prospective-paired-incumbent-reconstruction.json"
)
_PRODUCT_SEAL = Path(
    "benchmark-results/phase-5/public-owner-domain-cumulative-product-set.json"
)
_PREFIX = "phase-5-public-owner-domain-cumulative-evaluation"
_IDENTITY = Path(f"config/contracts/{_PREFIX}-identity-review.json")
_IMPLEMENTATION = Path(
    f"config/contracts/{_PREFIX}-implementation-decision.json"
)
_EXECUTION_DECISION = Path(
    f"config/contracts/{_PREFIX}-execution-decision.json"
)
_OUTPUT = Path(
    "benchmark-results/phase-5/public-owner-domain-cumulative-decision.json"
)
_CURRENT_REVISION = "95cfc76ded56556dc3ad6894410962d34f0d5604"
_CURRENT_SOURCE_TREE_SHA256 = (
    "8da21e86afc5035da0704724a9d29104ea8b0e4d55fa4a98f0c5f3efca9a75a5"
)
_CURRENT_CONFIGURATION_SHA256 = (
    "2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d"
)
_CURRENT_PRODUCT_SET_SHA256 = (
    "f43cb2741e3d66a51bd71baccc6f090199af02eb0784d08cb4295613f17758ed"
)
_CURRENT_PRODUCT_SEAL_SHA256 = (
    "194022abbfc2633a2e9e323463eeee235ebc521e43d229dd3884a826e0e7a29b"
)
_CURRENT_PRODUCT_SEAL_CANONICAL_SHA256 = (
    "50961efd5b04fc9c92bac4a60b2b178dea9d1b38eb70b96c1d008598ad3df20f"
)
_CURRENT_REPLAY_IDENTITY_SHA256 = (
    "0a464a387d5e742d213eb9045743e1356f5c9510b2409cdd10e6c0efc24534a0"
)
_CURRENT_REPLAY_DECISION_SHA256 = (
    "5662241eab2112f230009743145c2b8c6bfc5136852814d73baed5b00d26de1f"
)


def _base_module() -> Any:
    """Load the exact historical completion module."""
    if file_sha256(_BASE_COMPLETION) != _BASE_COMPLETION_SHA256:
        raise ValueError("public owner-domain base completion changed")
    return importlib.import_module(
        "scripts.validation.complete_phase5_final_cumulative_evaluation"
    )


_BASE = _base_module()
_BASE_GLOBALS = vars(_BASE)
_AUTHORIZATION = cast(dict[str, bool], _BASE._AUTHORIZATION)
_INCUMBENT_CONFIGURATION_SHA256 = cast(
    str, _BASE._INCUMBENT_CONFIGURATION_SHA256
)
_INCUMBENT_EVALUATOR_PRODUCT_SET_SHA256 = cast(
    str, _BASE._INCUMBENT_EVALUATOR_PRODUCT_SET_SHA256
)
_INCUMBENT_REVISION = cast(str, _BASE._INCUMBENT_REVISION)
_INCUMBENT_SOURCE_TREE_SHA256 = cast(str, _BASE._INCUMBENT_SOURCE_TREE_SHA256)


@contextmanager
def _configured_completion() -> Generator[dict[str, Any]]:
    """Apply version-8 product bindings and restore the closed parent."""
    previous = dict(_BASE_GLOBALS)
    historical_terminal = cast(Path, previous["_HISTORICAL_TERMINAL"])
    if not historical_terminal.is_absolute():
        historical_terminal = _ROOT / historical_terminal
    try:
        _BASE_GLOBALS.update(
            {
                "__file__": str(Path(__file__).resolve()),
                "_ROOT": _ROOT,
                "_EVALUATOR": _EVALUATOR,
                "_HISTORICAL_TERMINAL": historical_terminal,
                "_CURRENT_SCRATCH": _CURRENT_SCRATCH,
                "_PRODUCT_SEAL": _PRODUCT_SEAL,
                "_IDENTITY": _IDENTITY,
                "_IMPLEMENTATION": _IMPLEMENTATION,
                "_EXECUTION_DECISION": _EXECUTION_DECISION,
                "_OUTPUT": _OUTPUT,
                "_CURRENT_REVISION": _CURRENT_REVISION,
                "_CURRENT_SOURCE_TREE_SHA256": _CURRENT_SOURCE_TREE_SHA256,
                "_CURRENT_CONFIGURATION_SHA256": (
                    _CURRENT_CONFIGURATION_SHA256
                ),
                "_CURRENT_PRODUCT_SET_SHA256": _CURRENT_PRODUCT_SET_SHA256,
                "_CURRENT_PRODUCT_SEAL_SHA256": (_CURRENT_PRODUCT_SEAL_SHA256),
                "_CURRENT_PRODUCT_SEAL_CANONICAL_SHA256": (
                    _CURRENT_PRODUCT_SEAL_CANONICAL_SHA256
                ),
                "_CURRENT_REPLAY_IDENTITY_SHA256": (
                    _CURRENT_REPLAY_IDENTITY_SHA256
                ),
                "_CURRENT_REPLAY_DECISION_SHA256": (
                    _CURRENT_REPLAY_DECISION_SHA256
                ),
            }
        )
        yield _BASE_GLOBALS
    finally:
        _BASE_GLOBALS.clear()
        _BASE_GLOBALS.update(previous)


def _expected_parent_products() -> dict[str, object]:
    """Return the exact inherited product-verifier expectation."""
    with _configured_completion() as parent:
        return cast(dict[str, object], parent["_expected_parent_products"]())


def expected_verified_products() -> dict[str, object]:
    """Return every frozen product and parent-program identity."""
    with _configured_completion() as parent:
        return cast(dict[str, object], parent["expected_verified_products"]())


def verify_products(arguments: argparse.Namespace) -> dict[str, object]:
    """Rehash both candidates and all retained references without writes."""
    with _configured_completion() as parent:
        return cast(dict[str, object], parent["verify_products"](arguments))


def run_bounded_terminal_smoke(directory: Path) -> dict[str, object]:
    """Exercise the exact terminal seams on retained smoke evidence."""
    with _configured_completion() as parent:
        return cast(
            dict[str, object],
            parent["run_bounded_terminal_smoke"](directory),
        )


def expected_bounded_smoke() -> dict[str, object]:
    """Run the bounded terminal smoke in a temporary directory."""
    with _configured_completion() as parent:
        return cast(dict[str, object], parent["expected_bounded_smoke"]())


def bounded_smoke_summary(record: dict[str, object]) -> dict[str, object]:
    """Return the compact frozen smoke summary."""
    with _configured_completion() as parent:
        return cast(dict[str, object], parent["bounded_smoke_summary"](record))


def _expected_execution(
    verified: dict[str, object], smoke: dict[str, object]
) -> dict[str, object]:
    """Return the exact evaluation-only execution identity."""
    with _configured_completion() as parent:
        return cast(
            dict[str, object], parent["_expected_execution"](verified, smoke)
        )


def _evaluator_command(arguments: argparse.Namespace) -> list[str]:
    """Return the inherited evaluator-only subprocess command."""
    with _configured_completion() as parent:
        return cast(list[str], parent["_evaluator_command"](arguments))


def run_authorized_evaluation(arguments: argparse.Namespace) -> None:
    """Verify all inputs and consume only exact evaluation authority."""
    with _configured_completion() as parent:
        parent["run_authorized_evaluation"](arguments)


def _parse_args() -> argparse.Namespace:
    """Parse the fixed evaluation, verification, or smoke invocation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=_ROOT)
    parser.add_argument(
        "--reference-reconstruction",
        type=Path,
        default=_REFERENCE_RECONSTRUCTION,
    )
    parser.add_argument("--source-request", type=Path, default=_SOURCE_REQUEST)
    parser.add_argument("--population", type=Path, default=_POPULATION)
    parser.add_argument(
        "--current-scratch", type=Path, default=_CURRENT_SCRATCH
    )
    parser.add_argument(
        "--incumbent-scratch", type=Path, default=_INCUMBENT_SCRATCH
    )
    parser.add_argument(
        "--reconstruction-record",
        type=Path,
        default=_RECONSTRUCTION_RECORD,
    )
    parser.add_argument("--product-seal", type=Path, default=_PRODUCT_SEAL)
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--smoke-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Run smoke, complete verification, or the exact evaluation."""
    arguments = _parse_args()
    if arguments.smoke_only:
        print(
            json.dumps(
                bounded_smoke_summary(expected_bounded_smoke()),
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
        )
        return
    if arguments.verify_only:
        print(
            json.dumps(
                verify_products(arguments),
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
        )
        return
    run_authorized_evaluation(arguments)


if __name__ == "__main__":
    main()
