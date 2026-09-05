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
| Terminal-parent cumulative replay | Test the persistent terminal-cycle correction on the complete cumulative population | Fail, materially improved | Compact passed. Continuum improved from 89 to 96 passing endpoints; split and duplicate fractions nearly halved, but 35 failures and 30 regressions remain. |
| Prospective 128-case science smoke | Fail fast on the terminal-cycle eligibility candidate before another complete replay | Fail, full replay blocked | All incumbent-retention checks passed, but eight PyBDSF-parity checks failed. The terminal-cycle repair activated diagnostically without changing catalogue membership; systematic mask-boundary precision is the principal confirmed gap. |
| Publication-scale-persistence cumulative replay | Test the smoke-passing adjacent-scale publication rule on the complete 800-compact/1,600-Continuum regression population | Legacy fail; prospective decision incomplete | Compact passed. The original wrapper reported 31 absolute failures, 11 underpowered endpoints, and 26 historical status regressions, but the later prospective review found all stored PyBDSF comparisons within margin and no full paired evidence against the selected Hebog incumbent. |
| Adaptive-background 144-image development lane | Test whether adaptive background/RMS refinement preserves bright extended sources when its strict 75-sigma trigger activates | Fail; qualification blocked | Triggering and Serial/Dask invariance passed, but 9 of 12 geometry groups failed. Shell and mixed compact/extended emission lost support or mask quality relative to the coarse control, with severe mixed-source flux failures. |

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

### Prospective correction after this result

The retained sidecars showed why the science was unchanged: all 18,065 direct
components remained singleton sources, and every one of 1,923 constructed
parents first appeared at the final retained scale. The old rule required the
same parent to recur at a fourth scale that does not exist.

The next fixture-only correction does not alter this terminal result. It uses
connected adjacent-scale significant support only to corroborate non-terminal
hierarchy evidence; connected support alone cannot merge pairs or paths. For a
parent first resolved at the final scale, it requires a cycle of at least three
features and proves that every constituent feature persists from the preceding
scale. Uncorroborated terminal bridges, pairs, chains, ambiguous owners,
invalid support, and partial overlaps with an existing exact source remain
separate. See the
[persistent-support parent correction](phase-5-public-finder-persistent-support-parent-correction.md)
for the complete scientific and authorization boundary.

## Latest scientific snapshot: terminal-parent correction

**Terminal date:** 2026-08-31

**Evidence role:** viewed-development cumulative regression, not fresh held-out
qualification and not a new public-data campaign.

**Scientific question:** can a cycle-supported parent first visible at the last
retained scale join persistent shell and other multi-lobe components without
regressing compact science or overmerging independent sources?

**Terminal verdict:** the correction worked, but not often enough to pass. The
exact write-once ledger is
`benchmark-results/phase-5/cumulative-regression-ledger-public-finder-terminal-parent-correction.json`,
SHA-256
`e2ee663f4eade383518eabbafda5cd33bfe9808b4a9b37492a77337738b611db`.

### What was tested

The replay generated 800 compact products and 1,600 Continuum products from
candidate `85d5807...`, then compared them with the same 9,600 reconstructed
reference runs and closed like-semantics baseline. The immutable preflight
verified every input, reference, program, configuration, source tree, and
write-once path before execution. All 2,400 products completed and the atomic
ledger was published without an operational failure.

Compact passed with no like-semantics regression. Continuum produced 96
passes, 35 failures, 12 underpowered endpoints, no indeterminate endpoints,
and 30 like-semantics regressions. Both
`cumulative_science_regression_ready` and `all_required_endpoints_pass` are
false.

| Overall Continuum metric | Previous parent | Terminal parent | Required limit | Outcome |
| --- | ---: | ---: | ---: | --- |
| Completeness | 100.00% | 100.00% | at least 90% | Pass |
| Reliability | 62.38% | 85.21% | at least 95% | Improved, fail |
| Median integrated-flux error | 5.22% | 4.53% | at most 10% | Pass |
| Integrated-flux-error p95 | 79.26% | 26.94% | at most 25% | Strongly improved, fail |
| Position-error p95 | 4.18 beams | 0.98 beam | at most 0.5 beam | Strongly improved, fail |
| Duplicate fraction | 25.29% | 12.83% | at most 2% | Nearly halved, fail |
| Split fraction | 25.29% | 12.83% | at most 10% | Nearly halved, fail |
| Mask precision | 88.41% | 88.41% | at least 85% plus paired non-inferiority | Absolute pass, paired fail |
| Mask recall | 91.96% | 91.96% | at least 90% | Pass |
| Mask intersection over union | 82.06% | 82.06% | at least 80% | Pass |
| Merge fraction | 0.00% | 0.00% | at most 10% | Pass |

Nine endpoint states improved and 54 of 143 Continuum point estimates changed.
The clearest result is the shell stratum: split and duplicate fractions fell
from 100% to 34.56%, while median integrated-flux error fell from 76.46% to
10.39%. Tile-boundary median flux and six shell or corner mean-astrometry
endpoints moved from fail to pass. Scale-4 and varying-noise split endpoints
moved from fail to underpowered. No endpoint became worse and the
like-semantics regression count fell from 37 to 30.

### Scientific interpretation and next boundary

This is the first source-parent correction that materially changed the
governed catalogue. It shows that source-level measurement is effective once
the intended parent activates. The remaining poor reliability, duplicate and
split fractions, and flux and position tails are concentrated in realizations
where the source remains fragmented; they are not evidence that accepted
parents are generally measured badly.

The current implementation requires every terminal-cycle feature to have an
exact pixel-overlap child at the preceding scale. The ledger proves incomplete
activation, while code inspection identifies this exact-overlap condition as
a plausible narrow blocker. The terminal ledger does not retain per-rejection
sidecars, so that attribution is not yet proven for every failed realization.
Named approval of pre-review `e416f7d8...` opened a red analytic
boundary-drift fixture before implementation. That fixture confirmed the
exact-overlap failure. The implemented prospective repair uses only mutually
unique, fixed-B3-footprint, same-significant-component evidence to corroborate
a displaced adjacent-scale child. It may not create a cycle or source
membership, accept pairs or paths, change thresholds or photometry, or rescore
this result.

The exact non-executable review is
`config/contracts/phase-5-public-finder-terminal-feature-persistence-pre-review.json`,
SHA-256
`e416f7d81ac8345f2ac0ac982980e9e37299886309af2468380a7a463beafc38`.
Implementation and fixture validation are complete under the named approval.
Replacement candidate `3d080f7...`, source tree `a25d22d8...`, configuration
`2d6ab6bb...`, wrapper `0c66f221...`, and evaluator `1cb62c00...` are now
frozen by non-executable review `45aef047...`. Its complete no-write verifier
checked all 2,400 retained inputs and 9,600 reference runs while leaving both
scratch and output absent. No new scientific result exists yet, and the
present terminal-parent failure remains immutable. A replay requires a new
exact review-bound approval.

## Latest scientific snapshot: terminal-feature persistence

**Terminal date:** 2026-08-31

**Evidence role:** viewed-development cumulative regression, not fresh
held-out qualification and not a new public-data campaign.

**Scientific question:** can a mutually unique preceding-scale child that is
displaced by a small boundary change corroborate an already seeded terminal
cycle, recover additional valid source parents, and preserve compact and
overmerge safety?

**Terminal verdict:** no. The intended displaced-child path did not activate,
and an accompanying cycle-eligibility restriction removed some scientifically
useful predecessor parents. The exact write-once ledger is
`benchmark-results/phase-5/cumulative-regression-ledger-public-finder-terminal-feature-persistence.json`,
SHA-256
`a9b4d57ec7384eb1d625b9a030126f4ca5d45f0a83150b309d14b3536eeae8a6`.

### What was tested

Immutable checkout `ed84c216...` verified the exact 2,400 inputs and 9,600
retained reference runs before executing candidate `3d080f7...` with source
tree `a25d22d8...` and configuration `2d6ab6bb...`. The population contains
800 compact cases and 1,600 Continuum cases. It uses the same closed baseline,
truth matching, absolute gates, and like-semantics comparisons as the
preceding terminal-parent replay. All candidate products completed, and the
atomic ledger was published without a process repair or duplicate run.

Compact passed every binding decision with no like-semantics regression.
Continuum produced 93 passes, 39 failures, 11 underpowered endpoints, no
indeterminate endpoints, and 33 like-semantics regressions. Both cumulative
readiness booleans remain false.

| Overall Continuum metric | Terminal parent | Feature persistence | Required limit | Outcome |
| --- | ---: | ---: | ---: | --- |
| Completeness | 100.00% | 100.00% | at least 90% | Pass |
| Reliability | 85.21% | 77.80% | at least 95% | Regressed, fail |
| Median integrated-flux error | 4.53% | 4.70% | at most 10% | Pass |
| Integrated-flux-error p95 | 26.94% | 74.62% | at most 25% | Regressed, fail |
| Position-error p95 | 0.98 beam | 3.59 beams | at most 0.5 beam | Regressed, fail |
| Duplicate fraction | 12.83% | 15.21% | at most 2% | Regressed, fail |
| Split fraction | 12.83% | 15.21% | at most 10% | Regressed, fail |
| Mask precision | 88.41% | 88.41% | at least 85% plus paired non-inferiority | Absolute pass, paired fail |
| Mask recall | 91.96% | 91.96% | at least 90% | Pass |
| Mask intersection over union | 82.06% | 82.06% | at least 80% | Pass |
| Merge fraction | 0.00% | 0.00% | at most 10% | Pass |

Fifty of 143 Continuum point estimates changed. No endpoint state improved;
three astrometric-bias passes became failures, the scale-4-beam split endpoint
moved from underpowered to failure, and three new like-semantics regressions
appeared. The failure families are reliability; flux median and tail;
astrometric bias and tail; duplicate and split topology; and paired
mask-precision non-inferiority.

### Activation evidence and interpretation

| Terminal-persistence diagnostic | Count |
| --- | ---: |
| Terminal-cycle candidates | 1,211 |
| Accepted terminal parents | 1,211 |
| Exactly persistent terminal features | 4,414 |
| Displaced-child candidates | 0 |
| Accepted displaced children | 0 |
| Missing or ambiguous children | 0 |
| Rejected cycles or whole-group conflicts | 0 |

The proposed displacement mechanism was dormant on this population. The
ledger also rules out process, identity, compact-science, mask-support, and
displaced-overmerge explanations.

Code inspection identifies the only new restriction capable of changing the
predecessor's existing exact-parent path: before persistence evaluation, the
candidate rejects a whole terminal-cycle feature group if any geometric
feature has no direct-component owner. Previously, an unseeded but persistent
feature could corroborate cycle geometry without becoming a catalogue member;
membership was still derived only from seeded direct components. The new
guard can therefore remove a useful parent without entering the downstream
displaced, missing, ambiguity, or conflict census.

That attribution is deliberately not treated as fully proved per realization:
the census begins after the guard and transient candidate products were
removed after atomic publication. The next boundary is a non-executable
fixture-first pre-review. It requires a red seeded-cycle eligibility fixture,
negative overmerge controls, bounded pre-eligibility diagnostics, and
Serial/existing-Dask invariance before any prospective implementation. It
does not authorize another replay, viewed-data execution, tuning, rescoring,
qualification, cutover, or release. Its exact SHA-256 is
`e70e602f5a7a7c2a703def62ac6e5922c505feb71ae4b6f9def6dfcbf9520cd5`.

## Prospective 128-case science smoke

**Terminal date:** 2026-09-01

**Evidence role:** viewed-development diagnostic smoke. It is neither a full
cumulative replay nor qualification evidence and cannot be pooled with either.
The authoritative atomic record is
`benchmark-results/phase-5/prospective-science-smoke.json`, SHA-256
`e3ac8e62b0d136078b2a4a15e7841b12f62c4381db7bb581d03a9468448b248c`.

**Scientific question:** does terminal-cycle eligibility fix the known
catalogue-source loss while preserving the whole incumbent and avoiding an
obvious PyBDSF-parity regression on a small, deterministic population?

**Population and method:** 64 compact and 64 Continuum realizations were
selected deterministically from the retained cumulative population. The exact
candidate and exact whole incumbent were reexecuted on the same inputs. All
369 applicable incumbent-retention comparisons and 361 applicable PyBDSF
comparisons used the frozen prospective contract; underpowered comparisons
remained diagnostic and a confirmed failure stopped the full replay.

| Decision class | Count |
| --- | ---: |
| Pass | 326 |
| Underpowered diagnostic | 35 |
| Confirmed fail | 8 |
| Failed incumbent-retention comparisons | 0 |

Compact products were byte-identical to the incumbent. Every failed family
also had zero candidate-versus-incumbent difference. The eight confirmed
PyBDSF-parity failures were one image-edge duplicate-fraction check, two
duplicate morphology/scale checks, two overall mask-precision checks, and
three diffuse split checks. Mask recall and intersection over union were
better than the PyBDSF references, but mask precision was worse in every one
of the 64 Continuum realizations. This identifies a systematic sparse-boundary
support gap rather than a sensitivity failure. The duplicate and split
failures were sparse realization-level outliers.

The terminal-cycle eligibility census was active: 26 unseeded persistent
candidates were accepted. Nevertheless, all 64 catalogue membership records
were identical to the incumbent, which had already accepted the same 75
terminal parents. The repair therefore cannot explain or fix the remaining
parity failures.

**Terminal verdict:** fail. The full cumulative replay remains blocked. The
prospective next correction applies the already-reviewed dense-core,
high-S/N-boundary, and nearby significant-support refinement after seeded
ownership, with its existing fixed constants. Review
`phase-5-prospective-boundary-refinement-pre-review`, SHA-256
`e92ac2893699bb0ff96347af6a691c654649fa6e152ef5dd588930f9f0cf82aa`,
also requires a regression fix for an opened-away high-S/N thin detection and
a new write-once smoke result. It authorizes no threshold tuning or
retrospective rescoring.

## Boundary-connectivity 128-case science smoke

**Terminal date:** 2026-09-01

**Evidence role:** viewed-development diagnostic smoke. The authoritative
atomic record is
`benchmark-results/phase-5/prospective-science-smoke-boundary-connectivity.json`,
SHA-256
`e30f27dd4438521bd7f17c13d094257b3577a97801078def79da2101e3d018ad`.

**Scientific question:** does seeded-owner boundary cleanup close the PyBDSF
mask-precision gap without losing any scientific quality already present in
the whole Hebog incumbent?

The exact 64-compact/64-Continuum smoke population and frozen prospective
decision contract were unchanged. Compact products were byte-identical to the
incumbent. The corrected terminal-cycle path remained active on 26 unseeded
persistent candidates.

| Decision class | Count |
| --- | ---: |
| Pass | 309 |
| Underpowered diagnostic | 49 |
| Confirmed fail | 11 |
| Failed incumbent-retention comparisons | 3 |

Boundary cleanup modestly improved overall mask precision relative to the
incumbent, while mask recall and intersection-over-union remained within their
retention margins. It did not close the released or pinned-master precision
gates: recovered multiscale support could still enter the published mask below
the frozen three-sigma island threshold.

Three new incumbent position-p95 failures revealed an implementation coupling,
not a detection loss. The refined published mask also replaced the seeded
catalogue measurement plane, changing component support, moment centroids, and
identifiers. Continuum-2 varying-noise seed 2026861185 dominates this tail:
position p95 changed from 0.5709 to 2.2886 beams overall and from 0.6018 to
2.4340 beams at scale four. The remaining four duplicate and two diffuse-split
failures are inherited sparse topology gaps rather than boundary-cleanup
regressions.

**Terminal verdict:** fail. The full replay remains blocked. Pre-review
`phase-5-prospective-mask-measurement-separation-pre-review`, SHA-256
`bd0ba2979b101958b511786f737315b4d2595d298e5a42a2443cfb9e92121603`,
freezes a mask-only correction: recovered published support must meet the
existing island threshold, while association and measurement retain the stable
seeded-owner plane. No threshold, margin, population, or closed result is
changed or rescored.

## Mask/measurement-separated 128-case science smoke

**Terminal date:** 2026-09-01

**Evidence role:** viewed-development diagnostic smoke. The authoritative
atomic record is
`benchmark-results/phase-5/prospective-science-smoke-mask-measurement-separation.json`,
SHA-256
`07f51256f241a43bc146b5d82aa3ce8c275ecbd47b6e470db650a194cbd3df16`.

**Scientific question:** does persisting the exact measurement-label plane
restore stable catalogue/source evaluation while the separately refined
published mask closes every PyBDSF and incumbent-retention gate?

The same deterministic 64-compact/64-Continuum population was evaluated.
Compact products remained byte-identical to the incumbent. Exact current and
historical schema dispatch succeeded, so the result is the first complete
scientific decision for the mask/measurement separation rather than a process
failure.

| Decision class | Count |
| --- | ---: |
| Pass | 326 |
| Underpowered diagnostic | 35 |
| Confirmed fail | 8 |
| Failed incumbent-retention comparisons | 0 |

The separation fixed all three position-p95 regressions introduced by the
boundary candidate. The eight remaining failures are four duplicate-fraction
checks, two overall mask-precision checks, and two diffuse split-fraction
checks. The edge duplicate is one realization, Continuum-1 seed 2026860341;
the diffuse split is three realizations, seeds 2026860341, 2026862118, and
2026862301. Artifact and scale-one duplicate failures share a small set of
disconnected detections rather than a population-wide catalogue shift.

Mechanism review separated the two causes. The mask deficit exists in the
direct detection plane; measurement ownership is effectively identical and
publication cleanup already improves precision slightly. The implementation
nevertheless passed the maximum of direct, matched-filter, and à-trous S/N to
a refinement documented to require original-pixel S/N. Filtered significance
could therefore publish sparse support below the frozen three-sigma island
threshold. On seven diagnosed failing or worst-mask cases, using the actual
residual divided by RMS raised publication precision in every case while
leaving measurement and catalogue products unchanged.

The topology failures are independent. The conservative component graph has
zero admissible edges in all seven diagnosed cases. Some duplicate secondaries
have no retained multiscale lineage, while several bright artifact and shell
detections have distinct persistent lineages. Globally disabling connectivity
restoration, relaxing association constraints, or filtering rows using viewed
truth would therefore be scientifically unjustified.

**Terminal verdict:** fail. The full replay remains blocked. Pre-review
`phase-5-prospective-publication-snr-repair-pre-review`, SHA-256
`9c0e8ece3e64e13947a803586dfcf3fd7dcabef5281fff96a05cf9ae1a63ee53`,
and implementation decision `029f9a2068c7...` freeze only the original-pixel
publication statistic. No threshold, margin, measurement, association,
population, comparator, or decision rule changes. The replacement candidate
configuration is `57841bc3...`; it must complete the same write-once smoke
before any separate topology correction or full replay.

The first materialization attempt exposed a process-only `runpy` composition
defect before producing any candidate product: changing the returned mapping
did not change the globals resolved by the frozen CLI, leaving an unimportable
`<run_path>` worker and inactive builder/evaluator overrides. Regression tests
now verify the actual function globals. Repaired implementation decision
`a292fa98c66b...` binds the correction; no scientific product was overwritten
or rescored.

## Original-pixel publication-S/N 128-case science smoke

**Terminal date:** 2026-09-01

**Evidence role:** viewed-development diagnostic smoke. The authoritative
atomic record is
`benchmark-results/phase-5/prospective-science-smoke-publication-snr-repair.json`,
SHA-256
`a8bee362728df293a30d171bed5afb4e412ecae9cbf9af06fbbce5afec083249`.

**Scientific question:** does using original-pixel residual/RMS for publication
support close the remaining mask-precision gap without changing measurement,
catalogue, compact, or incumbent-retention science?

The same deterministic 64-compact/64-Continuum smoke population was used.
Compact products were byte-identical to the incumbent, and no candidate
measurement or catalogue rule changed.

| Decision class | Count |
| --- | ---: |
| Pass | 327 |
| Underpowered diagnostic | 35 |
| Confirmed fail | 7 |
| Failed incumbent-retention comparisons | 0 |

The repair cleared the released-PyBDSF mask-precision gate and narrowed the
pinned-master precision regression to 0.05231 against a 0.05 margin. It did
not clear that binding comparison. Refinement still begins from the expanded
measurement-owner plane, whose dense opened core does not receive the direct
S/N floor; therefore the remaining systematic mask miss is an origin-domain
defect rather than evidence for threshold tuning.

Six topology comparisons also fail: image-edge and morphology-artifact
duplicate fractions, scale-one duplicate fraction, and diffuse split fraction.
The edge result is driven by seed 2026860341; the diffuse result is driven by
2026860341, 2026862118, and 2026862301. Attribution finds pairs of persistent
sibling detections which the deliberately conservative three-member cycle rule
cannot group. Proximity and connected support alone remain unsafe; any pair
repair must additionally prove repeated adjacent-scale geometry, mutual
uniqueness, whole-group reconciliation, and negative-overmerge invariance.

**Terminal verdict:** fail. This result improves the prior smoke from eight to
seven confirmed failures, but the full cumulative replay remains blocked. The
next bounded candidate must correct mask-origin semantics and source topology
without changing thresholds, margins, comparators, or closed evidence, then
pass the same smoke with zero confirmed failures.

## Direct-origin and sibling-pair 128-case science smoke

**Terminal date:** 2026-09-01

**Evidence role:** viewed-development diagnostic smoke. The authoritative
atomic record is
`benchmark-results/phase-5/prospective-science-smoke-mask-origin-sibling-pair.json`,
SHA-256
`778e43a96f0fad15c7ae28a562bcd18ca4b6e000df672221657e0803148addfc`.

**Scientific question:** does beginning publication cleanup from immutable
direct labels and adding a conservative persistent sibling parent close the
remaining mask-precision and duplicate/split failures without regressing the
incumbent?

The same deterministic 64-compact/64-Continuum population was evaluated.
Compact products remained byte-identical to the incumbent.

| Decision class | Count |
| --- | ---: |
| Pass | 327 |
| Underpowered diagnostic | 35 |
| Confirmed fail | 7 |
| Failed incumbent-retention comparisons | 0 |

The decision vector is unchanged from the original-pixel publication-S/N
smoke. Subsequent byte and dispatch review separated two causes. First, the
direct-origin publication builder was not installed in the globals used by the
nested final writer, so every one of the 64 Continuum masks remained
byte-identical to the predecessor. Second, the sibling association source did
activate—ten association sidecars changed—but the rule required two attached
feature lineages and one connected significant-support component. Each of the
four governed failing pairs instead has only one attached or unambiguous
direct owner and no thresholded support bridge.

Read-only mechanism review on the three affected realizations found a common
bounded signal without selecting a new number from the result: one scale
feature persists uniquely to an adjacent scale around a single direct anchor,
and two applications of the existing scale-specific B3 footprint contain
exactly one additional unresolved owner. The proposed correction requires
that exact two-owner, mutually unique topology and whole-singleton
reconciliation; one-scale geometry, invalid gaps, resolved alternatives,
crowding, chains, and partial existing groups remain rejected. A retained-data
micro lane confirms that this rule groups all four governed edge, diffuse, and
bright-artifact pairs.

**Terminal verdict:** fail. The result is preserved and cannot be rescored.
The full replay remains blocked until the separately activated direct-origin
writer and persistent-feature influence correction publish a fresh smoke with
zero confirmed failures. No threshold, margin, comparator, measurement, or
photometric rule is changed.

## Activated persistent-feature-influence 128-case science smoke

**Terminal date:** 2026-09-01

**Evidence role:** viewed-development diagnostic smoke. The authoritative
atomic record is
`benchmark-results/phase-5/prospective-science-smoke-persistent-feature-influence.json`,
SHA-256
`3280088263f12ae6e63b1f81cc77c71d0b0e2f86539be7ea8459823b61886993`.

**Scientific question:** does activating direct-origin publication at the
actual final writer and allowing unique persistent-feature influence close the
seven remaining mask and topology failures without regressing compact or the
frozen Hebog incumbent?

The deterministic 64-compact/64-Continuum smoke used current product set
`21e27007...` and the exact incumbent product set `1c76f739...`. Compact
products remained byte-identical.

| Decision class | Count |
| --- | ---: |
| Pass | 334 |
| Underpowered diagnostic | 34 |
| Confirmed fail | 1 |
| Failed incumbent-retention comparisons | 0 |

The persistent-feature rule closes all six duplicate/split failures. The only
failure is pinned-master overall mask precision: the candidate is `0.05231`
worse against the frozen `0.05` practical margin, with observed paired
standard deviation `0.02480` and upper confidence limit `0.05698`.

Complete retained-input attribution corrects the prior explanation. Direct and
measurement owner labels are identical for all 64 Continuum cases, and all
segment-mask bytes match the preceding publication-S/N candidate. The active
source-association change, not a mask-origin change, closed the topology
failures. The residual false mask area is concentrated in sparse support seen
at only one scale: its precision is `0.54903`, compared with `0.92069` for the
dense branch and `1.0` for the 111 original-image high-S/N boundary pixels.

**Terminal verdict:** fail, with one bounded mask-support cause remaining. The
result is preserved and cannot be rescored. A prospective adjacent-scale
persistence rule must remove one-scale protrusions while retaining connected
owner bridges, then pass a fresh smoke before the cumulative replay opens.

## Publication-scale-persistence 128-case science smoke

**Terminal date:** 2026-09-01

**Evidence role:** viewed-development diagnostic smoke. The authoritative
atomic record is
`benchmark-results/phase-5/prospective-science-smoke-publication-scale-persistence.json`,
SHA-256
`9316882c606f66bcbf8937c4fc3f5aea331bb9ab9e8689953026016566bd9855`.

**Scientific question:** does exact adjacent-scale persistence remove noisy
one-scale publication support while retaining dense/high-S/N support, exact
persistent features, and necessary same-owner bridges?

Candidate `937737d...` sealed product set `86f703dc...` against the unchanged
incumbent product set `1c76f739...`. Compact products remain byte-identical.

| Decision class | Count |
| --- | ---: |
| Pass | 334 |
| Underpowered diagnostic | 35 |
| Confirmed fail | 0 |
| Failed incumbent-retention comparisons | 0 |

The formerly failing pinned-master overall mask-precision point regression
improves from `0.05231` to `0.04932`, now inside the unchanged `0.05` practical
margin. Its upper confidence limit is `0.05397`, so this small smoke remains
underpowered on that comparison. Released PyBDSF mask precision passes, every
incumbent comparison passes, and all earlier duplicate/split failures remain
closed.

**Terminal verdict:** zero confirmed failures; the governed larger replay is
open. The smoke is non-promotional and cannot itself qualify or release the
candidate. The 2,400-case replay must close the remaining power question and
pass all PyBDSF and incumbent-retention comparisons plus every binding safety
invariant without tuning; numeric absolute objectives remain report-only.

The first immutable full-replay command passed its complete no-write preflight
but stopped before candidate execution when the full path reloaded the
retained-reference verifier without its historical producer-source view. It
created no product or ledger and left a zero-byte scratch. The retry is bound
to a process-only dispatch repair; all scientific identities and gates remain
unchanged.

## Publication-scale-persistence cumulative replay

**Terminal date:** 2026-09-01

**Evidence role:** viewed-development cumulative regression. This is terminal
scientific evidence, not fresh qualification. The authoritative atomic ledger
is
`benchmark-results/phase-5/cumulative-regression-ledger-public-finder-publication-scale-persistence.json`,
SHA-256
`a9c6ed280308f863b149ad4d8dd7db59b8581cfa51cd585c004d4b69844881c8`.

**Scientific question:** does candidate `937737d...`, which passed the
128-case smoke, preserve compact science and the terminal-parent Hebog
incumbent while matching both PyBDSF references across the complete cumulative
population?

The replay covered 800 compact/blended and 1,600 Continuum realizations. It
used candidate source tree `9f8e4a67...`, configuration `2c907949...`, sealed
product-set manifest `77a71b5f...`, reconstructed reference `48209eae...`, and
closed Hebog baseline `a45303df...`. The evaluation-only completion verified
all 2,400 candidate products and all 9,600 retained reference runs before
publishing the ledger. No candidate product was rerun during completion.

### Scientific result

Compact science passes: all 143 Aegean and 450 dual-PyBDSF comparisons pass,
and there are no like-semantics compact regressions. Continuum does not pass.

| Continuum decision class | Count |
| --- | ---: |
| Pass | 101 |
| Confirmed fail | 31 |
| Underpowered | 11 |
| Indeterminate | 0 |
| Like-semantics incumbent regressions | 26 |

The 31 confirmed failures comprise nine duplicate-fraction, seven
integrated-flux-p95, seven position-p95, four split-fraction, three
integrated-flux-median, and one reliability endpoint. Important overall values
are:

| Metric | Hebog | Absolute requirement | Decision |
| --- | ---: | ---: | --- |
| Completeness | 1.0000 | at least 0.90 | Pass |
| Reliability | 0.9031 | at least 0.95 | Fail |
| Mask precision | 0.9184 | at least 0.85 | Pass |
| Mask recall | 0.9012 | at least 0.90 | Pass |
| Mask IoU | 0.8343 | at least 0.80 | Pass |
| Duplicate fraction | 0.0604 | at most 0.02 | Fail |
| Split fraction | 0.0604 | at most 0.10 | Underpowered |
| Merge fraction | 0.0000 | at most 0.10 | Pass |
| Integrated-flux p95 | 0.2699 | at most 0.25 | Fail |
| Position p95 | 0.9848 beam | at most 0.50 beam | Fail |

The failures concentrate in shell, above-compact-deblend-limit, scale-4,
tile-boundary, tile-corner, artifact, and varying-noise strata. Shell duplicate
and split fractions are `0.3456`; tile-boundary values are `0.1728`. The
terminal diagnostics found 1,821 cycle candidates and 1,817 accepted parents,
but no displaced-child candidates or acceptances. This is useful activation
evidence, not yet a complete causal attribution.

The frozen trade-off rule cannot turn this result into a pass. It permits only
small incumbent-relative movement inside a predeclared practical margin when
all absolute and both PyBDSF gates remain green and a related material gain is
documented. Here multiple absolute gates fail and 26 like-semantics statuses
regress, so `cumulative_science_regression_ready` and
`all_required_endpoints_pass` are both false.

### Operational result and next action

Two process defects were repaired without changing science. The first stopped
before candidate execution at historical retained-reference dispatch. The
second stopped after all candidate products but before publication because the
full compiler omitted the smoke-proven separation between measurement labels
and the refined publication mask. The evaluation-only completion reused the
hash-verified sealed products and published the terminal decision.

**Terminal verdict:** fail. The passing 128-case smoke was too small to expose
the complete population's topology and measurement tails. Before another
candidate or replay is frozen, perform a prospective root-cause review on the
already viewed products: compare failed full-population strata with the smoke
and terminal-parent incumbent, establish whether publication persistence,
source association, or source measurement caused each failure family, and
encode the confirmed causes in targeted analytic fixtures and a stratified
fail-fast smoke. Do not tune or rescore this ledger.

## Prospective root-cause review of publication-scale persistence

**Review date:** 2026-09-02

**Evidence role:** non-executable prospective review of already viewed
development-regression evidence. It does not change the immutable terminal
ledger's original `fail` status and does not authorize implementation or
execution. The exact review is
`config/contracts/phase-5-publication-scale-persistence-root-cause-pre-review.json`,
SHA-256
`77bd4b82cc7526b5e6f1b276ea16c887428c92f1c18126071405de69a07dce82`.

The most important finding is that two questions had been combined:

1. Did the candidate miss ambitious absolute quality objectives? Yes. The
   shell-dominated duplicate, flux-tail, and position-tail measurements are
   real and remain useful improvement targets.
2. Did it fail the later agreed Phase 5 replacement rule: no worse than both
   PyBDSF references, no material regression from the selected Hebog
   incumbent, and no safety failure? The retained evidence does not show that.
   It supports PyBDSF parity but lacks the full paired incumbent observations
   needed to prove retention.

The original cumulative wrapper still applied the historical absolute-gate
decision path. The prospective registry instead marks numeric absolute targets
as report-only longer-term objectives. It also requires observed paired
confidence limits to decide non-inferiority; planning variance is a design
audit, not a terminal gate. Finally, the wrapper's 26 “regressions” are status
transitions against older baseline `a45303df...`, not paired comparisons with
the selected whole terminal-parent incumbent `85d5807...`.

### What the retained evidence supports

| Prospective question | Retained evidence | Conclusion |
| --- | --- | --- |
| Compact science | 143 Aegean and 450 dual-PyBDSF comparisons passed; no historical compact regression | Green in the terminal ledger |
| Released PyBDSF parity | All 113 applicable stored Continuum upper confidence limits are within their frozen margins | Supported by stored analysis |
| Pinned PyBDSF `master` parity | All 113 applicable stored Continuum upper confidence limits are within their frozen margins | Supported by stored analysis |
| Selected-incumbent retention | 32 of 143 Continuum point estimates move adversely; none moves beyond its frozen practical margin | Encouraging, but point estimates do not prove paired non-inferiority |
| Full paired incumbent confidence | Exact full-population terminal-parent products were not retained | Missing; the global prospective decision is incomplete |
| Binding safety | No product, provenance, determinism, finite-measurement, or write-once failure is recorded | No safety failure observed |

This audit is not a retrospective rescore. It explains why the historical
ledger remains a valid failure under its original wrapper while also being
insufficient to decide the prospectively frozen contract.

### Scientific attribution

The named failure strata overlap. Every image has seven governed truth groups.
The shell group is simultaneously `above-compact-deblend-limit`,
`morphology-shell`, and `tile-corner`; `tile-boundary` contains shell plus
filament; `scale-4` contains shell plus four other astronomical groups; and
`varying-noise` contains all six astronomical groups. These labels therefore
cannot be counted as independent causal cohorts.

| Remaining split/duplicate cohort | Affected truth groups | Share of 676 |
| --- | ---: | ---: |
| Shell | 553 | 81.8% |
| Artifact | 118 | 17.5% |
| Diffuse | 3 | 0.4% |
| Mixed compact/extended | 2 | 0.3% |

Relative to terminal-parent incumbent `85d5807...`, the total falls from 1,437
to 676 affected truth groups: 720 artifact cases and 41 other non-shell cases
improve, while the 553 shell cases are unchanged. Reliability improves by
0.0510, overall duplicate and split fractions each improve by 0.06795, mask
precision improves by 0.03432, and mask IoU improves by 0.01371. Mask recall
moves by -0.01849, overall position p95 by +0.00857 beam, and scale-4 position
p95 by +0.01307 beam; all are inside their frozen 0.05 incumbent margins.

The dominant remaining absolute-quality issue is therefore shell
under-association: detected shell lobes remain separate catalogue sources.
That topology plausibly creates the high whole-source flux and centroid tails
when a lobe is compared with one shell truth source. This is high-confidence
mechanistic attribution, not row-level proof. Aggregate co-movement cannot
exclude an independent measurement-tail defect, and the large per-realization
candidate products were removed after compilation.

Publication-scale persistence is not the catalogue-topology cause. It refines
only the published detection mask; source association and measurement still
use stable measurement/direct-component labels. Its observed effect is the
mask precision/IoU improvement with a bounded recall trade-off. A generic tile
boundary or varying-noise failure is also excluded: shell accounts for every
boundary split and shell plus five sparse cases accounts for every varying-
noise split. Only four of 1,821 terminal cycles were rejected and displaced-
child persistence never activated, so that late rejection path cannot explain
553 shell splits.

### Prospective correction

Do not change source-finding science yet. First align the cumulative evaluator
with the already frozen prospective registry and retain enough paired evidence
to make the missing decision:

- publish separate PyBDSF-parity, selected-incumbent-retention, binding-safety,
  and absolute-objective sections;
- decide non-inferiority from paired realization confidence limits and report
  planning-variance deviations separately;
- retain hash-bound, array-free per-realization summaries that join truth
  group, association mechanism, topology, flux, and position outcomes before
  deleting large products; and
- freeze result-neutral shell, artifact, scale-4, corner, and varying-noise
  sentinels for fast diagnostics, then prospectively power one exact paired
  current/terminal-parent evidence population.

If that evidence confirms the current point-estimate picture, Hebog satisfies
the Phase 5 relative scientific requirement and shell association remains a
transparent longer-term improvement objective. If it demonstrates a material
incumbent regression, the truth-linked summaries will identify whether a
science repair belongs in association or measurement before another candidate
is proposed.

### Prospective paired-evidence implementation

**Prepared:** 2026-09-02

The approved evaluation-only correction is implemented without changing
Hebog's source-finding code or any closed result. The future decision now has
separate sections for Aegean parity, both PyBDSF parity checks, retention of
the selected terminal-parent Hebog incumbent, binding product/safety checks,
and report-only absolute quality objectives. Missing candidate evidence fails;
missing or inconclusive comparator evidence cannot pass. Observed paired
confidence limits decide non-inferiority, while a planning-variance miss is
reported separately and cannot change an observed pass or failure.

The prospective population contains 800 compact inputs and 1,600 Continuum
inputs, with 400 independent realizations from each of four Continuum datasets.
It covers all 1,187 frozen co-primary comparisons and has a conservative
familywise power lower bound of 0.90978. The result-neutral diagnostic lane
freezes 160 sentinel memberships over 155 unique shell, artifact, scale-4,
corner, and varying-noise inputs.

The future atomic record will retain array-free endpoint sufficient statistics
for every Continuum realization from current Hebog, the selected incumbent,
released PyBDSF, and pinned PyBDSF `master`. The sentinel subset additionally
retains truth-group-level association mechanisms, duplicate/split topology,
flux and position errors, source membership sizes, publication/association
mask overlap counts, and hierarchy reason counts. Each summary and each
complete summary set is hash-bound; no image or label array enters the record.
These sentinel diagnostics are explanatory only and cannot promote a result.

Complete no-write validation reproduced the exact population, power audit,
and sentinel selection; verified all 2,400 inputs and 9,600 retained reference
runs; constructed both 2,400-task candidate plans; exercised the evaluator
seams; and confirmed that both future scratch directories and the write-once
output are absent. No replay or scientific evaluation has been authorized by
this preparation. The next step is a separate named approval bound to the
final non-executable identity review.

That identity is now frozen in
`phase-5-prospective-paired-cumulative-replay-identity-review.json` at SHA-256
`4f5211ed16e2ea2cf844c1e48269f64de53b8aa62614483b29e2ee4f255d04fa`.
It binds expected execution SHA-256
`cef4e7642665b957c8b8a0194359ffa486591b1075dad982b8de70e8e6155424`.
The record grants no execution or evaluation authority.

### Paired replay operational failure and incumbent recovery

**Terminal date:** 2026-09-02

**Evidence role:** regression; operational failure before scientific decision

The authorized replay asked whether current Hebog retains the scientific
quality of terminal-parent Hebog while matching Aegean and both pinned PyBDSF
references on the same 800 compact and 1,600 Continuum inputs. Both Hebog lanes
completed all 2,400 products, but the evaluator correctly stopped before
publishing the write-once decision: historical-incumbent source memberships did
not partition the persisted Continuum labels.

This was not a scientific gate failure. The materializer verified and recorded
the historical source-tree identity, but worker processes imported the current
editable Hebog package. Those workers therefore combined current separate
measurement/publication labels with a historical product schema that stores
only one label plane. In the resulting invalid incumbent set, 52 associated
sources were partly absent and 174 were fully absent from that plane. Relaxing
the evaluator would invent support, so its validation remains unchanged.

| Product set | Products | Identity | Disposition |
| --- | ---: | --- | --- |
| Current Hebog | 2,400 | `6bcb2959...` | Valid; retain and reverify |
| Mixed-lineage incumbent | 2,400 | `b373cafe...` | Preserve as non-evaluable failure evidence |
| Authentic historical incumbent | 2,400 | `ea12ce03...` | Reconstructed and fully verified |
| Paired decision | 0 | — | Not published; no scientific verdict |

The bounded repair adds a worker-import origin guard and reconstructs only the
incumbent in a new namespace under immutable historical execution checkout
`c1614c2...`. Each reconstructed association must exactly partition its
persisted labels. A subsequent evaluation-only completion will combine that
verified incumbent set with the unchanged current set under the same 1,187
comparisons, safety gates, confidence rules, practical margins, retained
references, and baseline. No current candidate or viewed-data execution,
source-finding change, threshold tuning, or rescoring is part of the repair.

The reconstruction completed under review `ed968311...` and decision
`10e7f098...`. Recovery record `b302967f...` binds all 800 compact and 1,600
Continuum products, historical producer program `1e9483fc...`, wrapper
`2c40315f...`, and authentic reconstruction-marker product set `ea12ce03...`;
no current-candidate execution or policy change occurred. The evaluator's
normalized representation of the same incumbent artifacts is `8dbc9dff...`.
Evaluation-only pre-review `a156ddae...` requires both named identities and
both complete sets to be rehashed, then requires the unchanged evaluator seams
to pass before the absent paired decision can be written once.

### Paired evaluation-only diagnostic failure

**Terminal date:** 2026-09-03

**Evidence role:** operational failure after binding compilation and before
atomic scientific publication

The exact evaluation-only completion under review `75d46048...` and decision
`4624d6d9...` reverified both 2,400-product Hebog sets and all 9,600 retained
reference runs. It then compiled the frozen paired comparisons but stopped
while constructing the separate result-neutral truth-linked tail diagnostics.
No atomic paired decision was published, so the in-memory binding result is not
scientific evidence and no pass or fail may be inferred from it.

The failure was an adapter-order defect. For Hebog, associated catalogue-source
membership is defined over the measurement label plane, while the publication
label plane intentionally omits low-persistence components. The tail adapter
called source reconstruction with publication labels before it selected the
measurement labels. The exact membership guard therefore reported that valid
source memberships did not partition the wrong native-support plane. The guard
must remain strict.

| Boundary | Terminal result | Interpretation |
| --- | --- | --- |
| Product rehash | Passed | Current `6bcb2959...`; incumbent evaluator `8dbc9dff...` |
| Reference rehash | Passed | 9,600 retained runs |
| Binding paired compilation | Completed in memory | Not publishable or interpretable without the atomic record |
| Result-neutral tail diagnostics | Failed | Measurement/publication label-selection order defect |
| Atomic paired decision | Absent | No scientific verdict |

The prospective correction selects Hebog's association plane before catalogue
source reconstruction, uses that measurement plane for membership recovery,
and continues using publication labels for published-mask statistics. A fixture
must make the planes deliberately different and verify both roles. This changes
no source-finding product, threshold, comparator, confidence rule, margin, or
scientific gate. Any completion retry requires a new exact evaluation-only
identity and decision. The complete prospective repair review is
`config/contracts/phase-5-prospective-paired-tail-diagnostic-repair-pre-review.json`,
SHA-256 `e1130b9b6b8825ab22e8f74f71f9429f98fdbf803312d45a54d0ec36647fb932`.

The approved correction is now implemented as an evaluation-only overlay; the
failed evaluator remains byte-for-byte unchanged. Its regression fixture gives
Hebog two measurement supports but only one published support and proves that
source composition receives the former while published-mask statistics receive
the latter. Reference finders continue using publication labels for both roles,
and the strict malformed-partition rejection still passes. A complete no-write
preflight rehashed both 2,400-product Hebog sets and all 9,600 reference runs,
verified the repaired seam, and confirmed that no candidate execution or atomic
decision occurred. Repair commit `0ce3de6...` repeated the complete proof from
its clean committed revision. The exact non-executable evaluation-only review
is SHA-256 `5572148d6604f52988fe256beb0ec1e2046c305f2e0d3a2d50c0ee862f2f9585`,
binding expected execution SHA-256
`17f41e8ad0b48df3adc5b6248dd585f68036c6c7d8e72e4386724e78ce73e954`.
It grants no execution authority; retrying the several-hour compiler requires
a separate named one-use approval.

### Paired tail-repair evaluation topology failure

**Terminal date:** 2026-09-03

**Evidence role:** operational failure after binding compilation and before
atomic scientific publication

The approved repaired completion ran from immutable commit `07cbae3...` under
review `5572148d...`, decision `3de3f6fc...`, and expected execution
`17f41e8a...`. It reverified both sealed 2,400-product Hebog sets and all 9,600
retained reference runs. The measurement/publication-label repair succeeded,
and the binding paired science again compiled in memory. The separate
result-neutral tail then failed before writing the atomic decision, so no
scientific result may be inferred.

| Boundary | Terminal result | Interpretation |
| --- | --- | --- |
| Product and reference rehash | Passed | Exact current, incumbent, and retained-reference evidence preserved |
| Label-role repair | Passed | Source membership used measurement labels; mask statistics used publication labels |
| Binding paired compilation | Completed in memory | Unpublished and therefore not interpretable |
| Truth-linked topology tail | Failed | Multi-support associated-source record reached a single-support helper |
| Atomic paired decision | Absent | No scientific verdict |

The topology helper expects each catalogue row to expose one `support_label`.
Hebog's associated source record correctly exposes a canonical
`support_labels` union because one measured source can span several native
components. The previous repair test stubbed the downstream summary builder,
so it proved label-role separation but missed this next real interface seam.

The result-neutral repair is now implemented. Associated-source rows dispatch
through the existing source-union association context while native supports
remain separate topology evidence; legacy single-support PyBDSF rows retain
their unchanged path. Exact support partitions, member counts, mixed
semantics, and deterministic ordering are checked explicitly.

The new real-product tail check then caught a second interface gap before an
evaluation retry: the direct diagnostic path bypassed the binding compiler's
sidecar-aware loader and attempted to infer Hebog membership heuristically.
The repaired path now loads each checksum-verified `source-association-json`
sidecar for current and incumbent Hebog and retains the legacy path for both
PyBDSF references. Its no-write real-product check passed 620 array-free
summaries across 155 unique inputs (155 per finder), digest `a9d50450...`, with
no promotion effect. The complete integrity pass also rehashed both 2,400-
product Hebog sets and all 9,600 retained reference runs successfully.

These checks establish that the sealed products can be reused and neither
Hebog nor PyBDSF needs to be rerun. They do not recover the unpublished
in-memory comparison: the atomic paired decision is still absent, so a new
frozen evaluation-only identity and separate one-use approval remain required.
Non-executable review `7889c11f...` now binds implementation commit
`9f6cb556...`, expected execution `ad407f73...`, the exact product/reference
proof, and the real-tail digest. Every authorization is false; evaluation may
begin only after separate exact one-use approval.

### Prospective paired topology-repair evaluation

**Terminal date:** 2026-09-04

**Evidence role:** terminal regression evaluation; scientifically valid but
incomplete because four incumbent-retention comparisons remain inconclusive

The evaluation asked whether publication-scale-persistence Hebog retains the
best closed Hebog result while matching both released PyBDSF and pinned PyBDSF
`master`, without weakening safety or using ambitious absolute objectives as
release blockers. It reused the sealed 2,400-product current set
`6bcb2959...`, sealed 2,400-product incumbent set `8dbc9dff...`, and all 9,600
retained reference runs; no finder was rerun. The population contained 800
compact and 1,600 Continuum inputs. Analytic injected truth supplied the
scientific reference, and all comparisons used the pre-registered paired
confidence limits and practical margins.

Atomic decision `5bced804...` has canonical record identity `170361b1...` and
is bound to immutable checkout `a2ddcc5...`, review `7889c11f...`, execution
decision `4e1bbbaf...`, expected execution `ad407f73...`, and repaired
evaluator `39a568ba...`.

| Binding comparison | Pass | Underpowered | Fail | Interpretation |
| --- | ---: | ---: | ---: | --- |
| Aegean parity | 143 | 0 | 0 | Fully passes |
| Released PyBDSF parity | 338 | 0 | 0 | Fully passes |
| Pinned PyBDSF `master` parity | 338 | 0 | 0 | Fully passes |
| Incumbent Hebog retention | 364 | 4 | 0 | Four position-tail checks are inconclusive |
| Binding safety | 5 | 0 | 0 | Fully passes |

The four inconclusive checks are Continuum position-error p95 for
above-compact-deblend-limit, morphology-shell, scale-4-beam, and tile-corner.
Their observed incumbent-relative movements are only `0.0030`–`0.0131` beams,
well inside the frozen `0.05`-beam practical margin, but their paired upper
confidence limits are `0.0542`–`0.0564` beams. The data
therefore show no material regression, but they do not yet exclude one with
the required confidence. The first, second, and fourth endpoints describe the
same shell observations: their retained endpoint payloads are identical across
all 6,400 finder/input summaries. Scale-4-beam is the other distinct evidence
pattern. A power extension must preserve all four registry checks but must not
treat the three shell aliases as independent information.

All 1,183 other co-primary comparisons pass, including every comparison with
both PyBDSF versions, and all safety invariants pass. The correct verdict is
`incomplete`, not `fail` and not release-ready. This is strong evidence that
Hebog has reached PyBDSF scientific parity on this regression population, but
the project's separate no-regression rule requires a small pre-registered,
seed-disjoint current-versus-incumbent power extension before Phase 5 can
close. The 15 absolute position objectives remain report-only and do not alter
this verdict. No tuning, rescoring, qualification, cutover, or release is
authorized by this result.

## Adaptive-background bright-extended development lane

**Terminal date:** 2026-09-04

**Evidence role:** prospective, seed-disjoint development evidence; not
qualification, a PyBDSF comparison, or release evidence

**Scientific question:** when Hebog's strict 75-sigma adaptive background/RMS
trigger activates, does refinement preserve the support, segmentation, and
photometry of bright extended sources better than the same frozen finder with
only coarse background estimation?

The 144 analytic 512-by-512 images covered shell, curved-filament, and mixed
compact/extended morphologies; 4-, 8-, and 12-beam scales; two restoring
beams; flat and varying noise; interior and tile-corner placement; and nominal
60-, 75-, and 90-sigma trigger cohorts. Four independent noise seeds populated
each cell. The adaptive candidate and coarse-only diagnostic control were
paired on every image. The repair completion reused all 144 sealed serial
products and ran only the 12 missing existing-Dask comparisons; it did not
rerun either serial arm.

| Morphology | Geometry groups passing | Main terminal evidence |
| --- | ---: | --- |
| Shell | 0 / 4 | Every group exceeded paired support-recall and mask-IoU margins; three also missed the support-recall median floor and two exceeded the split floor. |
| Curved filament | 3 / 4 | Support, masks, and flux were strong; one varying-noise group failed only because its split fraction was `0.667` against the `0.25` floor. |
| Mixed compact/extended | 0 / 4 | All groups exceeded the paired flux margin, with widespread hard failures in flux, mask IoU, and support recall; two also exceeded the split floor. |

All 144 inputs were product-valid and complete. The 60-sigma negative controls
remained below the trigger, every 90-sigma positive control activated over
truth, and all 12 caller-owned two-worker Dask results were scientifically
identical to Serial. This separates the scientific failure from the earlier
worker-result deserialization defect and from executor nondeterminism.

The retained sentinels are consistent with bright extended emission
contaminating local adaptive background/RMS estimation and being absorbed from
source support: median in-support background error was `0.188`-`0.449` true
RMS for shell groups and `0.576`-`2.261` for mixed groups, compared with
`0.061`-`0.125` for curved filaments. That pattern is a root-cause hypothesis,
not yet proof of the unique failing mechanism; support construction,
measurement, and publication effects still need to be separated before a
source-finding change is proposed.

Atomic decision SHA-256 `ff415f064f4ea7daa9254338041e52ad15d41b84edf692602092134850218026`
has canonical record identity
`4f6e37241ee58420c30f8416c784e6c57efbd6e55eae32c1e878757116d865ab`.
It is bound to immutable execution commit `7c92b26...`, preserved product set
`c9212f3a...`, original lane review `f9ccef67...`, repair review `d61b9643...`,
completion review `d2a664f5...`, completion program `8f7c9619...`, and
completion execution decision `0d5c071b...`.

The terminal verdict is `fail`: the known adaptive-background risk is real in
this previously uncovered bright-extended regime. This does not alter the
closed cumulative comparison showing PyBDSF parity on its regression
population, whose source peaks did not cross the adaptive trigger. It does
block opening final held-out qualification with the current candidate. The
next step is an approval-gated, non-executable root-cause review followed by a
test-first prospective correction and a rerun of this small development lane;
no threshold change, tuning, rescoring, qualification, cutover, or release is
authorized by this result.

## Prospective evaluation contract after terminal-cycle repair

**Frozen date:** 2026-08-31

**Evidence role:** non-executable prospective governance. This record does
not change, rescore, or replace any campaign result above.

The next candidate must pass every applicable comparison to released PyBDSF,
pinned PyBDSF `master`, and Aegean, while also retaining the scientific quality
of one complete closed Hebog incumbent. A small incumbent-relative movement is
acceptable only inside the frozen practical margin, with all applicable
relative comparisons and safety invariants passing and a substantial
scientifically related improvement reported explicitly. It cannot compensate
for a failed or materially regressed check. Ambitious absolute numeric targets
remain visible as longer-term objectives; finite products, valid schemas and
provenance, determinism, and write-once publication remain binding safety
requirements.

| Frozen scope | Count |
| --- | ---: |
| Compact binding endpoints | 225 |
| Continuum binding endpoints | 143 |
| Continuum longer-term objectives | 15 |
| Endpoints per PyBDSF reference | 338 |
| Applicable Aegean endpoints | 143 |
| Incumbent-Hebog retention endpoints | 368 |
| Total co-primary comparisons | 1,187 |

The endpoint registry is
`config/contracts/phase-5-prospective-science-endpoint-registry.json`, SHA-256
`095354bce2f34ae257574f9168770a194f1f5b00024db0ec5bcafdafba006a7e`.
The decision contract is
`config/contracts/phase-5-prospective-science-decision-contract.json`, SHA-256
`f70f321397618b9f63d3dd03d650a5bbc73f8aad5e5fa91f15a198a99bdb38f9`.

The retention baseline is the whole terminal-parent candidate `85d5807...`
and ledger `e2ee663f...`; it is not a synthetic best-per-endpoint envelope.
Because its raw realization products were not retained, a later governed
campaign must reexecute that exact incumbent on the same inputs to produce
paired realization-level evidence. Planning variance will size the study and
audit assumptions, but only the observed paired confidence limit will decide
non-inferiority. Missing or underpowered binding evidence cannot pass.

The contract was activated under the recorded conditional user authority only
after its test-first evaluator, no-write verification, and fail-fast lanes
passed. The first smoke failed as documented above. The later
publication-scale-persistence smoke has zero confirmed failures and therefore
opens exactly one larger cumulative replay; it does not itself satisfy the
power audit or authorize qualification. Tuning, rescoring, cutover, and release
remain outside this authority.

## Source-owned footprint-guard development lane

**Terminal date:** 2026-09-05

**Evidence role:** development and process validation, not cumulative
scientific parity or qualification.

The lane asked whether the estimator-footprint source guard preserved or
improved the 12 adaptive-background geometry groups relative to the paired
coarse control while retaining deterministic Serial/existing-Dask behavior.
It completed all 144 candidate/control inputs and all 12 Dask comparisons.
The trigger seam and executor-invariance gate passed, 11 geometries passed,
and one mixed compact/extended geometry failed only the paired split margin.

| Terminal check | Result |
| --- | ---: |
| Inputs completed | 144 / 144 |
| Geometry groups passing | 11 / 12 |
| Serial/existing-Dask comparisons | 12 / 12 identical |
| Trigger seam | Pass |
| Binding failure | One split-margin result |

The failed seed reported five candidate catalogue rows, three of which the
development matcher called truth-linked, against two coarse rows with one
called truth-linked. Exact source-owned component support gives a different
and scientifically appropriate account: only one candidate row intersects the
injected three-sigma truth support, with 440 overlapping pixels; each of the
other four rows has zero overlap. They are nearby reliability detections, not
fragments of the injected source. The coarse result also has one linked source.

This is an evaluator defect rather than evidence that Hebog science became
worse. The matcher used catalogue centroids inside the broad source's bounding
box expanded by 1.5 beams, so nearby sub-threshold noise islands could be
mistaken for fragments. The immutable terminal decision remains failed and is
not rescored. The prospective repair links each public source through its own
source-owned label support and keeps every non-overlapping row and its flux as
explicit reliability evidence. Its root-cause record is
`config/contracts/phase-5-source-owned-footprint-guard-lane-root-cause-review.json`.

Atomic terminal SHA-256 is
`8add4b13568258219b3b52b5ae017a106d22143314995a547e6b8cd059a6b2ea`.
The next gate is a fresh 144-input development lane using the corrected frozen
evaluator. Cumulative dual-PyBDSF replay and seed-disjoint held-out
qualification remain ordered behind a passing fast result.

## Source-support-linkage development retry

**Terminal date:** 2026-09-05

**Evidence role:** development and process validation, not cumulative PyBDSF
parity or qualification

The repaired retry completed all 144 candidate/control pairs and all 12
caller-owned-Dask comparisons. Product validity, trigger behavior, and exact
Serial/Dask science identity passed. Eleven of the 12 geometry groups passed;
one varying-noise, eight-beam mixed compact/extended geometry failed the
historical maximum-single-image flux and split retention margins.

| Check | Terminal result |
| --- | ---: |
| Candidate/control pairs | 144 / 144 |
| Serial/existing-Dask comparisons | 12 / 12 identical |
| Geometry groups | 11 / 12 pass |
| Failed input | Boundary seed `2026950137` |
| Flux-error movement on that seed | `+0.053766` |
| Support-recall movement on that seed | `+0.116412` improvement |
| Boundary-cell median flux movement | `-0.005116` improvement |
| Boundary-cell median support movement | `+0.051527` improvement |

The split was not a resolved second piece of the injected source. A bounded
deterministic reproduction found that the dominant catalogue row owns 441
truth pixels, while the second row touches only two pixels at the truth
boundary. The any-intersection matcher called both rows truth-linked. The
production hierarchy had no multiscale parent evidence linking the nearby
rows, so merging them would be scientifically unsafe; all such rows remain
explicit reliability detections.

The terminal decision remains failed and is not rescored. Its SHA-256 is
`ea44147e3f1e786e3f8f53084434da55c16b6d8b7021baa1eb12985f4a5138d6`.
Root-cause review `25f6bf0f...` defines a prospective seed-disjoint replication:
a row must own at least the existing seven-pixel minimum-island support inside
truth to count as a fragment, and paired retention binds to each four-seed
trigger cell rather than the single noisiest image. Worst-image movements
remain visible tail sentinels, all margins remain unchanged, and final
per-geometry released/master PyBDSF and incumbent comparisons remain strict.
No Hebog source-finding algorithm changes in this repair.

The seed-disjoint replication was prepared with two additional fail-closed
checks. Both found wrapper-only defects before scratch creation or candidate
execution: first, a nested `runpy` worker could not be imported by a spawned
process; second, the overlay omitted its new process-review binding. Both
failed identities remain immutable. The repaired wrapper now passes an actual
candidate/control process smoke on an already-viewed seed and a complete
no-write preflight for all 144 candidate, 144 control, and 12 existing-Dask
slots. A final freezer-only Ruff formatting change was rebound before execution
to validation-clean identity `6289b9ce...` and decision `8cd60e66...`. This is
process evidence only; the fresh replication result is still required before
any cumulative replay.

## Seed-disjoint source-support-linkage replication

**Terminal date:** 2026-09-05

**Evidence role:** development retention and executor-invariance evidence, not
cumulative PyBDSF parity or qualification

The fresh replication ran from immutable tooling commit `eec48cc...` against
unchanged source-finding candidate `0b9e132...`. It completed 144 paired
candidate/coarse-control inputs across 12 geometry groups, then repeated one
above-trigger case per group on an existing two-worker Dask scheduler.

| Check | Terminal result |
| --- | ---: |
| Candidate/control pairs | 144 / 144 |
| Binding geometry groups | 12 / 12 pass |
| Binding failures | 0 |
| Serial/existing-Dask comparisons | 12 / 12 identical |
| Trigger seam | Pass |
| Groups missing non-binding improvement objectives | 2 |

Every geometry retained the reviewed scientific quality of its paired coarse
control under the prospective four-seed cell-median rule. Maximum
single-realization movements remain visible as non-binding tail sentinels. Two
mixed compact/extended groups still miss aspirational flux, mask, or support
objectives, so they remain improvement targets rather than being hidden; they
did not cross a frozen retention gate. The lane therefore closes the immediate
adaptive-risk regression concern without claiming PyBDSF parity.

Atomic terminal SHA-256 is
`0978d4a3653ce9bd4b1244ea1125142400607d04c330758ee3b4a495f4193eae`.
The next gate is the exact cumulative dual-PyBDSF replay, followed only on a
pass by fresh seed-disjoint held-out qualification.

## Public component-topology correction

**Review date:** 2026-09-05

**Evidence role:** prospective source correction; the refreshed Hydra images
are visual diagnostics and have not been reexecuted or rescored.

The completed notebook refresh exposed a semantic and scientific mismatch.
The plot showed one marker per associated Hebog source but one marker per
PyBDSF Gaussian component, so it visually compared different catalogue
levels. The stored Hebog products also contained a real defect: nearly every
connected support parent had one component, and an independent beam-scale
local-maximum census flagged 122 multi-peak parents with fewer published
components than diagnostic peaks. Local maxima are not themselves asserted
astrophysical sources, but a two-dimensional unequal-Gaussian analytic fixture
reproduced an erroneous one-component result.

The root cause is the compact partition implementation. It passed the earlier
one-dimensional bridge fixtures, but constructing a marker-distance image and
passing it to SciPy `watershed_ift` could give almost the entire
two-dimensional island to one marker. The remaining few pixels were then
correctly merged by the minimum-area rule, hiding an otherwise admissible
second peak. The prospective correction assigns the exact parent to its
nearest canonical marker only in the new public component-topology path,
retains the intensity saddle as the scientific merge decision, applies that
bounded topology before public Gaussian measurement, and proves that neither
direct nor expanded measurement support changes. A full equivalence check
caught and rejected applying that ownership change to the established Phase 3
compact path because it regressed blend photometry. One connected support can
now produce several Gaussian components and one associated source without
changing the previously qualified compact curve. Over-bound parents remain
retained and are exposed through explicit deferral telemetry.

The previous candidate's sealed product set `195a5a36...` remains valid for
its exact old source tree but cannot qualify the corrected science. The old
incumbent and 9,600 released/master PyBDSF reference products remain reusable.
The prospective correction is local commit `6166779...`, source tree
`e1925831...`, with unchanged configuration `2c907949...`. Non-executable
notebook/comparison identity `897845b9...` binds this exact composition and
requires separate associated-source and Gaussian-component catalogues so the
two scientific levels cannot be confused in plots or counts.
The previously observed final-evaluator `_load_materializer` dispatch error is
separately repaired at the raw overlay boundary. A new candidate must first
pass fixtures, complete no-write validation, and the fast executor-invariance
lane, then run a fresh 2,400-product cumulative candidate stage. No threshold,
saddle margin, comparator, or acceptance gate was changed after viewing the
notebook results.

## Public unseeded-parent retention correction

**Review date:** 2026-09-05

**Evidence role:** prospective source correction; no notebook case or
cumulative scientific result was published by the failed attempt

After the refresh orchestration was rebound to the multi-peak candidate, its
first `sdc1-sparse-y06-x10` case reached the public component topology and
stopped with `compact island has no eligible deblending peak`. The FITS
`BLANK` and `datfix` warnings were unrelated. The case had an admitted
multiscale parent but no finite direct-residual peak strictly above the compact
deblender's seed threshold. This is a valid relationship between the two
stages: multiscale support admission does not prove a direct-residual compact
seed exists.

The prospective correction retains exactly one component for that parent and
preserves its complete direct and measurement support. It cannot invent a
split without evidence, and it does not weaken the standalone Phase 3 compact
kernel's fail-closed no-marker contract. Boundary fixtures cover peaks below
and exactly at the strict gate, while above-gate one-, two-, and three-peak
paths retain their established behaviour. Component topology has complete
line and branch coverage; focused public Serial/Dask integration, all compact
equivalence tests, documentation, and installed-wheel smoke validation pass.

The successor candidate is commit `3ed6086...`, source tree `c1fb96c4...`,
configuration `2c907949...`, and scientific composition `d160acd4...`.
Non-executable identity `6f41d726...` binds those exact values and supersedes
the never-executed multi-peak notebook identity `897845b9...`. The failed
refresh staging contains only its request and empty first-case directories;
it is not reusable evidence. The next permitted notebook attempt must use the
successor identity, and the governed fast regression lane still precedes any
cumulative replay.

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
