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
`64db011706ea62e3f90472a0b0e46bc67b363cdf615256868d87788acf44654e`,
and implementation decision `029f9a2068c7...` freeze only the original-pixel
publication statistic. No threshold, margin, measurement, association,
population, comparator, or decision rule changes. The replacement candidate
configuration is `8f515d7c...`; it must complete the same write-once smoke
before any separate topology correction or full replay.

## Prospective evaluation contract after terminal-cycle repair

**Frozen date:** 2026-08-31

**Evidence role:** non-executable prospective governance. This record does
not change, rescore, or replace any campaign result above.

The next candidate must pass every applicable comparison to released PyBDSF,
pinned PyBDSF `master`, and Aegean, while also retaining the scientific quality
of one complete closed Hebog incumbent. It may not compensate for one failed
check with a gain elsewhere. Ambitious absolute numeric targets remain visible
as longer-term objectives; finite products, valid schemas and provenance,
determinism, and write-once publication remain binding safety requirements.

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
passed. The first smoke then failed as documented above, so the full replay
remains blocked. Qualification, tuning, rescoring, cutover, and release remain
outside this authority.

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
