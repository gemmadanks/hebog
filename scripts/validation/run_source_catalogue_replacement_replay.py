"""Launch one admitted current-only replay, or perform its no-write audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.validation.source_catalogue_replacement_admission import (
    verify_authority,
    verify_preflight,
)
from scripts.validation.source_catalogue_replacement_runner import (
    run_replacement,
)
from scripts.validation.source_catalogue_replay_plan import read_bound

from hebog.validation.external_runners import canonical_sha256, file_sha256


def main() -> None:
    """Reject identity drift and consumed namespaces before any capture."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--identity-review", type=Path, required=True)
    parser.add_argument("--identity-review-sha256", required=True)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--authorization-sha256")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    plan_binding = {
        "path": str(args.plan.resolve()),
        "sha256": args.plan_sha256,
    }
    review_binding = {
        "path": str(args.identity_review.resolve()),
        "sha256": args.identity_review_sha256,
    }
    plan, review = read_bound(plan_binding), read_bound(review_binding)
    expected = canonical_sha256(plan)
    if (
        review["plan"] != plan_binding
        or review["expected_execution_sha256"] != expected
        or review["status"] != "frozen-non-executable"
        or any(review["authorizations"].values())
    ):
        raise ValueError("replacement execution review changed")
    authority_binding = None
    if not args.preflight_only:
        if args.authorization is None or args.authorization_sha256 is None:
            raise PermissionError("exact one-use authorization required")
        authority_binding = {
            "path": str(args.authorization.resolve()),
            "sha256": args.authorization_sha256,
        }
        verify_authority(
            plan_binding,
            review_binding,
            expected,
            read_bound(authority_binding),
        )
    verify_preflight(plan, Path(__file__).resolve().parents[2])
    # The exhaustive audit may take minutes. Recheck the write-once approval
    # and small controlling documents immediately before any namespace claim.
    read_bound(plan_binding)
    read_bound(review_binding)
    if authority_binding is not None:
        verify_authority(
            plan_binding,
            review_binding,
            expected,
            read_bound(authority_binding),
        )
    if args.preflight_only:
        print(
            json.dumps(
                {
                    "status": "preflight-pass",
                    "finder_execution_started": False,
                    "plan": plan_binding,
                }
            )
        )
        return
    launch = {
        "plan": plan_binding,
        "identity_review": review_binding,
        "authorization": authority_binding,
        "execution_revision": plan["execution_revision"],
        "python_executable": sys.executable,
        "expected_execution_sha256": expected,
    }
    terminal = run_replacement(plan, launch)
    print(
        json.dumps(
            {
                "output": plan["output"],
                "sha256": file_sha256(Path(plan["output"])),
                "status": terminal["result"]["status"],
            }
        )
    )


if __name__ == "__main__":
    main()
