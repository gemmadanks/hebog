# Scientific readiness

**Current status: not established for the development finder.** General
scientific readiness requires exact candidate-bound evidence and independent
acceptance. It is separate from the smaller
[experimental package release](release-status.md#release-boundaries) checklist.
Neither development closeout nor an experimental release changes a scientific
verdict or authorizes default Rapthor cutover.

## Remaining scientific acceptance work

1. Verify the current cumulative terminal and resolve or explicitly classify
   its scientific failures, underpowered comparisons and public-output risks.
   Classification does not turn a binding non-pass into a pass.
2. Establish cumulative parity/retention for one exact candidate under its
   prospective reviewed contract, then fresh held-out/public evidence with
   populations and power fixed before viewing results. Closed campaigns are
   immutable and are not reused as confirmation.
3. Confirm installed public API behaviour, product/schema/provenance validity,
   Serial/existing-Dask determinism and the applicable engineering evidence.
4. Prepare a current-candidate scientific-readiness packet and obtain separate
   radio-astronomy and engineering acceptances bound to that same packet.
   Every required machine gate must pass; missing, malformed or failing
   evidence cannot be replaced by reviewer approval.

The [implementation plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md)
tracks these as separate tasks. The restricted Rapthor profile, consumer
acceptance and complete `filter_skymodel` performance belong in a later
integration-readiness packet.

## Existing command and frozen contract

The existing
[Phase 5 readiness contract](https://github.com/gemmadanks/hebog/blob/main/config/contracts/phase-5-readiness.json)
and `scripts/validation/review_phase5_readiness.py` remain frozen tooling for
an older candidate/evidence composition. That contract also requires the
restricted Rapthor profile. It does **not** implement the current separation
of standalone scientific readiness and Rapthor integration, and it cannot
certify v15 or serve as an experimental package release checklist.

A prospective update to the readiness composition is a remaining engineering
task before scientific promotion. Preserve the old contract and decisions;
do not change their booleans, bypass missing artifacts or point the old packet
at a successor candidate to obtain a pass.

The maintained acceptance design has two operations: `prepare` verifies
terminal evidence and binds it in a review packet; `finalize` re-verifies that
packet and requires one independent acceptance for each reviewer role. Both
acceptances must bind the identical packet digest with no blocking findings.
Finalization is a scientific decision and does not itself publish a package
or change a Rapthor default.

Historical command examples and campaign-specific records remain accessible
in [Git history](https://github.com/gemmadanks/hebog/blob/0ce253cf26a7954a58dc9a211eb01d8502e69025/docs/reference/phase-5-release-readiness.md).
For current evidence, use the [campaign overview](phase-5-campaign-overview.md)
and [execution log](https://github.com/gemmadanks/hebog/blob/main/LOG.md).
