# Phase 4 paired non-inferiority protocol

**Status:** reviewed on 2026-08-03 by Gemma Danks, Data Processing Software
Engineer. The final unseen population is frozen and remains ungenerated and
unopened until every execution identity is recorded.

This protocol answers a deliberately narrower question than “does Hebog equal
PyBDSF byte for byte?” It asks whether Hebog passes the existing truth-based
science gates, retains its demonstrated strengths, and is no worse than the
released PyBDSF used by Rapthor by any practically meaningful amount. Pinned
PyBDSF `master` remains a secondary robustness and compatibility anchor.

The machine-readable source is
`config/contracts/phase-4-paired-noninferiority.json`.
It is the approved analysis contract. It does not contain the final campaign
seeds or truth; those are frozen separately in
`config/datasets/phase-4-final-qualification.json`.
The unchanged Phase 4 measurement-semantics contract and the five-sigma
scientific-gate contract are both `reviewed-provisional` under the same named
decision.

## Why the comparison is paired

Hebog and PyBDSF will process exactly the same generated floating-point image
for each noise seed. The scientific result can then be expressed as a
within-image difference, which removes much of the variation caused by a
particular noise realization, WCS, source placement, or background field.

Sources in one image are not independent: they share correlated noise and a
background/RMS estimate. The interval therefore resamples complete
noise-seed images and recomputes the metric, keeping every source, truth group,
and stratum from that image together. Treating thousands of source rows as
independent would make the uncertainty misleadingly small.

For every endpoint the sign is normalized so a positive number means Hebog is
worse:

- for a higher-is-better rate, regression is `PyBDSF - Hebog`;
- for a lower-is-better error or adverse rate, it is `Hebog - PyBDSF`; and
- for a metric with an ideal value, it is Hebog's absolute distance from the
  ideal minus PyBDSF's absolute distance from the same ideal.

The final analysis uses a paired, one-sided, 95% SciPy BCa cluster-bootstrap
interval with 50,000 fixed-seed resamples. A degenerate or undefined interval
is indeterminate and fails closed; it is not replaced after seeing the result
by a more favourable method.

## Passing rule

Every co-primary endpoint's one-sided upper confidence limit must be within
its predeclared practical regression margin. The signed point estimate is
reported for transparency, but its sign is not a separate gate: under exact
equality a sign gate fails half of repeated experiments and would reject
scientifically negligible random differences even when the interval excludes
the non-inferiority margin.
Every co-primary endpoint's one-sided upper confidence limit must be within
its predeclared practical regression margin. The signed point estimate is
reported for transparency, but its sign is not a separate gate: under exact
equality a sign gate fails half of repeated experiments and would reject
scientifically negligible random differences even when the interval excludes
the non-inferiority margin.

All existing absolute science gates and the independently frozen regression
envelopes protecting Hebog's stronger results must also pass. Metrics cannot
compensate for one another. This is an intersection-union decision: because a
pass requires every individual null hypothesis to be rejected at one-sided
alpha 0.05, no additional multiplicity correction is applied.

The released PyBDSF used by Rapthor is the primary reference. If it or Hebog
fails a realization, primary qualification fails and that seed stays in the
denominator. Pinned `master` failures are recorded and the secondary report
continues, because the already observed atrous exception is itself a
robustness result.

## Proposed margins

The draft uses absolute percentage-point margins for rates and native metric
units for errors. The most decision-sensitive margins are:

| Endpoint | Practical regression margin |
| --- | ---: |
| Point-source specificity | 0.5 percentage points |
| Catastrophic-outlier fraction | 0.25 percentage points |
| Clear-resolved recall | 1 percentage point |
| Unresolved-group completeness | 1 percentage point |
| Median unresolved-group position | 0.01 beam |
| 95th-percentile unresolved-group position | 0.02 beam |
| Median unresolved-group total-flux error | 0.01 fractional |
| 95th-percentile unresolved-group total-flux error | 0.02 fractional |
| Normalized-residual absolute bias departure | 0.025 |
| One-sigma coverage absolute departure | 0.02 |
| Normalized-residual dispersion absolute departure | 0.04 |

Completeness, reliability, association-pair precision/recall, fitted-shape,
deconvolution-classification, association-identity, and uncertainty
availability each use a 0.5-percentage-point margin. Clear-resolved
deconvolved-shape availability uses 1 percentage point because there is one
such source per realization. The intersection-union rule still forbids a
such source per realization. The intersection-union rule still forbids a
trade of one metric for another; these margins bound sampling uncertainty
rather than authorize a scientifically meaningful regression.
rather than authorize a scientifically meaningful regression.

## Power and its limitation

The proposed final design has 600 independent noise realizations, three times
the population used by each viewed campaign. A normal design approximation
uses paired discordance for binary outcomes, a cluster design effect for
multiple sources in one image, and the standard deviation of realization-level
paired statistics for continuous outcomes. Under the provisional assumptions,
the weakest interval-exclusion power is 92.2%; point specificity is 94.5% and
the next weakest endpoint, unresolved-group completeness, is 96.6%.

Run the executable calculation with:

```console
uv run python scripts/validation/calculate_phase4_paired_power.py \
  config/contracts/phase-4-paired-noninferiority.json
```

The 90% target applies to exclusion of the non-inferiority margin. The power
calculation also reports point-direction probabilities so the rejected stricter
rule remains auditable, but the reviewed decision is based on the interval,
the absolute gates, and the independently frozen envelopes protecting Hebog's
stronger results.
The 90% target applies to exclusion of the non-inferiority margin. The power
calculation also reports point-direction probabilities so the rejected stricter
rule remains auditable, but the reviewed decision is based on the interval,
the absolute gates, and the independently frozen envelopes protecting Hebog's
stronger results.

The initial discordance, within-image correlation, and paired-standard-
deviation values were provisional planning inputs. The maintained audit now
checks their combined implication directly: it resamples whole images,
recomputes every aggregate ratio, quantile, and uncertainty endpoint, and
converts the bootstrap standard error back to a per-realization paired
standard deviation. This is more robust than inventing a one-to-one identity
between false candidates for catalogue reliability and it covers nonlinear
endpoints for which discordance and intracluster correlation are not separately
identifiable.

The first 50,000-resample audit showed that 11 bounds were conservative and
nine were too small. The revised draft rounds every failed dispersion bound
above the observed value and assumes no more than half of the independently
observed favourable Hebog effect. It does not change any practical margin or
scientific gate. The second audit verifies all 20 bounds; its SHA-256 is
`af7c6cdfdf55629b77a6960292f523f73f583ec8e09bb407233cda26845ea9b1`.
The reviewed protocol's canonical SHA-256 is
`1702076858c024d9080601625ae8a7819c9b170f26086e688ca4d3b45d5b022a`.
`af7c6cdfdf55629b77a6960292f523f73f583ec8e09bb407233cda26845ea9b1`.
The reviewed protocol's canonical SHA-256 is
`1702076858c024d9080601625ae8a7819c9b170f26086e688ca4d3b45d5b022a`.
The weakest interval-exclusion power at 600 images remains 92.2%, for median
unresolved-group position. Named review accepted these measured,
conservative planning inputs. Sample size must not change after the final
population is opened.
unresolved-group position. Named review accepted these measured,
conservative planning inputs. Sample size must not change after the final
population is opened.

The governed assumption-audit population is
`config/datasets/phase-4-paired-regression.json`, dataset
`phase4-paired-power-regression-512`, recipe SHA-256
`2669ad5c7e0883e50b6c82a8d1c66d92a8890df9d8fc7b64a645d6bdf52dedca`.
It contains 200 independently seeded, viewable regression realizations with
the proposed endpoint structure. It may be inspected, used to revise planning
assumptions, and used for corrective TDD; it can never qualify Hebog or be
relabelled as the final unseen population.

The first corrected-geometry execution produced exploratory candidate,
released-reference, and compiled evidence with SHA-256 values
`f58fec61ab4d29670acf6e49117e30045a90fdc0bce2c5de77f5c96e021544b9`,
`adeea227878ecb0b412a196a1adf09fdd212fca15fa9b3f187059e1c33f470b0`,
and `91056642e990f164292af598ac4d9b2bf6f334edfef84aaee44c5cf4301efaf2`.
Released PyBDSF completed all 200 realizations; Hebog completed 196. On their
196 joint successes, both recovered every declared truth group. Hebog had
96.75% point-source specificity against PyBDSF's 100%, but a lower governed
catastrophic fraction (0.733% against 1.562%), perfect clear-resolved recall
against 57.14%, and lower mean unresolved-blend position and total-flux errors
(0.056 beam and 5.42% against 0.082 beam and 14.17%). Catalogue reliability
was 99.69% against 99.76%.

The four Hebog failures were the same structural deblending defect: a
prominent five-pixel child was passed to a seven-parameter fit. The
independent cases are now permanent TDD regressions, and the deblender merges
such a basin without discarding parent pixels. Because production behaviour
has changed, the exploratory estimates do not verify the planning assumptions;
the complete paired run must be refreshed after the point-classification
correction as well.

The source-level margin audit then measured the standardized ATLAS extension
statistic for all 1,600 point and 200 clear regression cases. Point truth ended
at 3.38 sigma and clear truth began at 17.92 sigma. Phase 4 now uses a
at 3.38 sigma and clear truth began at 17.92 sigma. Phase 4 now uses a
five-sigma high-confidence catalogue decision, replacing the earlier
two-sigma boundary while retaining the same statistic. The analytic and
independent worst-margin tests pass, and named review approved this policy.
The pre-change campaign cannot establish its paired endpoint or variance, so
the refreshed complete run below remains the governing regression evidence.
independent worst-margin tests pass, and named review approved this policy.
The pre-change campaign cannot establish its paired endpoint or variance, so
the refreshed complete run below remains the governing regression evidence.

The refreshed post-correction execution is now complete. Both Hebog and
released PyBDSF completed all 200 images and recovered every truth group.
Hebog reached 100% point specificity and 100% clear-resolved recall; released
PyBDSF reached 100% and 57.5%, respectively. Hebog retained a lower governed
catastrophic fraction (0.531% against 1.547%) and lower mean unresolved-blend
position and total-flux errors (0.056 beam and 5.36% against 0.089 beam and
14.98%). The candidate, unchanged released-reference, and compiled evidence
have SHA-256 values
`32aacb78733d28cac086ae10596a1d2d1f5e7671d0cc6844c33a0ac87297fa0a`,
`adeea227878ecb0b412a196a1adf09fdd212fca15fa9b3f187059e1c33f470b0`,
and `bff79e0dafd096870460bfc1f6663a84d4f6cb813ea6ab7610b2bd8bee287a96`.

Catalogue reliability is the only raw co-primary point estimate in the
detection/association family in the opposite direction: 99.6828% for Hebog
and 99.6979% for PyBDSF, a net
difference of one unmatched candidate across 6,600 truth groups. Its
positive-as-worse paired estimate is 0.0151 percentage points and its
one-sided 95% BCa upper limit is 0.1808 percentage points, below the proposed
0.5-point practical margin. Every Hebog unmatched candidate is an unresolved
near-threshold noise detection with fitted peak SNR 4.34--6.11; there is no
separate high-SNR or resolved false-candidate population. This evidence does
not justify a post-fit SNR cut or a detection-threshold change. The strict
no-worse point-estimate condition would nevertheless fail this regression
endpoint, illustrating the already documented 50% directional-pass
probability under effective equality. Named review therefore removed that
condition before final-population freeze.
probability under effective equality. Named review therefore removed that
condition before final-population freeze.

The aggregate median unresolved-blend position is also slightly in the
opposite direction: 0.05455 beam for Hebog and 0.05175 beam for PyBDSF. The
positive-as-worse point estimate is 0.00279 beam and its one-sided 95% BCa
upper limit is 0.00682 beam, inside the proposed 0.01-beam margin. Hebog is
materially better in the associated 95th-percentile position tail (0.104
versus 0.395 beam) and both blend-flux endpoints. This second small directional
difference supports the reviewed interval-based decision and avoids tuning an
estimator to regression noise.
difference supports the reviewed interval-based decision and avoids tuning an
estimator to regression noise.

## One-look governance

After the completed named approval, the final manifest froze the generator
version, exactly 600 seeds, truth, WCS, beam, and endpoint strata. The reviewed
contracts freeze the margins, analysis rule, and stopping rule. Before opening
the population, implement and freeze the maintained evaluator for every paired
and absolute gate, then record the exact Hebog and PyBDSF revisions, container
or source-tree identities, and dependency inventories. Then:

1. run Hebog and both references on the same immutable images;
2. compile the isolated shards without deleting failures;
3. inspect the final result once; and
4. make no post-inspection parameter, margin, population, or sample-size
   change.

An infrastructure interruption may resume only the same frozen realizations.
A scientific failure remains evidence; it does not trigger another unseen
campaign.

The frozen dataset identifier is `phase4-final-paired-qualification-512`.
Its recipe SHA-256 is
`15f8f607463f2db4cf4c0eb72255a998784e2d83d3a0d7ebc45eb733f6fbc7db`
and the complete dataset-record SHA-256 used by the campaign evidence is
`07c736a9bafc79fb298ad1c076fb29b93d88ce9f988f38bba99c94af519d1fcb`.
The manifest records that no image or result had been generated or inspected
at freeze time. Its 600 seeds are disjoint from every previous Phase 4
population. A 90-degree layout and beam rotation preserve the governed
blend-to-beam geometry while a distinct WCS, background, invalid region, and
noise gradient reduce dependence on viewed populations.

## Basis and reviewed decisions

The endpoint families follow the completeness, reliability, astrometry,
photometry, blend, and failure-mode questions emphasized by the
[ASKAP/EMU Source Finding Data
Challenge](https://www.cambridge.org/core/journals/publications-of-the-astronomical-society-of-australia/article/askapemu-source-finding-data-challenge/A6C846F3ABB0105F026E3BD6B6EB9D19).
The advance declaration of margins and one-sided interval rule follows general
[non-inferiority guidance](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/non-inferiority-clinical-trials).
The implementation follows the documented [SciPy bootstrap
semantics](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html),
and whole-image resampling follows the
[cluster-bootstrap consistency literature](https://www.sciencedirect.com/science/article/pii/S0047259X12002175)
by preserving dependence within each image.

Gemma Danks, Data Processing Software Engineer, approved the following on
2026-08-03 before any final population was generated or inspected:
Gemma Danks, Data Processing Software Engineer, approved the following on
2026-08-03 before any final population was generated or inspected:

- every proposed margin is scientifically negligible for Rapthor and broader
  radio-continuum catalogues;
- 600 realizations are operationally proportionate after the independent
  assumptions are verified;
- the extra no-worse point-estimate condition is removed; signed point
  estimates remain mandatory report fields;
- the extra no-worse point-estimate condition is removed; signed point
  estimates remain mandatory report fields;
- the five-sigma high-confidence extension decision is scientifically
  proportionate given the wide independent point/clear margin and the cost of
  assigning a false physical size; and
- the co-primary and report-only endpoint split protects all material Hebog
  strengths without turning exploratory metrics into hidden gates.

The full named decision and supporting evidence are recorded in the
[Phase 4 scientific review record](phase-4-review-record.md).

The full named decision and supporting evidence are recorded in the
[Phase 4 scientific review record](phase-4-review-record.md).
