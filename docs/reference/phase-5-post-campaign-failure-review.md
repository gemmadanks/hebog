# Phase 5 post-campaign failure review

## Status and evidence boundary

This is the named scientific failure review requested by Gemma Danks on
2026-08-15 after the terminal post-failure campaign returned `fail`. It
authorizes prospective implementation and regression work only. It does not
change, reopen, or rescore the sealed campaign, and it does not authorize
Step 3, qualification, an external-equivalence claim, or removal of the
PyBDSF fallback.

The review used the sealed diagnostics only to locate failure families. Causes
and corrections were then reproduced with analytic tests and the existing
viewed Phase 5 development population. All campaign programs and terminal
evidence remain immutable at their approved revisions.

## Findings and corrections

| Failure | Root cause | Prospective correction |
| --- | --- | --- |
| Compact integrated-flux tails | The compiler treated fitted Gaussian-component catalogues as Rapthor source catalogues. It therefore replaced the fitted total of every unresolved component with peak flux. | Future compilers must request `fitted-gaussian-component` semantics. Rapthor source canonicalization remains unchanged. |
| Marginal compact fitted-axis tail | The beam-or-free source model was also published as the Gaussian component, discarding an available independently fitted free ellipse. | Retain the low-variance selected model for `SourceCandidate`, but publish the valid free ellipse in `GaussianComponent`. |
| Continuum integrated-flux tails and excess variance | The fixed four-beam aperture was unbiased but accumulated avoidable noise. | Measure original-pixel flux in a 1.5-major-beam nearest-owned aperture. |
| Continuum mask-precision near miss | Almost all false-positive pixels were one- or two-pixel, three-sigma boundary excursions attached to true sources; detached false sources were rare. | Retain dense opened support, calibrated high-S/N boundary pixels, and adjacent significant residual-B3 support within half a beam. Preserve nearest-segment ownership. |
| Shell and tile-corner position tails | Original-pixel three-sigma weights retained high boundary variance on diffuse shells. Pure geometric centres and morphology filling were inferior. | Use the already-computed residual-B3 reconstruction for diffuse-segment centroid weights, while retaining original weights when the measured peak-to-mean ratio exceeds 3.0. Original pixels still define peak and integrated flux. |

The peak-to-mean switch is a measured concentration rule, not a morphology
label. On the bounded development slice, all diffuse examples were at or below
2.31 and all compact-dominated mixed examples were at or above 4.01. The fixed
threshold of 3.0 lies in that separation. If the denoised signal cannot provide
a positive finite centroid, measurement falls back explicitly to the original
signal.

## Reproduced evidence

The compact diagnostic included 38,400 matched campaign components. Correct
component semantics reduced overall absolute integrated-flux p95 from 0.4132
to 0.1598, edge p95 from 0.5456 to 0.2085, and S/N-15 p95 from 0.5305 to
0.1453. These figures diagnose the closed result; they are not a revised
campaign decision.

The complete 80-image, 480-source existing development replay used the exact
post-failure observable-domain truth interpretation. With all prospective
Continuum corrections connected, it found:

- mean mask precision 0.9112, recall 0.9075, and IoU 0.8335;
- worst integrated-flux p95 0.1533, in scale-1 and mixed/invalid strata;
- worst position p95 0.4669, in shell/tile-corner strata;
- overall position p95 0.2946.

The aperture-only diagnostic placed every sampled morphology/scale flux tail
inside the frozen absolute limit. Boundary refinement improved precision,
recall, and IoU together. The denoised position alone regressed
compact-dominated mixed sources; the concentration switch restored original
weighting for that population and removed the regression.

## Decision and next evidence

The causes are sufficiently reproduced to retain these implementations as the
next prospective candidate. They are not sufficient to claim non-inferiority.
The next external evidence must:

1. use seeds disjoint from all development and closed external populations;
2. retain every absolute, paired non-inferiority, failure-denominator,
   excess-variance, and one-look rule from the failed campaign;
3. compare compact Gaussian components with PyBDSF Gaussian catalogues and
   Aegean components, without Rapthor source canonicalization;
4. bind the 1.5-beam aperture, multiscale boundary refinement, concentration
   threshold, source/component model split, and exact runtime identities;
5. use no fewer than the previous 1,600 Continuum and 800 compact images until
   a conservative exact-endpoint power audit justifies another count; and
6. obtain a separate named scientific approval before the one-look execution.

The closed result remains `fail`; Step 3 remains blocked pending that fresh
decision.
