# Phase 0 review record

This record distinguishes frozen technical decisions from reviews that require
scientific or facility authority.

## Accepted project decisions

Gemma Danks is the named decider on accepted ADRs 003, 004, 005, and 006.
Together they freeze the Rapthor-focused scope, external ownership of the
top-level scheduler, hierarchical haloed tiling, and versioned compatibility
boundary. Their confirmation criteria remain active gates rather than one-time
documentation approval.

The performance curve, public behaviour list, regression and qualification
manifests, and provisional large-image resource envelope are frozen for Phase
0. A later measured crossover or facility constraint may amend them only
through reviewed evidence, the implementation plan, and `LOG.md`.

The technical Phase 0 evidence was first captured on 2026-07-18 and corrected
on 2026-07-31 after closure review found that it had exercised Rapthor's
`7.5/5.0` helper fallback and that the reference image's preinstalled LSMTool
module did not match Rapthor's declared commit. The replacement evidence uses
the representative `5.0/3.0` strategy, verifies exact clean Rapthor and
LSMTool checkouts and imported package identities, retains sanitized package
inventories and script hashes, and repeats one warm-up plus five compact and
representative measurements per reference. The technical completion does not
confer the external approvals below.

## Scientific review still required

The [2026-07-31 scientific pre-review](scientific-pre-review.md) compared the
provisional contracts with official PyBDSF, ASKAPsoft/Selavy, Aegean, SKA SDP,
WSClean, CASA, LOFAR, and published source-finder comparison material. Its
disposition is **amend before scientific approval**. It is research and a
reviewer aid, not the named sign-off required below.

An SKA imaging/domain reviewer must confirm or amend, with their name and date:

- the definitions and legacy mappings in the domain glossary;
- the public/internal naming conventions;
- the catalogue, RMS, mask, empty-result, and failure semantics in the Rapthor
  source-finding contract;
- the scientific thresholds in Section 5 of the implementation plan; and
- the classification and coverage of the frozen regression and held-out
  qualification cases.

### Reviewer packet

Review these sources together because no single document contains the full
scientific contract:

1. [Domain glossary](domain-glossary.md), including the legacy mappings and
   public/internal naming conventions.
2. [Scientific pre-review findings](scientific-pre-review.md), including the
   cross-pipeline consensus, Rapthor disagreements, and recommended
   amendments.
3. [Domain model](../explanation/domain-model.md) and
   [Rapthor source-finding contract](rapthor-source-finding-contract.md),
   including catalogue, RMS, mask, empty-result, and failure semantics.
4. [Scientific equivalence gates](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md#5-scientific-equivalence-gates)
   and the associated
   [dataset matrix](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md#6-dataset-matrix).
5. Frozen
   [development](https://github.com/gemmadanks/hebog/blob/main/config/datasets/phase-0-development.json),
   [regression](https://github.com/gemmadanks/hebog/blob/main/config/datasets/phase-0-regression.json),
   and
   [qualification](https://github.com/gemmadanks/hebog/blob/main/config/datasets/phase-0-qualification.json)
   manifests.
6. [Phase 0 baseline results](phase-0-baseline-results.md) and the
   [scientific comparison method](scientific-comparison.md) as supporting
   context rather than scientific truth.

The project owner may perform this review when acting with the required SKA
imaging/source-finding competence and authority. If the reviewer is also the
ADR decider, record that dual role explicitly. Independent confirmation is
still advisable before production cutover, but is not a Phase 0 prerequisite.

### Scientific sign-off

Append a completed record here using this form:

- **Reviewer:** _name_
- **Role or scientific authority:** _role and relevant domain responsibility_
- **Review date:** _YYYY-MM-DD_
- **Decision:** _approved, or approved with required amendments_
- **Required amendments:** _none, or links to the amended contracts, gates,
  manifests, and decision record_
- **Qualification-data confirmation:** _confirm that held-out qualification
  results were not used to tune the reviewed thresholds or algorithms_

Until that sign-off is appended here, thresholds remain engineering gates and
must not be described as domain-approved. This does not block reproducibility,
I/O scaffolding, or red-green-refactor algorithm work against the frozen
provisional PyBDSF profile; it does block stabilizing scientific defaults,
accepting intentional reference deviations, or making a domain-approved
scientific-equivalence or production-readiness claim. Starting algorithm work
before this review accepts the risk of later contract changes.

The reviewer is not expected to inspect or manually approve every output.
Machine-readable equivalence tests do that. Human review is limited to whether
the chosen datasets, metrics, tolerances, terminology, default profiles, and
handling of PyBDSF disagreements are scientifically and operationally fit for
purpose.

The human reviewer must specifically decide whether to approve the proposed
`5.0/3.0` Rapthor normal-cycle profile, the separate `5.0/4.0` early-cycle
profile, primary-beam terminology, source/component/island schema, empty RMS
and dummy-component migration, MFS-only initial scope, and the revised
low-SNR curve/confidence rule.

## Facility review still required

The controlled runner owner must map the representative 512 GiB profile and
storage capability onto an actual facility, then record node RAM, CPUs,
workers, threads, reserved headroom, concurrent demand, local spill medium,
shared-storage identifier, and permitted cache policy in the evidence record.
The 100,000-square gates cannot be marked demonstrated before the complete
1/10/50/100/200-node curve is retained and reviewed.
