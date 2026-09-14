# Phase 4T compact confirmation protocol

**Status:** opened exactly once and failed on 2026-08-05. All three
implementations completed the 800-image population; Hebog passed both sets of
20 paired endpoints and 76/77 binding absolute gates, but its unresolved-group
total-flux tail exceeded the unchanged absolute limit. The terminal result is
preserved without rounding or rescoring. Phase 4U is the separately governed
later candidate that passed.

Phase 4T is a separately named confirmatory study after the immutable Phase 4S
failure. It does not rescore or replace Phase 4S. It asks whether Hebog passes
the corrected explicit morphology truth semantics, the unchanged absolute
uncertainty limits, and the same paired compatibility decision on a fresh,
adequately powered compact population.

The project owner asked Codex to perform the scientific review. This is an
AI-conducted synthesis of the retained evidence and peer-reviewed
radio-astronomy literature, not independent human or institutional sign-off.
Independent human review and controlled real-residual evidence remain
recommended before production cutover.

## Why a separate confirmation is justified

Phase 4S completed all 800 images for all three implementations and passed all
20 paired endpoints against released PyBDSF and pinned `master`. Its absolute
decision still failed. Post-opening review found that fixed 2% raw median
position and peak-flux limits were below the mixed-SNR noise floor for all
three implementations, while the point-specificity scorer compared 6,400
correct Hebog `unresolved` states with a projection-contaminated noiseless
truth deconvolution.

Those are estimand and truth-construction defects. They are corrected only for
future evidence: declared intrinsic morphology is authoritative, and raw
mixed-SNR position/flux/shape distributions are report-only. Binding
SNR-specific normalized-residual bias, coverage, and dispersion remain
unchanged. In particular, the SNR-10 integrated-flux mean-residual margin stays
at `0.15` sigma. Phase 4S missed that bound narrowly and the result is not
waived.

## Frozen inputs and population

The machine-readable inputs are:

- `config/datasets/phase-4t-qualification.json`;
- `config/contracts/phase-4t-paired-noninferiority.json`;
- `config/contracts/phase-4t-scientific-gates.json`; and
- `config/contracts/phase-4-measurement.json`.

The population contains 800 fresh 512-by-512 noise realizations. Each image
contains 49 observable truth groups: 48 individually resolvable sources and
one unresolved two-source blend. The individual population contains 32 point
sources, eight marginally resolved sources, and eight clearly resolved
sources. Every SNR-10, 15, 25, and 50 block contains eight declared point
sources; point and non-point cases include edge examples.

The field retains rotated unequal-pixel WCS axes, every edge/corner topology,
continuous source sizes and angles, beam-correlated noise, a noise gradient,
negative background, invalid pixels, and one unresolved blend. Its seeds begin
at `2026400001` and are disjoint from every viewed Phase 4/4R/4S population.
No controlled real residual/noise injection is available, so this study cannot
support a real-data or production-cutover claim.

Canonical identities at freeze time are:

- recipe SHA-256:
  `e39400565031867f3412a640ec55aa88e4807ff627affff6439c969e3445a696`;
- dataset-record SHA-256:
  `3afb044f413fbd3aa4748069b09255fbfe300b9a3f47c79f3589bab4ff06ee23`;
- manifest-document SHA-256:
  `919d8a32c4cdbd41fdb16a803aeed850d50af4eedc46d331c5a4dbc224ff5333`;
- comparison-protocol SHA-256:
  `2997015cb5235d5be9f3029d563455974fe1a1948843b5a50266fab616e094ee`;
  and
- scientific-gates SHA-256:
  `2841a2a93a17280c8decc5b0b1a7aa138279838f168a69504af37210aef13da6`.

The manifest and protocol freeze scripts reproduce those canonical documents
and refuse overwrite.

Reference execution remains pinned to released PyBDSF `1.14.1` at commit
`1b6e0a04ba6327bc1ce3f576928fe58b81d8c1cc` in container
`sha256:dce93991e2e671428ff8043a7e0d132294d2d2decf1e1587e9904d3e8f49b754`,
and PyBDSF `master` `1.14.2.dev40+gc70103be3` at commit
`c70103be3ae9ae9908286f144e6ce956acc0ce5c` in container
`sha256:f045820aa3e8bc0f5d90a35b90a4492048351de7d0255d6b7746b787d254b0d6`.
The Hebog candidate is the local commit that freezes this protocol; its exact
commit and dependency inventory must appear in the candidate shard before the
first reference result is accepted.

## Registered power and decisions

The same 20 paired endpoints remain the released-PyBDSF co-primary
intersection-union decision. Every binary population declaration matches the
manifest. At 800 images the weakest planned paired endpoint has about 97.07%
interval-exclusion power and the conservative union-bound joint lower limit is
about 96.07%, above the 90% target.

The retained absolute question is powered separately. The design freezes the
Phase 4S estimate (`0.1062` sigma), unit planning dispersion, eight SNR-10 point
sources per image, a 0.02 planning intracluster correlation, a two-sided 95%
confidence interval, and the unchanged `0.15`-sigma margin. The Phase 4S
SNR-10 point residuals had an estimated ICC of about `-0.0097`; the positive
planning value therefore adds a small pre-opening allowance rather than
assuming the observed negative estimate will repeat. The resulting effective
sample size is about 5,614 and planned interval-containment power is about
90.69%. Changing the viewed effect, margin, correlation, population, or sample
size after opening is prohibited.

The image/noise realization—not each fitted source—is the independent sampling
unit. Coverage and mean-bias intervals therefore use a cluster-sandwich
Student-t interval, and the dispersion interval resamples whole realizations
with a fixed-seed percentile bootstrap. This prevents eight sources sharing
one background/noise realization from being counted as eight independent
experiments. The numerical uncertainty margins and 10,000-resample budget are
unchanged from Phase 4S.

Every binding absolute gate, all 20 paired endpoints against released PyBDSF,
the independently reported `master` endpoints, every stronger-Hebog envelope,
and implementation completion must pass. Raw mixed-SNR distribution medians
and tails remain visible report-only diagnostics. An unexplained material
diagnostic regression still blocks expert acceptance even when it is not a
co-primary hypothesis.

## One-look execution rule

Commit this protocol, population, gate document, exact candidate revision,
reference revisions, environment identities, and absent output paths before
running. Then run Hebog, released PyBDSF, and pinned `master` once on identical
images. Compile all three immutable shards before opening the decision.

A scientific failure is terminal for Phase 4T. It cannot trigger another
threshold, endpoint, population, sample-size, or replacement-campaign change.
An infrastructure interruption may resume only missing work from the same
frozen population without overwriting completed evidence. A pass permits
substantive Phase 5 multiscale implementation; it does not authorize a compact
release claim, remove the PyBDSF fallback, or waive performance, scalability,
real-data, and production review gates.

## Scientific basis

- [ASKAP/EMU Source Finding Data Challenge](https://www.cambridge.org/core/journals/publications-of-the-astronomical-society-of-australia/article/askapemu-source-finding-data-challenge/A6C846F3ABB0105F026E3BD6B6EB9D19)
- [Condon, Errors in Elliptical Gaussian Fits](https://adsabs.harvard.edu/pdf/1997PASP..109..166C)
- [ATLAS Data Release 3](https://arxiv.org/abs/1508.03150)
- [ProFound radio source-finding comparison](https://academic.oup.com/mnras/article/487/3/3971/5511783)
- [SKA Science Data Challenge 1 results](https://academic.oup.com/mnras/article/500/3/3821/5918002)
- [Cameron & Miller, A Practitioner's Guide to Cluster-Robust Inference](https://doi.org/10.3368/jhr.50.2.317)

These sources support SNR-aware uncertainty interpretation, explicit
completeness/reliability and morphology populations, and separate evaluation
of compact and extended emission, as well as cluster-aware inference when
several measurements share one independent realization. They do not make
PyBDSF a scientific source of truth.

## Immutable outcome

The one-look decision opened on 2026-08-05. Hebog, released PyBDSF, and pinned
PyBDSF `master` each completed all 800 realizations. Hebog passed all 20 paired
non-inferiority endpoints against each reference, every uncertainty gate, and
76 of 77 binding absolute gates in total. The targeted SNR-10 integrated-flux
uncertainty result passed with mean normalized residual `0.06121` and a 95%
cluster-aware interval `[0.03743, 0.08500]` inside the unchanged
`[-0.15, 0.15]` limit.

The decision nevertheless failed as pre-registered. Hebog's
95th-percentile absolute unresolved-group total-flux error was
`0.2070797655`, above the frozen `0.2` maximum. The corresponding values for
released PyBDSF and pinned `master` were both `0.6000309649`, and the paired
upper confidence limits strongly passed, but superiority to the references
does not override an absolute gate. The `unresolved-group-errors` stronger
envelope consequently failed.

Phase 4T is terminal and will not be rounded, rescored, or repeated on the
unchanged candidate. Its result motivates general blend-flux investigation on
independent development and regression data; it does not authorize tuning to
these seeds or changing this viewed gate.
