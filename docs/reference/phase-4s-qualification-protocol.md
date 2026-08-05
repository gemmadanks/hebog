# Phase 4S compact qualification protocol

**Status:** expert-reviewed, frozen, and unopened on 2026-08-05. No image or
implementation result may be inspected until the contracts, manifest, and
candidate execution identity are committed.

This qualification asks one bounded question: is Hebog's compact,
single-scale behaviour scientifically acceptable against analytic truth and
non-inferior to the released PyBDSF version used by Rapthor? Pinned PyBDSF
`master` is a secondary robustness comparison. The campaign does not qualify
extended or multiscale emission.

The project owner asked Codex to conduct the expert pre-opening review. This
record is an AI-conducted synthesis of peer-reviewed radio-astronomy
literature, analytic contracts, and immutable Phase 4/4R evidence. It is not
independent human or institutional approval. Independent human domain review
and controlled real-residual validation remain recommended before production
cutover.

## Frozen inputs

The machine-readable inputs are:

- `config/contracts/phase-4s-paired-noninferiority.json`;
- `config/contracts/phase-4-measurement.json`;
- `config/contracts/phase-4-scientific-gates.json`; and
- `config/datasets/phase-4s-qualification.json`.

The population contains 800 paired whole-image noise realizations of one
512-by-512 field. Each image contains 33 observable truth groups: 32
individually resolvable compact sources and one unresolved two-source blend.
The individual population is partitioned into eight beam-compatible point
sources, 16 marginally resolved sources with continuously varied intrinsic
sizes, and eight clearly resolved sources. The SNR-10, 15, 25, and 50 strata
contain eight individual sources each.

The geometry crosses source and beam angles, rotated unequal-pixel WCS axes,
all four edges and four corners. It includes beam-correlated noise, a spatial
noise gradient, negative background, invalid pixels, and an unresolved blend.
No controlled real residual/noise injection was available. Synthetic
correlated Gaussian noise cannot support a real-data qualification claim.

The canonical identities at freeze time are:

- recipe SHA-256:
  `a49bf060515f777b745012317b4e0172fdfb60f9df88bf9dbe2a0ca70522f5de`;
- dataset-record SHA-256:
  `01e28063fec9be50bd47b155a79383093258d9df22ee1f9ca57286a0dd74ec63`;
- manifest-document SHA-256:
  `b0eac85a27101c25cf77ea1f4df45da6c33383b49c9cfd360039eac50eaa29d4`;
  and
- comparison-protocol SHA-256:
  `8db043b70dc295d2a36214fe3ffc5822f86ee89794ed36bb31f11b22b3040a96`.

The exact population can be reproduced without generating an image:

```console
uv run python scripts/validation/freeze_phase4s_qualification.py \
  --output /new/path/phase-4s-qualification.json
```

Both freeze scripts and all campaign/evaluator outputs refuse overwrite.

## Scientific decisions

The 5-sigma peak and 3-sigma island thresholds remain identical to Rapthor's
PyBDSF path. Compact association uses a 0.5-restoring-beam radius. The
ASKAP/EMU challenge supports reporting completeness and reliability against
SNR and using beam-scaled compact matching; exact catalogue row equality is
not the scientific criterion.

Five-sigma extension confidence remains Hebog's deliberately conservative
policy, not a claimed universal standard. Point-source specificity and
clear-source recall are separate gates. Covariance is propagated through
elliptical-Gaussian fitting and beam deconvolution. A weak intrinsic minor axis
or position angle near the resolution boundary is unavailable rather than
reported with false precision. Fitted shape, identifiable intrinsic axes,
classification, and Rapthor's `DC_Maj`, `E_RA`, `E_DEC`, and retained/rejected
decision remain governed.

The existing 20 paired compatibility endpoints are the co-primary
intersection-union decision against released PyBDSF. All must pass their
one-sided 95% upper-bound non-inferiority rule. Existing absolute truth gates
and the stronger-Hebog envelopes must also pass. Detailed SNR, morphology,
edge, position, flux, shape, angle, and uncertainty results remain visible
diagnostics. An unexplained material diagnostic regression still blocks
release through scientific review, but the 450 correlated Phase 4R
metric/stratum comparisons are not repeated as equal hypothesis-test votes.

Every binary endpoint declares a manifest population unit and exact count.
The executable audit confirms 33 association groups, 32 individual sources,
eight point sources, eight clear sources, and one unresolved group. At 800
realizations the weakest marginal endpoint has about 97.07% planned
interval-exclusion power. The dependence-robust union-bound lower limit for
the joint 20-endpoint decision is about 94.29%, above the binding 90% joint
target.

## One-look execution rule

Before opening the campaign, commit and record the exact Hebog source revision,
source-tree hash, package/dependency inventory, and matched released/master
PyBDSF environments. Then run Hebog and both references once on the identical
800 recipes. Candidate or released-reference failure makes qualification
fail; a pinned-master failure is retained and reported under the frozen
secondary policy.

Compile all three immutable shards before evaluating. The evaluator may write
one decision only. A scientific failure cannot trigger a changed estimator,
threshold, margin, population, endpoint, sample size, or replacement campaign
inside Phase 4S. An infrastructure interruption may resume only missing work
from the same frozen population without overwriting completed evidence.

## Scientific basis

- [ASKAP/EMU Source Finding Data Challenge](https://www.cambridge.org/core/journals/publications-of-the-astronomical-society-of-australia/article/askapemu-source-finding-data-challenge/A6C846F3ABB0105F026E3BD6B6EB9D19)
- [Condon, Errors in Elliptical Gaussian Fits](https://adsabs.harvard.edu/pdf/1997PASP..109..166C)
- [ATLAS Data Release 3](https://arxiv.org/abs/1508.03150)
- [ProFound radio source-finding comparison](https://academic.oup.com/mnras/article/487/3/3971/5511783)
- [SKA Science Data Challenge 1 results](https://academic.oup.com/mnras/article/500/3/3821/5918002)

These sources support completeness/reliability reporting, beam-aware
association, correlated Gaussian-fit uncertainty, conservative extension
classification, and separate treatment of complex/extended morphology. They
do not make PyBDSF a scientific source of truth.
