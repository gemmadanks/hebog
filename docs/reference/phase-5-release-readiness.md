# Phase 5 release readiness

Phase 5 is not complete merely because one scientific campaign or benchmark
passes. The readiness boundary requires all machine evidence first and then
two independent acceptances bound to the exact same review packet. Completing
Phase 5 still does not authorize Rapthor cutover, a release, tuning, rescoring,
optimization, or another campaign.

The machine contract is
[`config/contracts/phase-5-readiness.json`](https://github.com/gemmadanks/hebog/blob/main/config/contracts/phase-5-readiness.json).
It names every required artifact, required terminal field, predeclared file
identity where one already exists, the exact readiness library and command
identities, reviewer ownership, review question, and prohibited authorization.

## Two-stage boundary

The readiness command has two explicit operations:

1. `prepare` verifies every present artifact and freezes their SHA-256
   identities into a review packet. Missing artifacts remain named blockers.
   A complete packet is only `ready-for-independent-review`; it never marks
   Phase 5 complete.
2. `finalize` rebuilds the packet from the live contract and evidence, requires
   byte equality with the reviewed packet, and accepts exactly one independent
   radio-astronomy record and one independent engineering record. Both records
   must bind the packet SHA-256, contain no blocking findings, accept the Phase
   5 milestone, and keep cutover and release false.

Present but malformed, failing, moved, or checksum-drifted evidence is an
error. It is not treated like an absent optional result. Human acceptance
cannot compensate for a missing machine gate, and one reviewer cannot satisfy
both roles.

## Required evidence

The packet requires:

- the public-finder correction cumulative ledger, with the exact correction
  candidate and configuration, every required endpoint passing, readiness
  true, and no compact or Continuum like-semantics regression;
- a fresh held-out qualification decision for that corrected candidate;
- the restricted-input Rapthor profile decision with complete safety-stratum
  coverage;
- the reviewed 3,000-pixel incremental performance budget;
- the bounded deterministic execution contract;
- the passing closed final-qualification context;
- the immutable terminal public-finder failure; and
- the independent scientific review that diagnosed that failure without
  tuning or rescoring it.

The terminal SDC1/Hydra failure is deliberately included. The packet cannot
erase it or relabel it as a pass. The radio-astronomy reviewer must decide
whether the corrected cumulative and fresh held-out evidence support the
claimed capability while the viewed public result remains scoped as terminal
development evidence.

The first corrected cumulative replay now exists and is terminally failing:
compact passes, but Continuum records 44 failed endpoints, 10 underpowered
endpoints, and 37 like-semantics regressions. Because failing evidence is not
equivalent to missing evidence, `prepare` aborts rather than producing a
reviewable packet. Fresh correction qualification and the Rapthor profile also
remain absent. The command cannot publish a Phase 5 completion record until a
separately reviewed candidate passes every gate.

The later source-association measurement-repair replay completed all 2,400
candidate products but did not publish a ledger: its compiler rejected the new
binding source identity at the stale single-segment adapter. Those products are
preserved for a fail-closed evaluation-only completion. They are not passing
evidence, and readiness remains blocked until an exactly approved repair
publishes a terminal passing ledger and the later gates also pass.

## Prepare the packet

Run this only against terminal, write-once evidence. If evidence is still
missing, use a disposable or explicitly dated draft path; the command refuses
to overwrite it later.

```bash
uv run python scripts/validation/review_phase5_readiness.py prepare \
  --contract config/contracts/phase-5-readiness.json \
  --repository-root . \
  --output benchmark-results/phase-5/phase-5-readiness-review-packet.json
```

The packet records only required fields and artifact identities. It does not
copy raw images, catalogues, or detailed result arrays.

## Independent acceptance records

Each reviewer receives the packet, the evidence it binds, and the role-specific
questions embedded in the contract. An acceptance record has this shape:

```json
{
  "acceptance_id": "phase-5-radio-astronomy-acceptance",
  "blocking_findings": [],
  "cutover_authorized": false,
  "phase_five_milestone_accepted": true,
  "release_authorized": false,
  "review_packet_sha256": "<exact packet SHA-256>",
  "reviewed_on": "YYYY-MM-DD",
  "reviewer": {
    "name": "<independent reviewer>"
  },
  "role": "radio-astronomy",
  "schema_version": 1,
  "status": "accepted"
}
```

The engineering record uses acceptance ID
`phase-5-engineering-acceptance` and role `engineering`. A rejection or an
unresolved blocking finding remains a terminal blocker; it must not be edited
into an acceptance in place.

The radio-astronomy review covers absolute science, reference comparisons,
morphology and SNR scope, the public failure disposition, seeded-island
ownership, shapes, beam deconvolution, unavailable score semantics, and the
scientific meaning of the Rapthor profile. The engineering review covers
bounded memory and task ownership, determinism and retry safety, evidence
identity, the incremental performance budget, workflow integration, and the
closed later lifecycle gates.

## Finalize Phase 5

After both independent records are complete:

```bash
uv run python scripts/validation/review_phase5_readiness.py finalize \
  --review-packet benchmark-results/phase-5/phase-5-readiness-review-packet.json \
  --radio-astronomy-acceptance benchmark-results/phase-5/phase-5-radio-astronomy-acceptance.json \
  --engineering-acceptance benchmark-results/phase-5/phase-5-engineering-acceptance.json \
  --repository-root . \
  --output benchmark-results/phase-5/phase-5-readiness.json
```

A successful terminal record sets `phase_five_complete=true` and points to
Phase 6 distributed execution. Every authorization field remains false.
Default Rapthor cutover and release remain later governed decisions.
