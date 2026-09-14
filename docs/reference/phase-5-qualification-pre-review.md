# Phase 5 qualification design pre-review

**Decision:** do not open the checked-in 400-image Phase 5 qualification
manifest. It remains untouched, but it is too small and too narrow for the
current endpoint-specific power requirement. Named scientific approval on
2026-08-25 selected the closed compact evidence and froze a fresh,
four-geometry replacement. The one approved campaign and the separately
authorized evaluation repair have now completed. Terminal decision SHA-256
`d4db4d7f...` is `pass`: all 143 Continuum absolute endpoints, all 226
applicable paired comparisons, and both separately bound compact records pass.
Cutover and release remain unauthorized.

## Evidence

The checked-in `phase-5-qualification.json` has SHA-256
`40f1d0cfd173947e323cc35ff140c04f25fdd5c8303fbab8c138dc058fb0235f`.
It defines 400 independent realizations of one beam/WCS geometry. No
qualification image or finder result has been generated or inspected.

The prospective recovery power review has SHA-256
`bbfab3a0781c8a12083190d8c591152d5c461a45824bab6cba39e770915af9fc`.
It binds 226 continuum paired comparisons and, from the complete viewed
regression evidence, calculates:

| Quantity | Reviewed value |
| --- | ---: |
| Minimum continuum realizations | 1,532 |
| Population safety factor | 1.10 |
| Selected continuum realizations | 1,688 |
| Geometries | 4 |
| Realizations per geometry | 422 |
| Combined familywise power lower bound | 0.90508 |
| Required joint power | 0.90 |

The old contract's statement that at least 400 images were required predated
these endpoint-specific variance estimates. Four hundred images cannot be
relabelled as powered merely because the manifest is still unseen. It also
contains only one beam/WCS geometry, whereas the passing power design is
balanced over four.

The write-once no-science audit is
`benchmark-results/phase-5/qualification-design-audit.json`, SHA-256
`9b0fcb89a3ea4a10b791bca3589df8641b672d474e18d4abe0eb59d70292b2dc`.
It reads only the manifest recipe and the already reviewed power summary. It
does not generate or inspect an image, truth result, source-finder output, or
qualification statistic. Its terminal status is
`replacement-design-required` and every execution/opening flag is false.

The approved replacement manifest is
`config/datasets/phase-5-final-qualification-continuum.json`, SHA-256
`7c67127e828a92bc100299cf9ffecd13851e485c4be9e95866e2d0827ebb80df`.
The population freeze is
`config/contracts/phase-5-final-qualification-population.json`, SHA-256
`4a52f55114962d24d6371b166d393c3421a74156fa1c48305931fb39a631e5ac`.
It binds candidate revision `9062664...`, four sets of 422 fresh seeds, and
the passing closed Phase 4U qualification/current compact regression without
pooling or rescoring them.

The prospective run contains 1,688 Continuum inputs and 8,440 runs: Hebog,
released PyBDSF operational and controlled-background, and pinned-master
PyBDSF operational and controlled-background for every image. The 5,064
candidate/operational runs are binding. Aegean's scientifically applicable
compact scope is already closed, so its exact runtime remains one of the four
reviewed identities but its final runner fails closed rather than scheduling
a fresh or scientifically inapplicable Continuum leg.

## Recommended replacement

Freeze a new qualification-role continuum population with:

- 1,688 fresh, seed-disjoint images;
- four reviewed beam/WCS geometries and 422 images per geometry;
- the same governed morphologies, scales, edge, invalid-pixel, varying-noise,
  artifact, tile-edge, and tile-corner strata;
- the current final Hebog source tree and configuration, not an inferred
  historical candidate identity;
- released PyBDSF, pinned PyBDSF master, and Aegean over its declared scope;
- the unchanged absolute and paired endpoint registry and no-compensation
  rules; and
- one terminal opening with no adaptive sample size, rescore, or reuse after
  inspection.

The replacement seeds must be disjoint from every development, regression,
existing qualification, confirmation, external-campaign, and viewed-evidence
seed. The old 400-image manifest is retained as an unopened superseded design
and none of its seeds is reused. This makes the qualification identity and
its four-way balance unambiguous.

The compact Phase 4U qualification and current complete compact regression
remain separate passing evidence. Scientific review selected those closed
records, so no fresh 800-image compact lane is required. They remain
independently hash-bound and are not pooled with the final Continuum result.

## Required sequence

1. ~~Obtain named scientific approval and freeze the replacement population.~~
   Completed on 2026-08-25 without opening qualification.
2. ~~Implement and freeze the final candidate runner, compiler, evaluator,
   endpoint registry, and exact finder runtime identities.~~ Completed under
   identity-review SHA-256 `42ad6237...`; execution remains false.
3. ~~Obtain separate named one-look execution approval bound to review
   `42ad6237...` and every runtime identity.~~ Approved on 2026-08-25. Run the
   complete no-write preflight from the immutable authorization commit and
   execute only if every identity remains unchanged.
4. ~~Execute once, evaluate absolute science before comparisons and runtime,
   and retain a terminal failure without tuning or rescoring.~~ Completed. The
   one campaign sealed as `4badb8e1...`; evaluation-only repair identities
   `42ac2a96...` and `f4396a8a...` preserved the frozen science and produced
   passing decision `d4db4d7f...` without rerunning, tuning, or rescoring.
5. Only after qualification, public evidence, the Rapthor profile, and
   independent scientific and engineering acceptance pass may the Phase 5
   readiness record be published as complete.

## Command

The audit can be reproduced without opening qualification:

```bash
uv run python scripts/validation/review_phase5_qualification_design.py \
  --manifest config/datasets/phase-5-qualification.json \
  --power-review benchmark-results/phase-5/viewed-recovery-power-review.json \
  --output benchmark-results/phase-5/qualification-design-audit.json
```

The output is write-once. A new audit must use a new path rather than
overwriting the reviewed record.
