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
| R6 source-catalogue cumulative terminal (2026-09-09) | Test original repaired candidate `db8936b...` on the complete retained regression population using native source measurements | Scientific fail; process completed | 885 binding comparisons pass, 288 fail and 14 are underpowered. Both PyBDSF references, Aegean and incumbent retention have failures; all five safety checks pass. No fresh sentinel or Phase 5 closure follows. |

The latest result is the [R6 terminal snapshot](#2026-09-09-r6-cumulative-terminal-scientific-failure).
Earlier results below remain candidate-specific historical evidence.

The apparent contrast between final qualification and later failure is useful,
not contradictory. The final qualification showed that the frozen candidate
passed its declared untouched synthetic population. The public campaign then
exposed behaviours absent from that population. Those viewed cases became
development-regression evidence, and the later cumulative replays test proposed
corrections against the expanded evidence set.

## 2026-08-29: source-association measurement repair

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

## Version-8 public owner-domain fast regression

**Terminal date:** 2026-09-05

**Evidence role:** development retention and executor-invariance evidence, not
cumulative PyBDSF parity or qualification

The version-8 public candidate `95cfc76...`, source tree `8da21e86...`, and
unchanged configuration `2c907949...` ran from immutable tooling commit
`ec4be4d...`. The lane reused the previously passed seed-disjoint population
without changing its 12 geometry groups, four-seed cell-median rules, hard
truth floors, practical margins, trigger seams, or non-binding tail policy.
It completed 144 candidate/control pairs and one caller-owned two-worker Dask
comparison per geometry.

| Check | Terminal result |
| --- | ---: |
| Candidate/control pairs | 144 / 144 |
| Binding geometry groups | 12 / 12 pass |
| Binding failures | 0 |
| Serial/existing-Dask comparisons | 12 / 12 identical |
| Trigger seam | Pass |
| Groups missing non-binding improvement objectives | 4 |

Every geometry retained the reviewed scientific quality of its paired coarse
control. Two shell groups missed aspirational split objectives and two mixed
compact/extended groups missed aspirational absolute flux, mask, or support
objectives; these remain visible improvement targets and did not cross a
binding retention gate. The lane therefore closes the immediate regression
risk for the component-topology, unseeded-parent, and publication-owner-domain
corrections. It does not establish cumulative PyBDSF parity or held-out
qualification.

Atomic terminal SHA-256 is
`a274888dab12bd5a1623310b35ba3f9a90ff14f9fd5249d118cd2a1c8b778348`.
It binds identity review `29e6f247...`, one-use execution decision
`94bf8bf3...`, and manifest `8d539477...`. The next gate is a fresh
2,400-product cumulative current-candidate stage; its evaluator must reuse the
authentic incumbent and retained released/master PyBDSF products.

## Version-8 public owner-domain cumulative evaluation

**Terminal date:** 2026-09-06

**Evidence role:** cumulative regression evidence; evaluation-only reuse of
sealed current, incumbent, Aegean, and released/master PyBDSF products

The exact evaluation-only completion for candidate `95cfc76...`, source tree
`8da21e86...`, and unchanged configuration `2c907949...` exited successfully
and atomically published an `incomplete` decision. It compiled the sealed
2,400-product current set `f43cb274...` against the authentic incumbent and
all 9,600 retained reference runs; it executed no finder.

| Binding section | Terminal result |
| --- | ---: |
| Aegean parity | 143 pass / 0 unresolved |
| Released/master PyBDSF parity | 676 pass / 0 unresolved |
| Incumbent-Hebog retention | 364 pass / 4 underpowered |
| Binding safety | 5 / 5 pass |
| All binding comparisons | 1,183 pass / 4 underpowered / 0 fail |

Compact science passes every applicable comparison. Continuum passes every
dual-PyBDSF and Aegean comparison and 364 of 368 incumbent-retention checks.
The four unresolved checks are position-error p95 aliases for
`above-compact-deblend-limit`, `morphology-shell`, `scale-4-beam`, and
`tile-corner`. Three aliases share one shell evidence pattern: its observed
positive regression is `0.003013` beam and its upper confidence limit is
`0.056371` beam against the frozen `0.05`-beam margin. The scale-4-beam
pattern has observed positive regression `0.013073` beam and upper confidence
limit `0.054222` beam. The overall Continuum position-p95 comparison passes
with an upper confidence limit of `0.036636` beam. These are confidence gaps,
not observed failures beyond the practical margin, but the frozen rules do
not permit a pooled pass to hide an underpowered binding stratum.

All finite-measurement, product-validity, provenance, Serial/existing-Dask,
and write-once-publication safety checks pass. Longer-term absolute objectives
remain report-only. Nevertheless,
`cumulative_science_regression_ready=false` and
`all_required_endpoints_pass=false`, so Phase 5 cannot close and held-out
qualification remains closed. No threshold, margin, comparator, confidence
rule, or result was changed after inspection.

The atomic decision file SHA-256 is
`fe4afbe912d5acfe3086141fa6840effbbbe92d7a40343fda7791880b808a0ed` and
its canonical record SHA-256 is
`8d69ef44bfd4d134c31bb9f00f4c6771237f2d71e9dbbe6dd941e277514b088e`.
The next step is a prospective, power-checked retention-confirmation design
focused on the two distinct unresolved evidence patterns. It should reuse the
sealed evidence wherever scientifically valid, execute no PyBDSF work for the
incumbent-only question, preserve every frozen gate, and fit the requested
sub-12-hour closeout envelope. It must be frozen before any new realization
is viewed or executed.

## Cumulative uncertainty acceptance and compact closeout design

**Decision date:** 2026-09-06

**Evidence role:** human acceptance of a narrow residual uncertainty for
progression, followed by a production audit and a non-executable fresh-sentinel
design

The terminal cumulative decision above remains exactly `incomplete`. Its four
underpowered aliases, two distinct incumbent position-p95 evidence patterns,
false readiness flags, margins, and confidence limits have not been changed or
relabelled. The scientific owner decided that the 4,608-image independently
powered incumbent-only confirmation was not proportionate before closeout:
both point movements are inside `0.05` beam, the overall position-p95 upper
bound passes, 364 of 368 incumbent checks pass, and every released/master
PyBDSF, Aegean, and safety comparison passes with zero scientific failures.
This is a scoped uncertainty acceptance, not a statistical pass or permission
to claim fully powered incumbent non-inferiority. Exact acceptance record
SHA-256 is `a33635b5...`.

A bounded review of the exact `95cfc76...` production source tree then found no
release-blocking correctness, safety, or public-contract defect. The installed
top-level `hebog.find_sources` path, public records, write-once materialization,
reference profile, invalid-input behavior, and Serial/existing-Dask semantics
are covered by the focused 141-test public/science matrix; Ruff and Pyright are
clean. The candidate source remains `8da21e86...`, so none of the cumulative
science is invalidated. Two non-blocking improvements are disclosed for later
work: make the user-result composition digest transitive rather than curated,
and move stable production composition out of the `hebog.validation`
namespace. The cumulative and future terminal records already bind the full
source tree, so neither issue can misidentify this governed candidate. Exact
audit SHA-256 is `e8b8fe92...`.

The remaining fresh check is deliberately small. Non-executable pre-review
`84c44215...` specifies 168 new seed-disjoint images: all 36 known
adaptive-background risk cells at four realizations each, plus six compact
public-contract guard cells at four realizations each. The exact public Hebog
candidate and Rapthor's released PyBDSF `1.14.1` reference account for 336
runs; 12 representative caller-owned Dask comparisons bring the total to 348.
Pinned-master PyBDSF, Aegean, compact, and incumbent evidence is retained from
the cumulative campaign without reexecution. The sentinel is expected to take
one to four hours, has an eight-hour ceiling and an 8-GiB free-space preflight,
and may not open until its generator, manifest, runtimes, evaluator, one-look
rules, immutable checkout, and write-once output are exactly frozen. Because
four realizations per cell are not a powered non-inferiority study, the
sentinel can falsify closeout but cannot independently create the parity claim.

That implementation is now complete without opening an input. Frozen identity
review `d879c65e70dd0d280d237f4d28212ceccee45069aed967ad5c038fc7155f4cb2`
binds manifest
`1dc84802f4a59848d91d6ca7af8c3795770330f4d816f337135bf18f3171feb2`,
implementation decision
`66e7a886946a99c04501976ffc8cc582e29e7d3580d21908f07aa1aa91c2fd37`,
and expected execution
`df6b831b4eda14a9740aa09f6a8d0ebf152edd9778e98f13ff0cf660fac897ee`.
The 42-cell manifest includes 144 extended-risk images and 24 compact guards,
including unequal two-peak, connected three-peak tile-corner, non-square
varying-noise, edge, near-threshold, and invalid-pixel cases. Fourteen focused
tests pass. The complete no-write preflight verified all 168 seeds are disjoint
from 20,917 historical seeds across 46 manifests, verified the exact
released-PyBDSF image and dependency inventory, found 11.8 GiB free, and
confirmed that no finder execution or output publication began. The identity
is deliberately non-executable: a separate exact one-use decision and human
approval are required before the unopened population may be generated. An
initial approval of identity `0b387281...` could not be consumed because the
repository hook subsequently canonicalized one pre-review JSON key order.
Replacement identity `d879c65e...` changes no science, population, margin,
runtime, or expected execution, but requires renewed exact approval.

The renewed one-use execution began from immutable commit `956e8d0...` on
2026-09-06 and terminated after about 130 seconds, before recording a completed
realization and before running released PyBDSF. Its atomic terminal decision is
`operational-fail`, has SHA-256 `965454ea...`, and records `ValueError: Hebog
segment island identity is malformed`. Static diagnosis found that the
successor compiler accepts only the legacy `hebog-segment-N` catalogue
identity, while the frozen current public result intentionally exposes stable
source/component identities after the owner-domain repair. The result contains
no scientific comparison and does not change the cumulative parity evidence.
The output and scratch remain preserved; a test-first compiler repair,
replacement frozen identities, and a new exact one-use approval are required
before the unchanged sentinel may run.

## Compact held-out sentinel terminal scientific failure

**Decision date:** 2026-09-07

**Evidence role:** fresh seed-disjoint regression sentinel; release-blocking
falsification evidence, not an independently powered parity claim

The evaluator-only repair sequence retained four valid empty-result and
identity boundaries without changing Hebog source-finding science, the
released-PyBDSF configuration, the 168-image population, metrics, thresholds,
or practical margins. The final immutable execution used candidate revision
`95cfc76ded56556dc3ad6894410962d34f0d5604`, source-tree SHA-256
`8da21e86afc5035da0704724a9d29104ea8b0e4d55fa4a98f0c5f3efca9a75a5`,
configuration SHA-256
`2c907949d2b9678b2d1f4cc00f8ba6c079e866842edea6873f981dc1264ed11d`,
identity-review SHA-256
`b67d877624bc87b2b8b3d09ad6c5f2e42fe573fac1bcdb7aa9c79810c6a5a329`,
and execution-decision SHA-256
`6516d6ef373f91a1969d9c456392ba70e2cca77cfa93a710a01872f920741cd9`.
The released-PyBDSF runtime image digest was
`sha256:5310afe78c8fc09ed99ddee1c6978e5e32181b69f1d22432a02ef6e3a6761198`.

Operationally, the campaign is complete. It produced 168 Serial Hebog and 168
released-PyBDSF results plus 12 caller-owned existing-Dask comparisons. All
paired products and ownership records were valid, all 12 Dask results equalled
their Serial references, the exact 42-cell population was present, and no
pooling was used. The atomic terminal decision is
`compact-held-out-sentinel-pybdsf-empty-repair.json`, SHA-256
`f542c7dbdc98bb3023efda4604d453b654c6da7bf61e5892fe528c5e601820aa`.
It records `status=fail` and `passed=false`; this is not another operational
failure.

The frozen scientific gates pass in only 7 of 42 cells. All 12 shell cells and
all 12 curved-filament cells fail, as do 6 of 12 mixed compact/extended cells
and 5 of 6 compact guards. Endpoint outcomes are:

| Endpoint | Failed cells | Interpretation |
| --- | ---: | --- |
| Completeness | 0 | Hebog median is 1.0 in every cell; this cannot compensate for other failures. |
| Duplicate fraction | 0 | Passes every cell. |
| Merge fraction | 0 | Passes every cell. |
| Integrated-flux median / p95 | 29 / 30 | Frequent error regression beyond the frozen 0.05 margin. |
| Split fraction | 28 | Hebog often splits truth associations that released PyBDSF does not. |
| Position median / p95 | 25 / 25 | Frequent positional regression beyond the frozen 0.05-beam margin. |
| Absolute mean x / y offset | 10 / 22 | The y-direction bias is the larger recurrent failure. |
| Reliability | 11 | Several fresh cells fall outside the frozen 0.02 margin. |
| Mask IoU / precision / recall | 1 / 2 / 3 | Support masks are mostly retained; catalogue science remains the dominant defect. |

This fresh sentinel falsifies closeout for the exact production candidate even
though the earlier cumulative evidence passed released/master PyBDSF and
Aegean comparisons under its scoped incumbent-retention exception. The
sentinel's four realizations per cell cannot establish a new parity claim, but
its predeclared one-look rule permits it to block one. Phase 5 therefore cannot
close on `95cfc76...`, and no readiness packet or held-out qualification may be
finalized for that candidate. The next permissible work is a prospective
scientific root-cause review of source splitting, flux measurement, and
position association. It must not tune, rescore, change a margin, or reuse the
viewed sentinel as qualification data.

## Compact sentinel root-cause review

**Review date:** 2026-09-07

**Review identity:**
`phase-5-compact-held-out-sentinel-root-cause-pre-review.json`, SHA-256
`f94d0455be9bbb4472b7ee6e6b0cd24fbf4ecc8be1d3e8a293d4467dbc02cad3`

The prospective review binds the immutable failed terminal and all 168
array-free pair summaries. It makes no source-finding change, does not rescore
the viewed population, and authorizes no execution. The dominant issue is a
confirmed like-semantics defect in the sentinel evaluator rather than a
demonstrated Hebog scientific regression:

- the Hebog arm supplied its Gaussian-component catalogue and
  measurement-component labels;
- the PyBDSF arm supplied Gaussian rows but native island labels; and
- the common compiler preferred grouped association flux, which PyBDSF rows
  carry for each `(Isl_id, Source_id)`, while the Hebog component rows retain
  their individual component measurements.

This difference is visible without reopening an image. Hebog has exactly one
catalogue row per native support in all 168 summaries. PyBDSF has more Gaussian
rows than native support labels in 150 summaries, with up to nine additional
rows sharing that topology domain. The split fraction moves adversely beyond
the frozen image-level margin in 110 summaries; all 110 have shared PyBDSF
Gaussian/island ownership and 109 have more Hebog component supports than
PyBDSF island supports. Source truth was therefore compared against unlike
component and island representations. The same mismatch affects source flux,
position, and reliability because a single component row is not an associated
astronomical source.

The review accounts for interpretation rather than manufacturing a new
outcome. Of the 186 failed cell-endpoints, 180 are representation-sensitive
and cannot establish either parity or inferiority until the prospective
evaluator uses like source semantics. They are not assumed to pass after that
correction. The six mask failures—one IoU, two precision, and three recall—are
computed from positive support and are independent of label identity, so they
remain valid candidate risks. In addition, 14 image-level adverse flux cases
and 10 adverse position cases occur without a Hebog component-count excess;
these preserve possible residual photometry and astrometry defects for
fixture-only diagnosis.

Adaptive-background activation is not the primary explanation. Below-trigger
extended controls fail 11 of 12 cells with 58 failed endpoints, compared with
10 of 12 and 58 at the boundary and 9 of 12 and 55 above the trigger. The
failure burden is already present when the adaptive path is inactive.

The proposed successor keeps semantic levels explicit:

1. Binding source science uses Hebog's associated-source catalogue and
   source-union ownership against PyBDSF rows grouped by native source identity
   with equivalent source-union ownership.
2. Hebog components and PyBDSF Gaussian components remain a separate
   report-only diagnostic using individual component flux. Split or merge
   parity is not reported there unless both finders expose like component-owner
   planes.
3. Binary support-mask comparisons remain direct and binding.
4. Array-free evidence retains source and component counts, owner identities,
   source-union membership, source and component flux/centres, and the named
   topology domain.

Twelve red fixture classes cover multiple components per source, grouped
PyBDSF Gaussians, Hebog source unions, connected three-peak compact topology,
grouped versus component flux, source versus component centroids, source-level
reliability, label-domain equality, relabel-invariant masks, residual
single-component flux/position, below-trigger controls, and Serial/Dask
invariance. A separate exact approval is required before implementing this
fixture-only evaluator alignment. A new seed-disjoint sentinel can be frozen
only after all fixtures pass and requires its own approval. The old terminal
remains `fail`, and Phase 5 remains open.

### Prospective source-level evaluator alignment

The scientific owner approved exact review `f94d0455...` on 2026-09-07, and
the fixture-only alignment is now implemented. It did not read or rescore the
168 viewed sentinel pairs, execute either finder, or modify `src/hebog`. The
candidate source-tree identity therefore remains unchanged.

The prospective evidence contract has two deliberately separate levels. Its
binding catalogue contains associated astronomical sources and is measured
against an explicit source-union owner plane. Its individual Gaussian or
Hebog-component catalogue is retained as a report-only diagnostic; topology
metrics are present only when the native plane is genuinely component-owned.
Positive-support precision, recall, and IoU remain direct binding metrics.
The implementation refuses to derive source-union ownership from nearest
component positions, because that would introduce an unreviewed scientific
partition rule. A future finder-specific adapter must instead provide the
exact union and prove that it covers the native positive support once.

The array-free schema retains source/component identities, exact membership,
native owner labels, source-union labels, pixel counts, membership digests,
individual and grouped fluxes, and both centres. It rejects inconsistent or
rehashed ownership records before invoking the byte-identical frozen parent
evaluator. Fixture coverage includes multi-Gaussian and multi-component
sources, multiple sources sharing one island, three-peak connected topology,
valid empty results, residual mask/flux/position risks, trigger strata, and
malformed products. Serial and caller-owned two-worker existing-Dask results
are identical under reversed completion order.

This is process evidence, not a replacement scientific result. Terminal
`f542c7db...` remains an immutable failure and has not been rescored. The next
step is a separate prospective review of finder-specific source-union
extraction followed, if accepted, by a newly frozen seed-disjoint sentinel
identity and exact one-use execution approval. Phase 5 remains open.

### Prospective finder-specific source-union adapter review

The separate non-executable adapter review is complete as exact review
`02b46eca...`. It inspected only the bound schemas and control flow; it did not
read the viewed sentinel summaries, execute either finder, or alter the
candidate. Both finder products remain independently compared with the same
analytic injected truth. PyBDSF is a comparator, never the truth source.

Hebog can provide source-union ownership without inference. Its association
record partitions every stable measurement component into one catalogue
source, and each component records the exact positive label it owns. The
adapter can therefore relabel those component pixels by their canonical source
membership and use the terminal source catalogue's flux and position. Any
catalogue, membership, component, or positive-label mismatch must fail closed.

Released PyBDSF 1.14.1 does not export a source-owner plane. It exports the
island mask and provides separate `srl` source and `gaul` Gaussian catalogues.
For a future, explicitly identified validation diagnostic, the review
recommends retaining native `srl` fluxes and centroids and grouping accepted
Gaussians by `(Isl_id, Source_id)`. A multi-source island is partitioned by
which source's summed accepted-Gaussian model is largest at each island pixel,
with canonical source identity breaking an exact tie. This derived topology is
named `pybdsf-source-model-dominance-v1-derived-topology`; it must never be
described as a native PyBDSF export. The Gaussian rows remain diagnostic-only.

PyBDSF may also retain an island after all fits are rejected. Such a fitless
island must remain in binding binary-mask precision, recall, and IoU, but it
cannot acquire a fabricated source owner. The aligned fixture contract must be
amended so whole fitless islands may remain explicitly unowned, with their
count, pixel count, and membership digest retained. A modelled island must
still be completely and uniquely partitioned. Dropping fitless support,
duplicating a whole island for multiple sources, or using nearest-centroid
ownership is forbidden.

The human approved exact review `02b46eca...` on 2026-09-07 for test-first,
fixture-only implementation. The completed validation-only adapters implement
the reviewed direct Hebog projection and explicitly named PyBDSF derived
topology. The aligned record is now schema version 3. It binds source metrics
to the source-union plane, keeps Gaussian/component measurements diagnostic,
and measures binary-mask precision, recall, and IoU from all positive native
support. Whole fitless PyBDSF islands therefore remain mask evidence without
acquiring fabricated sources; modelled islands must remain completely owned.
Compact modelled/unowned support counts, pixel counts, and exact membership
digests make this distinction independently checkable without retaining image
arrays.

The adapters live only under `scripts/validation`. The candidate package tree
remains byte-identical at SHA-256 `8da21e86...`; consequently this evaluator
work does not alter the candidate run by the notebook or any frozen product
identity.

The 63-case focused suite passes direct and multi-component Hebog ownership,
one- and multi-source PyBDSF islands, multiple Gaussians per source, canonical
ties and composite source identities, fitless-only and mixed islands,
duplicate or missing memberships, zero-owned sources, invalid owner planes,
rehash-resistant retained evidence, row/completion-order invariance, and a
caller-owned two-worker existing-Dask comparison. This work did not execute
either finder, inspect or rescore the viewed sentinel result, change a finder,
or freeze an execution identity. A new seed-disjoint sentinel identity still
requires a separate prospective freeze and exact one-use approval. Phase 5
remains open.

## Source-aligned compact held-out sentinel terminal

**Terminal date:** 2026-09-07

**Evidence role:** fresh seed-disjoint regression sentinel; predeclared
one-look release blocker, not an independently powered parity claim

**Terminal:**
`compact-held-out-source-union-sentinel-spawn-repair.json`, SHA-256
`ca03240db8452d84479139e848c0467815fdac9cea02168283fe69f52be8b63a`

The source-aligned successor completed from immutable commit `235f55a...`
after three preserved process-only failures exposed the native PyBDSF source
schema and macOS spawn-dispatch boundaries. The final process executed all 168
current-Hebog Serial cases, all 168 released-PyBDSF cases, and all 12
caller-owned existing-Dask comparisons. Candidate revision `95cfc76...`,
source tree `8da21e86...`, configuration `2c907949...`, fresh manifest
`1c2ce27a...`, identity `c498a90d...`, decision `be0c4c23...`, every bound
program, the pinned released-PyBDSF container, and the immutable checkout all
verify. All 12 Serial/existing-Dask science projections agree. The terminal is
therefore a completed scientific result, not an operational failure.

Both finders were independently matched to the same analytic injected truth.
The `candidate_cell_median` and `released_pybdsf_cell_median` values are each
truth-referenced measurements; PyBDSF is the comparator for the frozen
practical-margin test and is not treated as ground truth. Source science now
uses like associated-source/source-union semantics, components remain
report-only diagnostics, binary support masks remain binding, and absolute
objectives remain report-only as predeclared.

The result is `status=fail` and `passed=false`. Twenty-four of 42 cells pass;
18 fail with 59 failed cell-endpoints:

| Binding parity endpoint | Failed cells |
| --- | ---: |
| Reliability | 13 |
| Integrated-flux median / p95 error | 8 / 8 |
| Absolute mean x / y offset | 5 / 4 |
| Position median / p95 error | 4 / 4 |
| Mask recall / precision | 4 / 2 |
| Completeness | 2 |
| Duplicate / split fraction | 2 / 2 |
| Merge fraction | 1 |
| Mask IoU | 0 |

The strongest compact failures are scientifically material. In the connected
three-peak tile-corner guard, Hebog completeness is `0.3333` versus PyBDSF
`1.0`, merge fraction is `1.0` versus `0.3333`, median position error is
`1.3184` versus `0.0337`, and median integrated-flux error is `1.0681` versus
`0.0521`. In the unequal connected two-peak guard, completeness is `0.5`
versus `1.0`, median position error is `1.0197` versus `0.0345`, and median
integrated-flux error is `2.0598` versus `0.0327`. Their support-mask IoU
values remain comparable, so good binary support does not compensate for
incorrect associated-source separation and measurement.

The extended failures are less uniform but recurrent. Reliability exceeds the
frozen adverse margin in 13 cells, and the scale-12 beam-B shell strata also
show flux and position regressions. For example, the above-trigger cell has
reliability `0.0625` versus `0.1181`, median flux error `0.9473` versus
`0.8745`, and median position error `6.0840` versus `5.9977`, while mask IoU
still passes (`0.9344` versus `0.9417`). These values are poor against truth
for both finders in some extended regimes, but Hebog is additionally outside
the predeclared PyBDSF-relative margins.

This compact sentinel does not erase the powered cumulative campaign's earlier
parity result under its scoped retention exception. It does show that the
stronger source-level parity claim does not generalize to this fresh
population, and its predeclared falsification role therefore blocks Phase 5
closeout for candidate `95cfc76...`. The terminal must not be tuned, rescored,
or rerun as qualification evidence. Any further candidate work requires a
prospective scientific decision and new development data; no automatic retry
is appropriate for this scientific failure.

## 2026-09-08: repaired candidate cumulative replay underway

This is a launch record, not a scientific result. The owner-approved R0--R5
repairs are committed as candidate `db8936b...`, source `43fb41f2...`,
configuration `5eca0efc...`. Development, public-interface, Serial/Dask and
engineering checks pass, but the candidate remains `development-unqualified`.
Neither the earlier cumulative pass nor its incumbent-uncertainty acceptance
transfers to the repaired source and measurement semantics.

R6 asks whether the repaired candidate retains compact science and native
source-level Continuum performance against the authentic incumbent and both
PyBDSF references, with applicable Aegean checks. It keeps all 800 compact
and 1,600 Continuum regression images, 1,187 binding comparisons, five safety
checks and the original 50,000-resample confidence rules. Each finder is
measured independently against analytic injected truth; PyBDSF is not truth.
The 9,600 retained native reference runs passed an exhaustive identity and
artifact audit. No new PyBDSF execution is required for this cumulative stage.

Immutable tooling commit `1b1cbae...`, exact plan `af35c5b3...`, review
`9b6913b9...` and one-use decision `a9b0975b...` bind the execution. The
complete no-write preflight passed before launch; record `3b2f84c8...`
preserves that result. The approved two-worker command is managed session
`19330`, with hourly monitoring. It captures 2,400 current and 2,400
historical-incumbent bundles, runs 12 existing-Dask comparisons, retains
complete per-image diagnostics, and only then compiles the atomic decision.
The disclosed estimate is 10--24 hours, with 90 GiB disk admission including
reserve. This is separate from the fresh sentinel's sub-12-hour target.

No endpoint result is available yet. The terminal will be
`benchmark-results/phase-5/source-catalogue-repair-cumulative-decision.json`.
Every binding gate must pass before a new unopened seed-disjoint sentinel;
a completed scientific failure is terminal and may not be tuned or rescored.
R6 and Phase 5 therefore remain open.

## 2026-09-08: R6 stops at the retained-reference adapter

This is a process-failure record, not a scientific pass or failure. The
unchanged candidate `db8936b...` and immutable execution `1b1cbae...`
completed all 2,400 current/incumbent capture pairs and 12 existing-Dask
comparisons. Managed session `19330` exited with status 1; its failure record
is `1242e7ff...`, recorded at 09:47:24 UTC. The atomic R6 decision is absent.
No binding science, Dask pass verdict or runtime conclusion is inferred from
these completion counts.

The adapter omitted `Wave_id` from Gaussian identity and rejected distinct
native rows as duplicate membership. A metadata audit found 153 catalogues
with repeated island/source/Gaussian keys and one with a repeated full
wave-aware key but distinct native model measurements. The test-first ID
repair preserves all native rows and masks and retains rejection of genuinely
indistinguishable duplicates. No candidate science or frozen gate changed.

The subsequent no-scoring audit of all 3,200 Continuum reference projections
found 50 additional failures across 28 inputs (23 released-PyBDSF and 27
pinned-master). A real catalogue source need not win any pixel under exclusive
model dominance. The frozen adapter explicitly rejects that situation; the
[prospective review task](phase-5-r6-native-reference-adapter-review.md)
must resolve its representation before a retry. No native source may be
silently dropped, given artificial support or treated as truth.

The capture seal `e1bc9a91...`, Dask record `16de0eeb...` and all completed
evaluations remain intact. Eight hundred compact and eight Continuum inputs
have 4,032 verified array-free finder records; their ordered completion-marker
set digest is `f976ea97...`. All 16 reference views behind those completed
Continuum inputs are exactly unchanged by the ID repair, without rescoring.
An approved evaluator continuation can reuse verified durable work rather
than rerun the finders. R6 and Phase 5 remain open; no retry has started.

## 2026-09-08: R6 unavailable-support amendment (fixture-only)

The scientific owner approved retaining valid native catalogue sources with
no exclusive model-dominance pixels. The R6 v2 adapter now represents their
support as unavailable while preserving every native source/component row,
position, flux, pixel winner and fitless published island. Matching uses the
existing centroid clause when overlap is unavailable; unmatched catalogue
rows remain in reliability denominators. Diagnostics explicitly distinguish
catalogue measurements from derived support availability.

The historical v1 adapter, its review and the old successor compiler remain
byte-identical. The isolated amended compiler reuses the same matching and
metric kernels. Synthetic normal, boundary, corruption and two-worker
existing-Dask tests cover the new representation; no real finder, evaluation
retry, viewed-data rescoring or qualification was run. This is repair
evidence, not a new science/parity result.

The [R6 adapter review](phase-5-r6-native-reference-adapter-review.md) describes
the amended schemas and remaining continuation step. All retained R6 products
and 808 completed evaluations remain untouched. R6 and Phase 5 remain open
until a separately frozen evaluation-only continuation completes and its
binding scientific gates are interpreted.

## 2026-09-08: R6 reusable-evidence inventory (no scientific evaluation)

The immutable auditor at `3fc57fc...` completed exhaustive read-only
verification of all 2,400 current/incumbent capture pairs, 9,600 retained
reference runs and 12 saved Serial/existing-Dask comparisons. It verified
808 completed inputs (800 compact and eight Continuum), comprising 4,032
finder records, for byte-for-byte reuse. Exactly 1,592 inputs remain pending.
Both empty directories left by the failed evaluation are preserved.

The atomic inventory has SHA-256
`e0d1571d092b47c6e34bec5c3cd23a11d6cb0acc14124befd057fc0d9dfa59a5`;
its non-executable identity review is `4d4fb7c5...`. It retains original
candidate `db8936b...`, separately from later notebook repairs. No finder,
Dask comparison or truth-score evaluation was rerun. The original scientific
terminal is still absent: this is evidence-integrity confirmation, not a
parity result or authorization to launch.

The next step is a separate evaluation-only continuation, with synthetic
resume and late-failure tests, a frozen exact execution decision and repeated
exhaustive launch admission. The monitor stays paused until that continuation
is launched. R6 and Phase 5 remain open.

## 2026-09-08: R6 evaluation-only continuation freeze

The continuation tooling is committed at `b64228d...` and isolated in a
clean immutable checkout. It reuses all 808 completed inputs byte-for-byte
and evaluates only the 1,592 missing inputs, using two workers and no finder
or Dask reruns. The original scientific candidate `db8936b...`, analytic
truth, population, thresholds, margins and statistical rules remain bound.
The amended evaluator is a separate identity, not a new scientific candidate.

Plan file SHA-256 is
`c99f9f86857139bbb992ff873a337cdfb09e04b376a1600bf3a07956db88721f`;
expected execution SHA-256 is
`1b73bd62d384154ea4536988bae107b6adcfb283efd81046637e1320c844ee7a`.
The non-executable review `6ebd6664...` and separate one-use decision
`3bc1e1e1...` bind the retained inventory, approved support amendment,
immutable code, original environment, new scratch and original terminal path.
The decision records the owner's standing R0--R6 repair authority.

Synthetic dispatch, two-worker spawn, preservation and failure tests pass;
every new executable line and branch is covered. Portable tests verify the
freeze without local campaign outputs. Exhaustive no-write admission must
pass before launch. No new scientific score or verdict is reported by this
freeze; R6 and Phase 5 remain open.

The exhaustive standalone preflight subsequently exited zero, confirming
all retained artifacts and reusable records without running a finder or
computing scientific scores. Its retained result has SHA-256
`76a4fdcb2d5e53084a0b8d1c9c568ed382d14fd294e701b1cc13cda7ca107980`.
Frozen records are committed at `522db3b...`. The single continuation is now
launched outside the sandbox in managed session `70321`; it repeats admission
before dispatch. Hourly monitoring is active. There is no new terminal or
scientific verdict yet, and no finder or Dask rerun is authorized by this
continuation.

## 2026-09-09: R6 cumulative terminal — scientific failure

**Evidence role:** completed cumulative regression, not fresh held-out
qualification. **Question:** do the R0--R5 source-catalogue repairs preserve
compact and Continuum quality against analytic truth, both PyBDSF references,
applicable Aegean comparisons and the selected Hebog incumbent?

**Verdict: no.** Managed session `70321` exited **0** and published
`benchmark-results/phase-5/source-catalogue-repair-cumulative-decision.json`,
SHA-256
`7146f2e857c9473117c16d29f5bd8d55a2790c66d1c1643cd79b96aa8cc51d72`.
The scientific status is `fail`; both `cumulative_science_regression_ready`
and `all_required_endpoints_pass` are **false**. A successful process and
passing software tests do not turn these failed scientific gates into parity.

### Population, semantics and provenance

The unchanged regression population comprises 800 compact/blend
512-by-512 images and 1,600 Continuum 1,024-by-1,024 images. Compact strata
include SNR 10, 15, 25 and 50, unresolved/marginal/clear-resolved shapes and
edges; Continuum retains its extended morphology, invalid-pixel, noise,
image-edge and tile-boundary/corner populations. Each finder is measured independently against analytic/injected
truth; PyBDSF is not truth. Compact matching and the Continuum source-level
centroid/overlap rules retain their frozen semantics, denominators and
thresholds. Native source positions, fluxes and membership are used; absent
exclusive derived support is represented under the separately approved
[R6 adapter amendment](phase-5-r6-native-reference-adapter-review.md).
It does not invent pixels, remove native catalogue rows or alter matching
thresholds. The 808 previously completed inputs are reused byte-for-byte.

Original scientific candidate `db8936b512370a1491f36845592fe3e8a24107ad`
has source SHA-256
`43fb41f20069a31627f0dbec09bdf1484bd2a04d633fe6563b94b09a554dd2cf`
and configuration SHA-256
`5eca0efc1995f206900506c87f2ca3cba6aa4a2f1a5155bc3e58863bf3cb75c4`.
The incumbent remains `85d5807...`, captured through immutable producer
`c1614c2...`; PyBDSF 1.14.1 (`1b6e0a04...`), pinned master
1.14.2.dev40 (`c70103be...`) and Aegean 2.3.5 (`bb04f50a...`) records are
retained with their original container/configuration identities, not rerun.
The original 2,400 capture pairs and 12 saved
Serial/existing-Dask comparisons remain sealed as `e1bc9a91...` and
`16de0eeb...`. Continuation implementation `b64228d...`, plan `c99f9f86...`,
review `6ebd6664...`, one-use decision `3bc1e1e1...` and expected execution
`1b73bd62...` bind the amended evaluator separately from the scientific
candidate and later notebook repairs. Python is 3.14.2 with the frozen
dependency inventory and one numerical thread per worker.

The continuation evaluated **1,592 missing inputs**, reused **808** completed
inputs and published combined evaluation seal SHA-256
`d14205d922e3a46b1cd93be3de84d745910b68f89a12f3ed00f5cb5f9d22ae5b`.
There are **10,400** finder-evaluation records in total. It performed **zero**
candidate, incumbent, PyBDSF or Dask reruns. The original process-failure
record, two empty failed directories and all original products are preserved.

The post-terminal read-only audit verified all 2,400 input bundles, 9,600
retained reference runs, 2,400 native capture pairs, 12 Dask comparisons and
10,400 evaluation records, including exact reuse and the combined seal.
It also checked the candidate/incumbent source and configuration, original
and continuation programs/reviews/decisions, immutable checkouts, approved
amendment, closed reference/baseline/sentinel and terminal identities. No
scientific score was recomputed. Its compact result is retained as
`benchmark-results/phase-5/r6-terminal-provenance-verification.json`, SHA-256
`5dde3be99d28a80b9bc1e1a23d57d4cac5db34d82e37b801e6c8e0a8030cdedf`.

### Compact science first

Values below are the stored overall endpoint summaries against truth, not
newly pooled or rescored estimates. Smaller position and axis errors are
better; higher recall is better. The bound is the frozen one-sided 95% upper
confidence limit on positive regression, which must be inside its practical
margin. No other metric can compensate for a failed comparison.

| Compact endpoint | Hebog | Released PyBDSF | Pinned master | Binding interpretation |
| --- | ---: | ---: | ---: | --- |
| Median position error (beam FWHM) | 0.025587 | 0.022518 | 0.022505 | Both fail: upper regression bounds 0.003222 / 0.003234 exceed margin 0.002. |
| Position-error p95 (beam FWHM) | 0.093800 | 0.077526 | 0.077073 | Both fail: upper bounds 0.017136 / 0.017629 exceed margin 0.005. |
| Fitted-axis-error p95 (fractional error) | 0.214900 | 0.181916 | 0.183842 | Both fail: upper bounds 0.035985 / 0.034131 exceed margin 0.01. |
| Clear-resolved classification recall | 87.4688% | 99.9844% | 97.4688% | Both fail: recall deficits 12.5156 / 10.0000 percentage points exceed the 1-point margin. |

Resolved deconvolved-shape availability has the same overall values and also
fails both PyBDSF comparisons. Compact Aegean failures additionally include
overall catastrophic-outlier fraction, fitted position angle and flux-error
tails. Incumbent failures span position, fitted shape, classification,
availability, flux and catastrophic outliers. These are observed failures,
not merely confidence intervals that need more images.

### Continuum second

Overall Continuum point estimates retain important gains against PyBDSF:
Hebog completeness is 100%, reliability is 78.4583% versus 56.7025% released
and 52.6068% master, and mask IoU is 0.832692 versus 0.779223 and 0.772351.
Those overall comparisons pass. They do not hide failures in specific strata:

| Continuum endpoint / stratum | Hebog | Released PyBDSF | Pinned master | Binding interpretation |
| --- | ---: | ---: | ---: | --- |
| Integrated-flux-error p95 / image edge (fractional error) | 0.868129 | 0.343303 | 0.479716 | Both fail: upper regression bounds 0.543745 / 0.408295 exceed margin 0.05. |
| Integrated-flux-error p95 / diffuse (fractional error) | 0.743839 | 0.325711 | 0.484344 | Both fail: upper bounds 0.440482 / 0.283004 exceed margin 0.05. |
| Position-error p95 / image edge (beam FWHM) | 1.369583 | 0.724245 | 0.231700 | Both fail: upper bounds 0.693306 / 1.185887 exceed margin 0.05. |
| Position-error p95 / diffuse (beam FWHM) | 1.120588 | 0.625220 | 0.207053 | Both fail: upper bounds 0.579506 / 0.991771 exceed margin 0.05. |

Each PyBDSF reference has seven failed Continuum comparisons: the four
patterns above plus position p95 for invalid pixels, mixed compact/extended
emission and the one-beam scale. These strata can overlap and are not seven
independent root causes. Incumbent retention also fails overall reliability
(0.784583 versus 0.852121), flux-error p95 (0.754667 versus 0.269410),
position-error p95 (2.865073 versus 0.976244 beam), duplicate fraction and
split fraction (both 0.171250 versus 0.128304). A good mask alone does not
establish a scientifically accurate source catalogue.

### Complete binding decision and next gate

| Comparator | Compact pass / fail / underpowered | Continuum pass / fail / underpowered | Total |
| --- | --- | --- | --- |
| Aegean | 87 / 53 / 3 | Not applicable | 143 |
| Incumbent Hebog | 119 / 100 / 6 | 79 / 59 / 5 | 368 |
| Released PyBDSF | 193 / 32 / 0 | 106 / 7 / 0 | 338 |
| Pinned PyBDSF master | 195 / 30 / 0 | 106 / 7 / 0 | 338 |
| All binding comparisons | 594 / 215 / 9 | 291 / 73 / 5 | 1,187 |

In total **885 pass, 288 fail and 14 are underpowered**. All five binding
safety checks pass: finite measurements, product validity, schema/provenance,
Serial/existing-Dask determinism and write-once publication. Fifteen
longer-term Continuum position objectives remain report-only; they neither
cause nor excuse this failure. The historical incumbent-uncertainty
acceptance is explicitly **not transferred**. Legacy compact subrecord names
containing `qualification` do not change this terminal's regression role or
make it fresh held-out evidence.

Evaluation after admission ran from 2026-09-08 20:43:52 UTC to 2026-09-09
00:34:36 UTC (about **3 h 51 min**). This includes missing-input evaluation
and aggregation, not finder capture; it is not a Hebog speedup or runtime
qualification. Scientific eligibility fails before runtime is considered.

**Next:** preserve this terminal without retry, tuning, rescoring or changing
any margin, threshold, comparator or confidence rule. R6 and Phase 5 remain
open; do not launch the fresh sentinel, cut over or release. A separate
prospective root-cause review should distinguish genuine estimator,
association and edge-support errors from any demonstrable representation
defect using the frozen records and bounded analytic fixtures. The terminal
alone does not prove an implementation-level cause. Any proposed repair and
new candidate/evaluation identity must be reviewed prospectively; passing
fixtures or later notebook repairs cannot inherit this candidate's evidence.

## 2026-09-09: R6 prospective root-cause review completed

The [separate scientific review](phase-5-r6-root-cause-review.md) inspected
all 10,400 sealed finder-record hashes and attributed failures using saved
native rows, flags and matches. Independent analytic witnesses ran against
the original immutable R6 code, not later notebook repairs. No closed input
was rerun, matched again or rescored; terminal `7146f2e8...` remains failed.

Compact review confirmed that joint fitting bypasses the configured
beam/free selection and found GLS-fallback flags on all 38,376 matched
current compact rows. Of 803 lost clear-resolved classifications, 800 belong
to one SNR-25 corner geometry and reach the major-axis significance censor.
Their covariance/calibration cause is not yet established; changing the
classification threshold is not an approved remedy.

Continuum review reproduced a source-domain substitution defect without
noise: a clipped Gaussian's total flux and model centre replace the
observable source measurement. The full public fixture overstates visible
flux by 72.6071%. Saved edge Gaussian-substitution rows show median signed
flux excess 58.6108%, versus -1.1266% for aperture rows. Separately, shell
and curved-filament splits occur in 701 and 689 of 1,600 cases respectively;
adequate Gaussian decomposition does not establish independent sources.
Residual aperture-position tails require further independent attribution.

These diagnostic subdivisions are not new gates or alternative scores.
The plan now orders prospective compact-policy/noise work, observable-domain
source measurements, association/position attribution, short joint fixture
validation and only then new exact cumulative evidence. Review is complete;
repairs, fresh qualification, Phase 5 closeout and release are not.

## 2026-09-09: Prospective R6 estimator repairs implemented

The approved [estimator/source-domain repairs](phase-5-r6-estimator-repairs.md)
restore coherent joint beam/free selection and owned-region GLS; retain
observable, signed source apertures separately from native Gaussian component
measurements; and add bounded extended-association and centroid attribution.
Independent regression fixtures also exposed circular-coordinate covariance
and periodic-angle initialization defects, now covered by focused tests.

The 108-case synthetic development matrix passes across analytic, noisy and
public-background conditions, including prior geometry guards. Four additional
open/asymmetric-arc cases, compact-neighbour counterexamples, 192 masked-corner
noise realizations and public Serial/existing-Dask conformance pass. This is
development evidence, **not a replacement campaign or a parity verdict**.
No closed scientific case was rerun, rematched or rescored.

The original terminal remains `7146f2e8...`: 885 pass, 288 fail, 14
underpowered, all five safety checks pass, and both readiness flags false.
The new public v10 composition and diagnostics schema 7 require separately
bound cumulative evidence before fresh qualification. Engineering validation
and the non-executable freeze are recorded in the plan and `LOG.md`; neither
grants execution authority. R6 and Phase 5 remain open.

## 2026-09-09: Replacement R6 reuse reviewed; admission remains pending

The [replacement admission review](phase-5-r6-replacement-admission-review.md)
confirms that 8,000 comparator evaluation records can be reused byte-for-byte:
2,400 incumbent, 4,800 dual-PyBDSF and 800 Aegean. Their finders and
truth-relative metric semantics are unchanged. The repaired candidate needs
2,400 new Serial captures/evaluations, 12 existing-Dask comparisons and new
paired statistics. No historical current-Hebog verdict or uncertainty waiver
transfers. All 2,400 inputs and known-risk populations remain in scope.

An exhaustive read-only recheck verified all original input/reference products,
capture pairs and 10,400 completed records; it ran no finder or evaluator.
Fixture-only reuse-aware orchestration and cost/size validation are next.
Provisional admission needs 68 GiB free versus 59.08 GiB observed; the tentative
9--14-hour total is not a guarantee or confirmation of the final campaign's
sub-12-hour target. No new run, output namespace, execution decision or monitor
was created. The existing failed terminal remains unchanged; Phase 5 is open.

## 2026-09-10 public-catalogue repair fixture result

This is **independent development-fixture evidence, not a campaign verdict**.
The prospective [catalogue repair contract](phase-5-public-catalogue-repair-contract.md)
addresses unsupported source associations, oversized computational fit groups,
unit-dependent numerical diagnostics and source-contaminated or spatially
oversmoothed background/RMS estimates. All viewed notebook and closed R6
products remain unchanged. Neither PyBDSF nor Aegean is treated as truth.

The combined final integration ladder passes 203 tests: all 108 existing
geometry cells, 24 bright-halo/noise controls, 38 noise-only/gradient/corner
controls, six background Serial/existing-Dask cases and 27 public-API cases.
The final compact-policy isolation regression and existing compact-profile
test also pass. Compact neighbours remain separate without positive merge
evidence; genuine extended-source guards remain binding. Source-level merge
provenance and unavailable/deferred states are explicit in diagnostics schema
8. Continuum composition v11 remains `development-unqualified`.

No pooled success overrides a failed geometry or unavailable processing.
These fixtures do not show that every viewed feature is real or establish
new catalogue completeness, reliability or PyBDSF parity. The next replay
still requires reuse-aware runner tests, exact retained-record verification
and resource admission. Candidate `ee83035...`, source `f708bd54...` and
composition `da4018cc...` are now frozen by non-executable review
`dc811fb8...`; the unchanged configuration is `5eca0efc...`. The review grants
no execution authority. All 29 committed-history/selector/synthetic notebook
checks pass, and the actual read-only notebook preflight admits the selected
identity for 13 configured cases without refreshing them. About
53 GiB is currently free versus the provisional 68 GiB budget; the earlier
9--14-hour estimate must be remeasured for this RMS policy. No replay,
reference execution, notebook refresh, rescoring or release was started.

## 2026-09-10 — Replacement replay prepared, execution withheld

The [v11 preparation record](phase-5-v11-replay-preparation.md) stages a
current-only 2,400-input replay with 12 new existing-Dask comparisons and
8,000 immutable comparator records. It introduces no alternate scoring rules.
The historical no-write audit again verified all 2,400 inputs, 9,600 reference
runs, captured pairs and 10,400 completed records; the failed R6 verdict is
unchanged. Forty new orchestration tests and two noisy synthetic end-to-end
tests pass. These are development/tooling checks, not new campaign parity.

A new noiseless exact-public fixture fails during source-protected adaptive
background estimation. The reproducer is retained as a strict xfail, **not a
passed admission gate**. Correctness repair/refreezing, a controlled cost
probe, sufficient disk space and the exact execution owner/preflight remain
required. The user requested no launch; none was started. The notebook
refresh remains isolated from these tooling/documentation edits. Cleanup
recommendations preserve its active staging and all replay-critical evidence;
no evidence or staging directory was removed.

## 2026-09-10 — Synthetic noiseless admission failure repaired

The [numerical repair](phase-5-noiseless-filter-repair.md) traces the exposed
background failure to remote FFT roundoff divided by nearly zero local noise.
It uses the same finite-support filters with spatial arithmetic where FFT
precision is insufficient, and range-safe variance propagation. The exact
public reproducer now passes without an xfail. Thresholds, noise-estimator policy,
positive-response admission and closed evaluator results are unchanged.

Composition v12 supersedes v11 for new work. Non-executable review
`2ab9d433...` binds candidate `ed5136a...`, source `838e2846...` and
composition `ba1039f5...`, with unchanged configuration `5eca0efc...`.
Thirty committed-history, selector/drift and synthetic notebook tests pass;
the actual no-write notebook preflight passes 13 configured cases. The review
grants no execution authority and no earlier scientific verdict transfers.
The saved v11 preparation is not current execution authority. The user's
no-launch instruction remains in force. No campaign was run or rescored,
and the failed R6 result remains failed.

## 2026-09-11 — Zero-noise development edge case repaired and frozen

This is **fixture evidence, not a replay or scientific parity verdict**.
The remaining cost fixture exposed an obsolete bright-region anchor after
source protection left exactly zero coarse noise. The
[repair](phase-5-zero-noise-adaptive-repair.md) preserves explicit unavailable
RMS and skips only unusable protected adaptive work; it does not invent noise,
weaken the support guard or reinterpret missing measurements as non-detections.

The exact regression passes; noisy catalogue, RMS and mask products match the
archived v12 control exactly. Caller-owned two-worker Dask matches Serial.
Validation includes 219 focused tests, 3,778 portable coverage tests plus a
25-test guard supplement, and 27 equivalence tests. Branch-aware coverage is
95.26468995%, above the previous freeze. These tests do not replace cumulative
or held-out scientific qualification.

Non-executable review `e93372b5...` binds v13 candidate `eacfa64...`, source
`d5107cd3...`, composition `0b6844bf...` and unchanged configuration
`5eca0efc...`. All 31 history/identity/selector/synthetic notebook checks pass.
The earlier 13-case notebook refresh remains preserved and was not rerun.
The standing replay authorization remains subject to new resource, exact-owner
and exhaustive no-write admission. No replay was launched; no closed R6
verdict transfers or was rescored. Phase 5 remains open.

## 2026-09-11 — V13 cost ladder and non-executable preparation complete

The [v13 preparation](phase-5-v13-replay-preparation.md) preserves the full
2,400-input population, 12 new Dask checks and 8,000 byte-identical comparator
records. Metadata `a1c60497...` grants no execution authority. No replay has
started, and no closed scientific result was rescored.

Eight independent development fixtures complete one warm-up plus five measured
repetitions: 48 captures and 30 full-metadata current-Hebog evaluations,
including every declared Continuum endpoint specification. The repaired
zero-noise case completes all captures. The initial cost probe's missing
truth annotations were a fixture-setup bug, repaired test-first without
changing the frozen candidate or evaluator. Both attempts remain preserved.
The completed cost terminal is `f2d4116c...`; summary `bf6bb1be...` records
timing dispersion, artifact identities and limitations. These are execution
and cost observations, not new parity evidence.

The unchanged replay has a 17.50–20.02-hour planning estimate, not a deadline
guarantee. The revised 69.58-GiB host reserve exceeded available space by
about 9.85 GiB at the cost-summary check. Disk headroom and the tested exact
execution owner/freeze/no-write preflight remain launch gates. Forty focused
orchestration tests pass; no reference finder, qualification or release ran.
The exhaustive historical audit `5b95726b...` verifies all 2,400 inputs,
9,600 references, 4,800 native captures, 12 old Dask comparisons and 10,400
records without rerunning an evaluator. The old 885-pass/288-fail/14-underpowered
verdict is preserved, not transferred to v13.

## 2026-09-11 — V13 exact launch owner fixture-validated

The [replacement launcher](phase-5-v13-replay-preparation.md#exact-launch-owner)
now binds the current preparation, candidate/runtime, sufficient measured
reserve and one-use authority before capture. It verifies mixed JSON/text
provenance as bytes, isolates new namespaces and rechecks code, resources and
controlling identities after the long no-write audit. Missing or changed
admission fails before finder execution. Process errors are not converted to
scientific success or automatic retries.

All 114 focused tests pass with 100% line and branch coverage of the two new
modules. The actual preparation's census and scientific metadata also verify
read-only. Candidate source remains `d5107cd3...`; the old failed R6 terminal
and completed notebook are unchanged. This is tooling/development evidence,
not new parity evidence. Adequate host headroom, the new committed execution
closure/identity and final exhaustive immutable preflight remain required.
No replay, reference finder, qualification or release has started.

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
