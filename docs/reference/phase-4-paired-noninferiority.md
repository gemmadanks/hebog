# Phase 4 paired non-inferiority protocol

**Status:** draft-provisional; named scientific review and independent
assumption verification are required before a final unseen population is
created.

This protocol answers a deliberately narrower question than “does Hebog equal
PyBDSF byte for byte?” It asks whether Hebog passes the existing truth-based
science gates, retains its demonstrated strengths, and is no worse than the
released PyBDSF used by Rapthor by any practically meaningful amount. Pinned
PyBDSF `master` remains a secondary robustness and compatibility anchor.

The machine-readable source is
`config/contracts/phase-4-paired-noninferiority.json`.
It is not yet an approved contract, and it does not contain the final campaign
seeds or truth.

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

Every co-primary endpoint must satisfy both conditions:

1. its point estimate is zero or negative, so Hebog is observed to be no worse;
2. its one-sided upper confidence limit is within the predeclared practical
   regression margin.

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
such source per realization. The point-estimate rule still forbids an observed
trade of one metric for another; these margins bound sampling uncertainty
rather than authorize a known regression.

## Power and its limitation

The proposed final design has 600 independent noise realizations, three times
the population used by each viewed campaign. A normal design approximation
uses paired discordance for binary outcomes, a cluster design effect for
multiple sources in one image, and the standard deviation of realization-level
paired statistics for continuous outcomes. Under the provisional assumptions,
the weakest interval-exclusion power is 92.2%; point specificity is 94.5% and
the catastrophic rate is 93.3%.

Run the executable calculation with:

```console
uv run python scripts/validation/calculate_phase4_paired_power.py \
  config/contracts/phase-4-paired-noninferiority.json
```

The 90% target applies to exclusion of the non-inferiority margin. The
additional no-worse point-estimate rule is intentionally stricter. If the true
paired difference were exactly zero, that directional condition would pass
only half of repeated experiments; no finite sample size can turn exact
equality into a 90%-probability directional result. The calculation therefore
reports interval-only, point-direction, and combined probabilities separately
rather than making an inflated “90% chance of overall passage” claim.

The discordance, within-image correlation, and paired-standard-deviation values
are currently provisional planning inputs, not measured facts. Before review
can change the status to `reviewed`, a maintained same-image run on independent
development/regression data must verify each bound. If a bound is exceeded,
the realization count must be increased and reviewed before the final
population is frozen. Sample size must not change after that population is
opened.

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
at 3.38 sigma and clear truth began at 17.92 sigma. Phase 4 now proposes a
five-sigma high-confidence catalogue decision, replacing the earlier
two-sigma boundary while retaining the same statistic. The analytic and
independent worst-margin tests pass, but this policy is not approved and the
pre-change campaign cannot establish its paired endpoint or variance. Named
review and a refreshed complete run remain mandatory.

## One-look governance

After named approval, freeze the generator version, exactly 600 seeds, truth,
WCS and beam strata, scientific contracts, both exact PyBDSF revisions,
container identities, margins, analysis code, and stopping rule. Then:

1. run Hebog and both references on the same immutable images;
2. compile the isolated shards without deleting failures;
3. inspect the final result once; and
4. make no post-inspection parameter, margin, population, or sample-size
   change.

An infrastructure interruption may resume only the same frozen realizations.
A scientific failure remains evidence; it does not trigger another unseen
campaign.

## Basis and review questions

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

Named review must decide whether:

- every proposed margin is scientifically negligible for Rapthor and broader
  radio-continuum catalogues;
- 600 realizations are operationally proportionate after the independent
  assumptions are verified;
- the stricter no-worse point-estimate condition should remain in addition to
  conventional non-inferiority; and
- the five-sigma high-confidence extension decision is scientifically
  proportionate given the wide independent point/clear margin and the cost of
  assigning a false physical size; and
- the co-primary and report-only endpoint split protects all material Hebog
  strengths without turning exploratory metrics into hidden gates.
