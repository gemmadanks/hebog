# Phase 4U compact-blend qualification protocol

**Status:** completed and passed on 2026-08-05 after one frozen opening. The
pre-opening inputs, candidate, references, and decision rule were not changed.

Phase 4U is a separately named qualification of the compact candidate created
after the immutable Phase 4T failure. It does not rescore or replace Phase 4T.
It asked whether the orientation-independent association aperture removed the
observed blend-flux weakness without regressing any compact result relative to
released PyBDSF or pinned PyBDSF `master`.

The project owner previously asked Codex to act as the radio-astronomy expert
for this review. This is an AI-conducted synthesis of analytic evidence, the
retained campaigns, and peer-reviewed literature—not independent human or
institutional sign-off. Independent human review and controlled real-residual
evidence remain production-cutover gates.

## Why one new qualification is justified

Phase 4T passed all 20 paired endpoints against both PyBDSF references and 76
of 77 binding absolute gates. Its only failure was an unresolved-group
total-flux 95th-percentile absolute error of `0.207080` against the unchanged
`0.2` limit. The corresponding PyBDSF value was `0.600031`, but reference
superiority could not override the absolute gate.

Independent analytic work then showed that a fixed elliptical restoring-beam
aperture loses flux as a two-component blend rotates toward the beam's minor
axis. That is a geometric clipping effect, not evidence for an empirical flux
scale. The changed candidate keeps the lower-variance beam aperture when it
contains at least 90% of the selected fit and otherwise follows the fitted
ellipse. A seed-disjoint 18-realization development matrix reduced mean signed
blend error from the Phase 4T tendency of about -9.7% to about -2.4%.

This is a substantive, truth-independent algorithm change and therefore
justifies one new unseen qualification. The viewed Phase 4T result, threshold,
and population remain immutable.

## Frozen inputs and population

The machine-readable inputs are:

- `config/datasets/phase-4u-qualification.json`;
- `config/contracts/phase-4u-paired-noninferiority.json`;
- the unchanged `config/contracts/phase-4t-scientific-gates.json`; and
- `config/contracts/phase-4-measurement.json`.

The population contains 800 fresh 512-by-512 noise realizations and 54
observable truth groups. Forty-eight individually resolvable controls preserve
the Phase 4T SNR, morphology, edge, WCS, correlated-noise, noise-gradient,
negative-background, and invalid-pixel coverage. Six new unresolved compact
blends are at total peak SNR 27. Their pairwise-crossed design contains:

- beam-normalized separations `0.45`, `0.65`, and `0.80` FWHM;
- source-pair angles 0, 45, and 90 degrees from the beam major axis; and
- equal-flux and 2:1 component ratios.

The directional separation is normalized by the elliptical beam, rather than
by raw pixels or the major axis alone. This keeps every pair genuinely
sub-beam while testing the minor-axis geometry that exposed the old clipping.
Blend centers are at least 60.58 pixels from every individual control. Seeds
begin at `2026600001`, do not overlap any viewed Phase 4 campaign, and do not
overlap Phase 4U development seeds `2026501001`--`2026501018`.

No controlled real residual/noise injection is available, so this study cannot
support a real-data or production-cutover claim.

Canonical identities at freeze time are:

- recipe SHA-256:
  `2fd89b058a113f8318bd67ab7c05925f66b7cfa895fb6a2c7ea6a9746bad144d`;
- dataset-record SHA-256:
  `8e2e0dc5ed2eb7b1ad2d530c088849939b3a147ea0f8fbe52ac067b982c352dc`;
- manifest-document SHA-256:
  `57365cd616d0965d62eb12eae16b8323c1ce94a7f900e4113022a42b85a9c712`;
- comparison-protocol SHA-256:
  `3106e114508d3858eae44105ca8e03a4dfe0912726fca83ebf6ef0394c472b76`;
- scientific-gates SHA-256:
  `2841a2a93a17280c8decc5b0b1a7aa138279838f168a69504af37210aef13da6`;
  and
- measurement-contract SHA-256:
  `ab6a3d932a1b73f5414cfef8199831bbb394f990db1b885bd06f15f044b77ed0`.

The freeze scripts reproduce the manifest and protocol and refuse overwrite.
Reference execution remains pinned to released PyBDSF `1.14.1` at commit
`1b6e0a04ba6327bc1ce3f576928fe58b81d8c1cc` in container
`sha256:dce93991e2e671428ff8043a7e0d132294d2d2decf1e1587e9904d3e8f49b754`,
and PyBDSF `master` `1.14.2.dev40+gc70103be3` at commit
`c70103be3ae9ae9908286f144e6ce956acc0ce5c` in container
`sha256:f045820aa3e8bc0f5d90a35b90a4492048351de7d0255d6b7746b787d254b0d6`.
The Hebog candidate is the local commit containing this freeze; its exact
commit and dependency inventory must appear in the candidate shard.

## Registered power and decision

The same 20 paired endpoints, directions, non-inferiority margins, and
intersection-union decision remain. All binary population declarations match
the manifest. The weakest planned paired endpoint has about 97.07% interval-
exclusion power and the conservative familywise lower bound is about 96.99%,
above the 90% target.

The unchanged SNR-10 integrated-flux uncertainty question retains eight point
sources per image, the Phase 4S anticipated mean of `0.1062` sigma, unit
dispersion, 0.02 planning intracluster correlation, two-sided 95% interval,
and `0.15`-sigma margin. Its effective sample size is about 5,614 and planned
interval-containment power is about 90.69%.

The image/noise realization—not each source or blend—is the independent
sampling unit. Binary endpoints with multiple observations per image use a
0.02 planning intracluster correlation, including the six-blend completeness
endpoint. Coverage and mean-bias intervals use cluster-sandwich Student-t
intervals; dispersion resamples whole realizations with the unchanged fixed
10,000-resample bootstrap.

Every binding absolute gate, all paired endpoints against both exact
references, every stronger-Hebog envelope, and implementation completion must
pass. The unresolved-group total-flux tail remains capped at `0.2`; no Phase 4T
threshold is changed. An unexplained material diagnostic regression blocks
acceptance even if it is not a co-primary endpoint.

## One-look execution rule

Commit this protocol, population, exact candidate and reference identities,
and absent output paths before execution. The frozen output paths are:

- `benchmark-results/phase-4u/qualification-hebog.json`;
- `benchmark-results/phase-4u/qualification-pybdsf-release.json`;
- `benchmark-results/phase-4u/qualification-pybdsf-master.json`;
- `benchmark-results/phase-4u/qualification-compiled.json`; and
- `benchmark-results/phase-4u/qualification-decision.json`.

Run Hebog, released PyBDSF, and pinned `master` once on identical images.
Compile all three immutable shards before opening exactly one decision. A
scientific failure is terminal and cannot trigger a changed threshold,
population, endpoint, sample size, or replacement campaign. An infrastructure
interruption may resume only missing work from the same frozen population and
must not overwrite completed evidence.

A pass closes the compact-science start gate and permits substantive Phase 5
multiscale implementation. It does not authorize a release claim, remove the
PyBDSF fallback, or waive performance, scalability, real-data, and production
review gates.

## Immutable outcome

Hebog, released PyBDSF, and pinned PyBDSF `master` each completed 800/800
images. The three immutable shards were compiled before the decision was
opened exactly once. The compiler and evaluator accepted all frozen dataset,
seed, contract, implementation, and protocol identities.

The Phase 4U decision passed:

- 77/77 binding absolute gates passed;
- 20/20 paired endpoints passed against released PyBDSF;
- 20/20 paired endpoints passed against pinned PyBDSF `master`;
- 5/5 stronger-Hebog regression envelopes passed; and
- no implementation had a failed seed.

Hebog recovered all 4,800 unresolved groups. Its median absolute total-flux
error was `0.047567` and its 95th-percentile absolute error was `0.139196`,
inside the unchanged `0.2` maximum. The mean and median signed errors were
`-0.020217` and `-0.019847`, compared with about `-0.1085` and `-0.1099` for
both PyBDSF references. The worst per-geometry Hebog 95th-percentile absolute
error was about `0.1622`, so the improvement is not confined to one blend
orientation or flux ratio.

Four legacy whole-catalogue raw-error summaries failed their report-only
reference limits. They were non-binding by the frozen contract, were
essentially unchanged from Phase 4T, and did not reveal a material diagnostic
regression. All binding SNR-, edge-, uncertainty-, classification-,
catastrophic-, and unresolved-group gates passed. The closest paired endpoint
was catalogue reliability, whose upper one-sided regression limit was
`0.003529` against the frozen `0.005` margin.

The immutable evidence-file SHA-256 values are:

- Hebog shard:
  `cbeae07878c2fe3d801fdff816b00db23f6d03655fe5652932e13b9e95a359dc`;
- released-PyBDSF shard:
  `75fa0a3a53ae4a7c63ffb2cac63213c04380eab3160622d93dfe1c00f78ea23b`;
- PyBDSF-master shard:
  `4c9563f0fe8687da3a4d5370c39fbbcb8579483a8911d4f3a123da2a1b4a6f49`;
- compiled campaign:
  `0355537bcfc1c716a6b4b9e7d0269c6d78c66bfacdfb69925f37a13ce6b018a1`;
  and
- decision:
  `309ab639cafc5c8aafb75bc85e9b8d531def3e7c51ea424561bb399dc53795f0`.

This result closes the compact single-scale science start gate and permits
Phase 5 multiscale development. It does not retrospectively change a failed
historical campaign and does not establish performance, real-data,
large-scale, or production readiness.

## Scientific basis

- [ASKAP/EMU Source Finding Data Challenge](https://www.cambridge.org/core/journals/publications-of-the-astronomical-society-of-australia/article/askapemu-source-finding-data-challenge/A6C846F3ABB0105F026E3BD6B6EB9D19)
- [Condon, Errors in Elliptical Gaussian Fits](https://adsabs.harvard.edu/pdf/1997PASP..109..166C)
- [ATLAS Data Release 3](https://arxiv.org/abs/1508.03150)
- [ProFound radio source-finding comparison](https://academic.oup.com/mnras/article/487/3/3971/5511783)
- [SKA Science Data Challenge 1 results](https://academic.oup.com/mnras/article/500/3/3821/5918002)
- [Cameron & Miller, cluster-robust inference](https://doi.org/10.3368/jhr.50.2.317)

These sources support SNR-aware flux evaluation, explicit blend populations,
elliptical-beam-aware source characterization, and cluster-aware inference.
They do not make PyBDSF a scientific source of truth.
