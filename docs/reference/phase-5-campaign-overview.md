# Phase 5 scientific campaign overview

This page is the human-readable companion to the immutable Phase 5 evidence.
It explains what each material campaign or cumulative replay asked, how it was
evaluated, what the scientific result means, and what changed next. Machine
decisions and their checksums remain authoritative.

After each terminal campaign, replay, or evaluation-only completion, append a
new dated snapshot. Do not edit an older result into a pass, combine populations
across decisions, or replace a failed result with a later interpretation.

## Progress at a glance

| Evidence stage | Purpose | Outcome | What it established |
| --- | --- | --- | --- |
| Final qualification | Test the frozen pre-public candidate on untouched synthetic compact and Continuum populations | Pass | The candidate passed 143 Continuum absolute gates, 226 powered PyBDSF comparisons, and both compact decisions. |
| Public SDC1/Hydra development campaign | Exercise the public finder on realistic, previously unseen public data | Fail | Revealed a real low-SNR sensitivity gap and deep-field association overmerging. Its position-only SDC1 protocol is a stress test, not an official SDC1 score. |
| First corrected cumulative replay | Check the seeded-island and public-measurement correction against all viewed regression evidence | Fail | Compact remained sound, but Continuum had 44 failures and 37 like-semantics regressions dominated by fragmentation. |
| Source-association measurement-repair replay | Test whether conservative component association and complete measurement records fixed the remaining Continuum failures | Fail | Association changed point estimates but no endpoint status. Compact passed; source reconstruction, source-level measurement, and mask precision remain open. |
| Source-reconstruction cumulative replay | Test deterministic multiscale hierarchy, one source-level measurement, connected support, and source-union topology | Fail | Compact passed, but Continuum again had 44 failures and 37 regressions. The hierarchy did not change governed source membership or fragmentation. |
| Parent-construction cumulative replay | Test whether scale-aware parent envelopes and persistence create the intended catalogue-source parents | Fail | Compact passed, but all 143 Continuum endpoint values and decisions were unchanged. The parent-construction path still did not change governed source membership. |

The apparent contrast between final qualification and later failure is useful,
not contradictory. The final qualification showed that the frozen candidate
passed its declared untouched synthetic population. The public campaign then
exposed behaviours absent from that population. Those viewed cases became
development-regression evidence, and the later cumulative replays test proposed
corrections against the expanded evidence set.

## Latest snapshot: source-association measurement repair

**Terminal date:** 2026-08-29

**Evidence role:** viewed-development cumulative regression, not fresh held-out
qualification and not a new real-sky campaign.

**Scientific question:** after the source-association and measurement repairs,
can Hebog preserve its compact-source performance while turning fragmented
extended emission into accurate, trustworthy catalogue sources?

**Terminal verdict:** no. Compact passed, but Continuum failed. The exact
terminal ledger is
`benchmark-results/phase-5/cumulative-regression-ledger-public-finder-source-association-measurement-repair.json`,
SHA-256
`6b2aa4deb306e0d7ba8285aae1e18bfb4f4e838b57aecd0497bec990e8a8c842`.

### What was tested

The cumulative population contained:

- 800 compact and blended 512-by-512 images;
- 1,600 Continuum images covering shells, filaments, diffuse and mixed
  emission, artifacts, invalid pixels, varying noise, image edges, and tile
  boundaries and corners;
- 2,400 preserved Hebog candidate product sets; and
- 9,600 retained reference runs, including released PyBDSF and pinned PyBDSF
  `master`.

Every image had analytic or injected truth. Each finder was associated with
that truth independently; finders were never matched to one another or treated
as votes. The evaluator measured compact and Continuum completeness,
reliability, flux, position, shape or mask quality, duplicates, splits, and
merges across the declared scientific strata.

The decision order was fail-closed:

1. Hebog had to pass every absolute truth gate.
2. It then had to be non-inferior to both PyBDSF references wherever the
   comparison applied.
3. It could not regress against the preceding like-semantics Hebog baseline.
4. No strong metric could compensate for a failure in another metric or
   stratum.

The candidate produced all 2,400 outputs. Compilation initially stopped because
the compiler assumed that every catalogue row owned exactly one legacy
component label, while an associated Hebog source may own several. A separately
approved evaluation-only adapter verified the preserved candidate products and
compiled them without executing the candidate again.

### Compact and blended sources

The compact lane passed every binding decision and had no like-semantics
regressions.

| Metric | Hebog | Released PyBDSF | PyBDSF `master` | Interpretation |
| --- | ---: | ---: | ---: | --- |
| Completeness | 100.00% | 100.00% | 100.00% | Effectively equal and passing. |
| Catalogue reliability | 99.76% | 99.87% | 99.18% | Passing and non-inferior to both. |
| Median position error | 0.0206 beam | 0.0225 beam | 0.0225 beam | Hebog is slightly better. |
| Position-error p95 | 0.0696 beam | 0.0775 beam | 0.0771 beam | Hebog is better in the tail. |
| Median integrated-flux error | 3.43% | 12.66% | 12.66% | Hebog is materially better. |
| Integrated-flux-error p95 | 16.77% | 34.50% | 34.76% | Hebog is materially better, although this remains an imperfect report-only tail. |
| Catastrophic-outlier fraction | 0.034% | 0.578% | 0.885% | Hebog has far fewer catastrophic outliers. |

The scientific conclusion is that Hebog is already competitive with PyBDSF
for compact, resolved Gaussian-like, and blended component finding. Its
strongest advantages are flux recovery, shape measurements, and outlier
control.

### Extended and irregular Continuum sources

The Continuum decision contained 143 binding endpoints across 16 overall,
morphology, scale, validity, noise, edge, and tile strata. Eighty-nine passed,
44 failed, and 10 were underpowered. Thirty-seven endpoints regressed against
the preceding like-semantics Hebog baseline.

| Metric | Hebog | Released PyBDSF | PyBDSF `master` | Interpretation |
| --- | ---: | ---: | ---: | --- |
| Completeness | 100.00% | 99.94% | 99.99% | Hebog finds the governed truth population. |
| Reliability | 62.38% | 56.70% | 52.61% | Hebog is numerically better, but all are poor and Hebog fails its 95% floor. |
| Median integrated-flux error | 5.22% | 17.52% | 27.88% | Hebog is clearly better for the typical matched source. |
| Integrated-flux-error p95 | 79.26% | 84.41% | 85.36% | Hebog is slightly better, but all are poor and Hebog fails its 25% limit. |
| Position-error p95 | 4.18 beams | 4.11 beams | 4.10 beams | Hebog is slightly worse and far above its 0.5-beam limit. |
| Duplicate fraction | 25.29% | 34.37% | 40.38% | Hebog is better than PyBDSF but fails its 2% limit. |
| Split fraction | 25.29% | 27.21% | 27.25% | Hebog is slightly better but fails its 10% limit. |
| Mask precision | 88.41% | 95.25% | 95.97% | Hebog admits more false support and fails paired non-inferiority. |
| Mask recall | 91.96% | 81.12% | 79.99% | Hebog recovers substantially more real emission. |
| Mask intersection over union | 82.06% | 77.92% | 77.24% | Hebog has better total mask overlap. |
| Merge fraction | 0.00% | 0.00% | 0.00% | All pass; overmerging is not the current failure. |

Hebog is therefore not simply worse than PyBDSF on extended emission. It is
more sensitive, recovers more true support, has better total mask overlap, and
usually measures flux more accurately. Its present weakness is converting that
emission into a clean source catalogue: one real extended source is often left
as several catalogue entries. Those fragments reduce reliability and create
large worst-case flux and position errors.

### Why the latest correction failed

The terminal review accounts for all 44 failures:

| Failure family | Failed endpoints | Explanation |
| --- | ---: | --- |
| Reliability | 1 | Under-associated components inflate the number of catalogue rows. |
| Duplicate and split topology | 18 | Straight centroid chords, directional-FWHM proximity, and complete-link grouping cannot represent shells, curved emission, or separated peaks with common multiscale support. Split scoring also remained tied to native components. |
| Integrated flux | 11 | The associated row sums independently measured component apertures instead of measuring the reconstructed source once. |
| Astrometry | 13 | Fragment positions and flux-weighted component centroids produce severe positional tails. |
| Mask precision | 1 | The likely cause is disconnected reconstructed support admitted by nearest distance alone. This attribution remains moderate-confidence until reproduced by analytic fixtures. |

The next proposed correction reconstructs a catalogue source from exact
adjacent-scale support, measures that source once on disjoint owned pixels,
requires connected recovered mask support, and separates binding source-level
topology from diagnostic component fragmentation. See the
[source-reconstruction pre-review](phase-5-public-finder-source-reconstruction-pre-review.md).

## Latest snapshot: source reconstruction

**Terminal date:** 2026-08-29

**Evidence role:** viewed-development cumulative regression, not fresh held-out
qualification and not a new real-sky campaign.

**Scientific question:** does a deterministic common-parent multiscale
hierarchy, followed by one measurement per reconstructed source and connected
support admission, eliminate the catalogue fragmentation exposed by the prior
replay without regressing compact science?

**Terminal verdict:** no. Compact passed, but Continuum failed. The exact
terminal ledger is
`benchmark-results/phase-5/cumulative-regression-ledger-public-finder-source-reconstruction.json`,
SHA-256
`84fbb3a18828210543d815d28aa4eab039a2ad7467aa2572a9c5119780f55a0e`.

### What was tested

The replay reused the governed 800 compact and 1,600 Continuum images, all
9,600 reconstructed reference runs, and the same closed like-semantics
baseline. Candidate `42c75f4...` generated all 2,400 new Hebog products.
Every image retained analytic or injected truth, and the evaluator applied the
same fail-closed absolute, paired PyBDSF non-inferiority, and previous-Hebog
regression gates described above.

The candidate stage completed successfully. Compilation then stopped before
publication because unchanged PyBDSF records were sent to the new Hebog-only
source-union evaluator. The approved evaluation-only repair dispatched each
record by its frozen semantics, verified product set `0d8c2d0b...`, and
published the ledger without rerunning Hebog. This operational incident did
not change candidate science, references, gates, thresholds, or products.

### Scientific result

Compact passed with no like-semantics regression. Continuum again produced 89
passes, 44 failures, 10 underpowered endpoints, and 37 like-semantics
regressions.

| Overall Continuum metric | Hebog | Required limit | Outcome |
| --- | ---: | ---: | --- |
| Completeness | 100.00% | at least 90% | Pass |
| Reliability | 62.38% | at least 95% | Fail |
| Median integrated-flux error | 5.22% | at most 10% | Pass |
| Integrated-flux-error p95 | 79.26% | at most 25% | Fail |
| Position-error p95 | 4.18 beams | at most 0.5 beam | Fail |
| Duplicate fraction | 25.29% | at most 2% | Fail |
| Split fraction | 25.29% | at most 10% | Fail |
| Mask precision | 88.41% | at least 85% | Absolute value passes, but paired non-inferiority fails |
| Mask recall | 91.96% | at least 90% | Pass |
| Mask intersection over union | 82.06% | at least 80% | Pass |
| Merge fraction | 0.00% | at most 10% | Pass |

Relative to the preceding measurement-repair ledger, 48 of 143 Continuum
point estimates changed. The largest change was only about
`6.6e-7`, no endpoint moved between pass, fail, or underpowered, and overall
duplicate and split fractions were exactly unchanged. This is stronger than a
generic statement that the correction was insufficient: on the governed
population, the new hierarchy did not materially change catalogue-source
membership. Consequently, one-source measurement and source-union scoring had
no different grouping to measure or score.

Hebog still has the same mixed scientific profile. It detects all governed
Continuum truth, has good typical flux recovery, high mask recall and overlap,
and no merge problem. It does not yet turn that recovered emission into a
clean, reliable source catalogue: fragmentation remains too high and drives
poor reliability and severe position and flux tails.

### What happens next

The cumulative gate remains closed, so fresh held-out qualification, the
Rapthor profile decision, cutover, and release cannot proceed. The next step is
a prospective root-cause review of why common-parent hierarchy activation left
source membership unchanged. That review must reproduce the activation gap in
analytic fixtures and freeze any correction before another replay is proposed;
this terminal evidence must not be tuned or rescored.

## Latest operational snapshot: parent construction

**Terminal date:** 2026-08-30

**Evidence role:** attempted viewed-development cumulative regression. This is
an operational failure, not a scientific result.

Candidate `5f2b098...` completed all 800 compact and 1,600 Continuum products.
Compilation then stopped before publishing an atomic ledger with
`associated source membership cannot be verified`. The new catalogue source
IDs were correctly constructed from immutable direct-seed components, but the
evaluator tried to reconstruct those identities from recovered measurement
labels whose support can begin at a different pixel. The cumulative writer had
also omitted the exact in-memory `source_association` record from every
Continuum shard, leaving no fail-closed way to verify the digest membership
from the preserved files.

No metric, endpoint status, or Hebog-versus-PyBDSF conclusion was produced.
The 2,400 candidate products are complete and remain unchanged. The evaluator
now has a tested overlay that consumes an explicit association record and
independently verifies both component and source digests plus the disjoint
support partition without modifying either frozen historical compiler. Closing
this attempt requires separately approved
reconstruction of only the omitted 1,600 association sidecars, with every
regenerated catalogue, label plane, and mask required to match the preserved
products exactly, followed by one evaluation-only completion.

## Latest scientific snapshot: parent construction

**Terminal date:** 2026-08-30

**Evidence role:** viewed-development cumulative regression, not fresh held-out
qualification and not a new public-data campaign.

**Scientific question:** do scale-aware parent envelopes, cycle-supported
sibling candidates, adjacent-scale persistence, and exact-feature
corroboration finally change catalogue-source membership enough to remove the
extended-source fragmentation exposed by the prior replays?

**Terminal verdict:** no. The repaired evaluation completed and published the
write-once ledger, but the scientific gate failed. The exact ledger is
`benchmark-results/phase-5/cumulative-regression-ledger-public-finder-source-hierarchy-parent-construction.json`,
SHA-256
`2ece9928eec152cf17f06e9e869d0db9c6a8f0acc2b18ea482aced5e133e6bce`.

### Scientific result

Compact passed every binding decision with no like-semantics regression.
Continuum produced 89 passes, 44 failures, 10 underpowered endpoints, no
indeterminate endpoints, and 37 like-semantics regressions.

| Overall Continuum metric | Hebog | Required limit | Outcome |
| --- | ---: | ---: | --- |
| Completeness | 100.00% | at least 90% | Pass |
| Reliability | 62.38% | at least 95% | Fail |
| Median integrated-flux error | 5.22% | at most 10% | Pass |
| Integrated-flux-error p95 | 79.26% | at most 25% | Fail |
| Position-error p95 | 4.18 beams | at most 0.5 beam | Fail |
| Duplicate fraction | 25.29% | at most 2% | Fail |
| Split fraction | 25.29% | at most 10% | Fail |
| Mask precision | 88.41% | at least 85% | Absolute value passes, but paired non-inferiority fails |
| Mask recall | 91.96% | at least 90% | Pass |
| Mask intersection over union | 82.06% | at least 80% | Pass |
| Merge fraction | 0.00% | at most 10% | Pass |

The failure families are unchanged: one reliability endpoint, 18 duplicate or
split endpoints, 11 integrated-flux endpoints, 13 astrometry endpoints, and
one mask-precision endpoint. More importantly, comparison with the preceding
source-reconstruction ledger found no change in the candidate value, status,
or reason for any of the 143 Continuum endpoints. This rules out the expected
scientific effect of the new parent construction on the governed population.
The issue is still activation or propagation of catalogue-source membership,
not merely an evaluator presentation problem.

### Operational recovery and consequence

Candidate execution had already produced all 2,400 immutable products. The
original compiler could not verify direct-seed membership because the exact
association record had not been persisted. An approved reconstruction created
only the 1,600 omitted Continuum association sidecars and verified every
regenerated catalogue, label plane, and mask against the preserved products.
Two evaluation-only composition defects were then repaired without rerunning
the candidate. The final completion verified the candidate product set,
association product set, retained references, closed baseline, and repair
identities before publishing this ledger.

The cumulative prerequisite remains closed. Fresh qualification, the Rapthor
profile decision, final readiness, cutover, and release cannot proceed. This
result is terminal evidence for this candidate: it must not be tuned, rescored,
or rerun. Any further scientific correction requires a new prospective
root-cause review and new frozen candidate identity.

## Required format for future snapshots

Append future terminal results to this page using the same order:

1. terminal date, evidence role, exact decision or ledger identity, and whether
   the population is development, regression, or qualification;
2. the single scientific question the campaign was designed to answer;
3. population sizes, morphology and SNR scope, finders and runtime identities,
   and truth source;
4. how candidates were matched and how uncertainty and non-inferiority were
   decided;
5. compact and Continuum comparison tables with units and gate interpretation;
6. endpoint pass, fail, underpowered, and regression counts;
7. a plain-language scientific verdict, including where Hebog is better than
   the references but still fails an absolute requirement;
8. operational failures clearly separated from scientific failures; and
9. the next authorized or approval-gated action.

This overview is explanatory. Exact JSON evidence, the
[external comparison protocol](phase-5-external-comparison-protocol.md), the
[implementation plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md),
and `LOG.md` remain the provenance and governance records.
