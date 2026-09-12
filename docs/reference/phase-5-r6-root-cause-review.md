# Phase 5 R6 scientific root-cause review

Date: 2026-09-09. Status: **review complete; prospective repairs, not a pass**.

The R6 failure is not an evaluator crash or evidence that PyBDSF was treated
as truth. Each finder was measured independently against injected analytic
truth. There are confirmed measurement-contract defects, a confirmed compact
estimator-policy bypass, and retained evidence of over-fragmentation. The
remaining calibration questions must be resolved on independent development
fixtures, not by adjusting the closed campaign's thresholds or scores.

## Scope and immutable evidence

This review concerns candidate `db8936b512370a1491f36845592fe3e8a24107ad`,
source SHA-256
`43fb41f20069a31627f0dbec09bdf1484bd2a04d633fe6563b94b09a554dd2cf`,
configuration SHA-256
`5eca0efc1995f206900506c87f2ca3cba6aa4a2f1a5155bc3e58863bf3cb75c4`.
Code tracing and analytic witnesses used its immutable execution checkout
`/private/tmp/hebog-r6-cumulative-evaluation-1b1cbae`, commit
`1b1cbae8cf8f05184cb2d095ced87175e2969849`, not later notebook repairs.

The [terminal snapshot](https://github.com/gemmadanks/hebog/blob/0ce253cf26a7954a58dc9a211eb01d8502e69025/docs/reference/phase-5-campaign-overview.md#2026-09-09-r6-cumulative-terminal-scientific-failure)
is authoritative: 885 comparisons pass, 288 fail and 14 are underpowered;
both readiness flags are false. All five safety checks pass. R6 and Phase 5
remain open. No prior uncertainty acceptance transfers.

| Evidence | SHA-256 |
| --- | --- |
| Closed terminal `source-catalogue-repair-cumulative-decision.json` | `7146f2e857c9473117c16d29f5bd8d55a2790c66d1c1643cd79b96aa8cc51d72` |
| Combined evaluation seal | `d14205d922e3a46b1cd93be3de84d745910b68f89a12f3ed00f5cb5f9d22ae5b` |
| Exhaustive terminal provenance verification | `5dde3be99d28a80b9bc1e1a23d57d4cac5db34d82e37b801e6c8e0a8030cdedf` |

For this review, every one of the 10,400 sealed finder-record files was
read and checked against its sealed SHA-256. Counts and descriptive
quantiles below use **already stored matches, signed residuals, native rows
and flags**. They are diagnostic subdivisions, not new binding endpoints,
confidence calculations, match assignments or campaign scores. The 800
compact and 1,600 Continuum inputs were not rerun. No reference finder or
campaign evaluator executed. Existing scientific and historical v1 records
remain untouched.

## Findings: compact science first

### C1 — Joint fitting bypasses the configured compact model selection (P1)

**Confirmed code path and independent witness.** In the frozen
`algorithms/fitting.py`, `fit_compact_gaussian_mixture` always allocates six
free-ellipse parameters per component and publishes a `free-elliptical`
model. Unlike `fit_compact_gaussian`, it never applies the requested
`beam-or-free` selection or its alternative-model evidence. This applies to
singletons too: `algorithms/component_measurement.py::measure_component_models`
always calls the joint solver. The public composition passes the reviewed
configuration returned by `phase_five_corrected_candidate_configs`.

On an independent exact point-source fixture with beam sigmas
`(1.6, 8/(2*pi*1.6))` pixels and angle 20 degrees, the existing single fitter
selects `beam-constrained`; the joint fitter selects `free-elliptical` under
the same `beam-or-free` request. This proves a policy bypass, not that every
free fit is wrong or that reinstating selection alone recovers parity.

**Recommendation:** preserve joint treatment of neighbouring emission, but
honour the reviewed selection policy with coherent component parameters and
uncertainties. Reuse existing model-selection machinery where appropriate;
do not splice flux from one model and shape/position from another. Require
singleton and joint-policy conformance, unresolved/marginal/resolved cases,
close blends, bound contact and unavailable-fit tests. Do not disable
deblending or replace a blend with independent contaminated fits.

### C2 — Large measurement context systematically bypasses GLS (P1)

**Confirmed fallback; its share of the error remains unquantified.** Every
one of the 38,376 matched current-Hebog compact truth rows carries
`correlated-gls-fallback`, `correlated-noise-sandwich-errors` and
`joint-gaussian-fit`. These are matched truth rows, not the total count of
all detected components. The public fitting window includes multiscale
model-adequacy halos, whereas
`fitting.py::_point_estimator_transform` admits dense correlated-noise GLS
only up to `maximum_gls_pixels=512`. The joint fitter uses all valid pixels
in that window rather than the configured owned-region support policy.

An independent boundary witness with the same finite correlation model
selects `correlated-gls` on a 16-by-32 grid (512 pixels), but falls back to
`diagonal-weighted`, reason `retained-region-exceeds-gls-limit`, on a
17-by-32 grid (544 pixels). Retained catalogue flags do not preserve the
per-fit fallback reason or pixel count, so the exact reason for each of the
38,376 fallbacks cannot be inferred from flags alone.

Sandwich errors account for correlation in parameter uncertainties; they
do not retroactively whiten the point-estimation objective. Noise-aware
Gaussian fitting is scientifically material, not just a speed choice
([Condon 1997](https://adsabs.harvard.edu/pdf/1997PASP..109..166C),
[Refregier and Brown 1998](https://arxiv.org/abs/astro-ph/9803279)).

**Recommendation:** separate bounded likelihood support from the larger
model-adequacy context, with explicit neighbour/wing treatment and noise
semantics. Do not simply raise a dense matrix limit to the halo area.
Require context-size, partition and masking invariance, correlated-noise
Monte Carlo calibration and runtime/memory checks. Retain per-fit model,
pixel count, fallback reason, bound/conditioning and covariance disposition
as small diagnostic records. Preserve the declared science while selecting
a scalable numerical method; no unreviewed approximation or limit change.

### C3 — Resolved-shape loss is concentrated at one corner geometry (P1)

**Confirmed localization and censoring stage, not a proven bad threshold.**
Of 6,400 clear-resolved truth rows, 803 lack a fully resolved result. Exactly
800 are `source-00036`, the SNR-25 corner case; all 800 were matched and
all carry `major-axis-not-significant`. The other three are one
`source-00032` major-axis-only result and two `source-00048` unresolved
results. Thus the 87.46875% recall is not broad non-detection of extended
compact sources. The labels identify frozen geometry cases, not cases to
tune or rerun.

The flag is emitted by
`algorithms/astrometry.py::_significant_deconvolved_axes`, which propagates
the native covariance and censors an intrinsic eigenvalue failing the
five-sigma significance rule. The retained rows establish this final
censoring stage. They do **not** establish whether the edge covariance is
miscalibrated, whether the available pixels genuinely contain insufficient
information, or how much C1/C2 contribute. Larger position/axis tails also
remain outside this one case.

**Recommendation:** independently test cropped/rotated elliptical beams,
all corners, pixel scales, SNR and invalid-pixel combinations. Validate the
joint marginal covariance and intrinsic-axis propagation against finite
differences and repeated new noise realizations before changing an
estimator. Keep classification and shape availability explicit. Do not
force `resolved`, remove uncertainty censoring, reduce five sigma or alter
the recall margin merely to recover the 800 rows.

## Continuum findings

### E1 — Singleton source substitution changes the measurement domain (P1)

**Confirmed end-to-end analytic reproduction.** In
`validation/products.py::_reconstructed_source_rows`, a single component in
`compact_ids` replaces the source's signed-aperture row with the Gaussian
component row. `_fitted_component_row` supplies the Gaussian's whole-plane
integral and model centre. There is no observable-domain condition on this
replacement. A clipped diffuse Gaussian can pass model adequacy and enter
this branch. `validation/observable_truth.py::measure_observable_truth`,
however, defines flux on finite valid image pixels and centroid on declared
truth support intersected with that domain.

A complete frozen public-composition witness uses a 49-by-65 image,
`10*exp(-0.5*((x-0.7)^2/6^2 + (y-24)^2/4^2))`, zero background, unit RMS,
a circular four-pixel FWHM beam and unchanged 5/3-sigma, seven-pixel
detection settings. Declared analytic support is signal at least three.
One source is published with Gaussian-model flag, flux 83.177664 Jy and
centre `(0.7, 24)`. Observable truth has flux 48.189015 Jy and centroid
`(3.445542, 24)`. The source therefore overstates observable flux by
72.6071% even with **no noise or background error**. The Gaussian fit itself
correctly recovers its model; the wrong step is substituting that different
quantity for the source-domain measurement.

The retained edge population is consistent with this mechanism:

| Current edge-source estimator | Count / 1,600 | Median signed fractional flux error | Position-error p95 (beams) |
| --- | ---: | ---: | ---: |
| Gaussian substitution | 613 | +0.586108 | 1.517218 |
| Signed aperture | 987 | -0.011266 | 0.428877 |

These are conditional diagnostics, not an alternative gate or a claim that
all aperture cases pass. The non-edge diffuse object has only 33 recorded
splits and position p95 0.226634 beams. The reported `morphology-diffuse`
stratum also includes the edge object; it must not be interpreted as an
independent population-wide diffuse failure.

**Recommendation:** keep native Gaussian centres/total flux in the
component catalogue and define a consistent observable-domain source
measurement. Apply valid-domain accounting to edge/invalid-pixel sources;
never make the answer depend on whether a singleton happened to qualify
for Gaussian substitution. Keep uncertainty/coverage limitations explicit.
Do not modify frozen truth to include unseen sky or rescore old source rows.
An intentional change of public source semantics needs scientific-owner
review and new candidate-bound evidence.

### E2 — Model adequacy does not establish astrophysical independence (P1)

**Observed fragmentation and a confirmed restrictive code mechanism; not
complete attribution of every split.** Saved matching records mark 701/1,600
shell and 689/1,600 curved-filament truth objects as split. Primary matched
Gaussian singleton rows account for 386 shell cases (median signed flux
error -0.759723) and 322 curved cases (-0.654449). Aperture rows also have
fragmentation tails, so changing the singleton flux estimator alone cannot
repair this failure.

In `component_measurement.py`, an adequate sum of Gaussian models permits
`_model_and_groups` to split components using directional FWHM overlap.
`source_association.py::constrain_source_memberships` then removes those
labels from their previous hierarchy groups. Later
`_extended_residual_groups` excludes protected compact labels; the separate
resolved-loop path cannot establish every open curved morphology. A good
sum of fitted Gaussians is evidence of a good emission model, not proof that
its separated components are independent astronomical sources. Conversely,
shared coarse support alone must not re-merge genuine neighbouring sources.

**Recommendation:** review bounded extended-morphology association together
with, not only after, compact protection. Retain competing hierarchy,
model-group and residual-group decisions before publication. Require open
arcs, incomplete/asymmetric shells, compact cores in halos and independent
nearby compact sources as paired positive/negative fixtures. Preserve each
component and single ownership of source flux; do not blindly regroup an
entire connected island or sum post-hoc matched fragments.

### E3 — Residual mixed/invalid-pixel astrometry needs calibration evidence

The mixed object's 41 Gaussian-substituted rows have median flux excess
0.511449 and position p95 0.941313 beams. Its 1,559 aperture rows still have
position p95 0.493818 beams. E1 therefore cannot explain all mixed-source
position loss. `products.py::_segment_position` selects signed-original or
denoised weights from peak/mean concentration, on assigned measurement
support. Source ownership, masking, denoising and residual background can
all affect the result. Current records do not separate those contributions
well enough to declare one of them the cause.

**Recommendation:** in the prospective fixture work, retain both candidate
centroid estimates and their domains, estimator-selection reason, local
background/RMS residuals, signed flux and unavailable disposition. Use
independent one-factor synthetic cases to isolate support assignment,
mask asymmetry and background error. Do not adjust the peak/mean selector
or thresholds from these viewed residuals. This remains an explicit causal
uncertainty, not a justification for claiming parity or launching more
qualification images.

## Why the earlier quick tests were insufficient

The existing tests correctly cover Gaussian recovery, joint neighbour
fitting, numerical derivatives, ownership safety and selected resolved-loop
fixtures. In particular, `test_edge_context_recovers_the_in_image_gaussian`
asserts recovery of the underlying Gaussian centre/axes, not agreement of
the **published source** with observable-domain truth. The joint-fit tests
do not establish configured beam/free selection equivalence or GLS admission
through the much larger public context. Handfuls of favourable loop fixtures
do not measure noisy fragmentation or covariance calibration at corners.
Passing those tests was implementation evidence, not sufficient scientific
coverage; neither their assertions nor the campaign gates should be weakened.

## Prospective repair and validation order

1. Obtain review of the C1--C3/E1--E3 recommendations and source/component
   measurement contract. Freeze independent analytic fixtures and preserve
   the failed R6 terminal. No execution authorization is created here.
2. Implement C1/C2 test-first, then C3 covariance/edge checks with unchanged
   classification rules. Independently fix E1 at the public source boundary.
3. Address E2/E3 with attribution-first fixtures and paired compact-retention
   counterexamples. Resolve or explicitly report remaining causal uncertainty
   before claiming a replacement is ready.
4. Exercise the exact public path in Serial and caller-owned existing Dask,
   plus geometry/context/partition/order invariance and bounded cost. Run a
   short seed-distinct noisy development matrix spanning every failed
   geometry, not merely the old happy-path suite. Full lint/type/coverage,
   equivalence, docs, packaging and review gates precede identity freezing.
5. Only then propose exact candidate-bound cumulative execution. Retained
   reference bytes may be reused only with verified identities and unchanged
   applicable semantics; changed Hebog measurements require new evidence.
   Never overwrite/re-evaluate closed R6 records. A fresh unopened sentinel
   follows a passing cumulative gate, not this review. Preserve the user's
   sub-12-hour final-campaign budget without dropping known-risk geometries.

PyBDSF itself distinguishes Gaussian components from grouped sources and
uses multiscale residual processing for extended emission
([official capabilities](https://pybdsf.readthedocs.io/en/latest/capabilities.html)).
Keeping both levels with precise semantics is preferable to hiding these
failures by reporting only components. This review copied no PyBDSF
implementation and proposes no gate, comparator or truth change.

## Review evidence and reproducibility

Local review workspace: `/private/tmp/hebog-r6-root-review-t5whoz`.
The following audit artifacts are untracked; essential findings, counts and
analytic recipes are retained above so the review does not depend on their
continued presence. Normal tests must not depend on this workspace or any
campaign output directory.

| Artifact | SHA-256 |
| --- | --- |
| Read-only `inspect_records.py` | `4b6aebdbaf46ca1f5bac7446f655e7cf176e2b7ee3034c76b7f2513c1f4f8fb4` |
| `record-counts.txt` | `c89bb1f8428c2b43f59cef76f294c771b6d7d5cb54bbc002b872e1059cfbd1ca` |
| Independent `analytic_probes.py` | `23b783b895ab2c18aa9a9656085dcf4b6bc36e534ced0959f6a40d414ee8924d` |
| `analytic-probes.txt` | `b74a6a0a4c1dd747f873018e883910a07e8788f003e9758ff0cabe5106b991a3` |

Analytic probes ran with the immutable checkout's `src` and repository first
on `PYTHONPATH`, the existing main `.venv/bin/python`, and OMP/OpenBLAS/MKL/
Numba thread budgets of one. No environment synchronization occurred. They
use independent unit fixtures, not campaign seeds or image cutouts. An
initial strongly sub-beam witness did not distinguish the single and joint
solvers because the single solver legitimately preferred its free model;
the final exact-beam witness tests the intended selection branch. The first
diagnostic reader also encountered differing native/adapted PyBDSF IDs;
attribution was restricted to current-Hebog records, while all finder-file
hashes were still verified. Neither preliminary check changed any evidence.

The review is not a proof of global optimality or that these repairs will
make all 288 failures pass. Numerical calibration, association ambiguity,
the 14 underpowered comparisons and replacement-candidate qualification
remain governed work, with no permission to tune on closed results.
