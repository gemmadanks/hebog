# Phase 5 qualification design pre-review

**Decision:** do not open the checked-in 400-image Phase 5 qualification
manifest. It remains untouched, but it is too small and too narrow for the
current endpoint-specific power requirement. A fresh, four-geometry
replacement must receive named scientific approval before its identities are
frozen. This review neither freezes nor executes that replacement.

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
remain separate passing evidence. Before freezing the replacement, scientific
review must decide whether the final one-look repeats a fresh 800-image compact
lane or binds those closed compact results. That choice affects campaign
power, runtime, and identity and must not be inferred here.

## Required sequence

1. Obtain named scientific approval of the 1,688-image/four-geometry continuum
   design and the compact-evidence choice.
2. Freeze the replacement manifest, candidate source/configuration, exact
   finder runtimes, compiler, evaluator, endpoint registry, and power audit.
3. Produce a no-write preflight review and obtain a separate named one-look
   execution approval bound to every identity.
4. Execute once, evaluate absolute science before comparisons and runtime, and
   retain a terminal failure without tuning or rescoring.
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
