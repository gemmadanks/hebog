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

## Cumulative campaign regression audit

A chronological audit of all Phase 5 evidence found that the external compact
corrections have not yet converged monotonically:

| Transition | Improvements retained | Passing result lost |
| --- | --- | --- |
| Successor to confirmation | Eleven PyBDSF/Aegean position and fitted-axis decisions moved from fail to pass. | Seven Aegean fitted-position-angle decisions moved from pass to fail after selecting a free-only component. |
| Confirmation to post-failure | All seven fitted-position-angle decisions returned to pass with beam-or-free publication. Twenty-four of 27 underpowered Continuum decisions became passing, and 13 Continuum failures became passing. | The Aegean marginal fitted-axis p95 and released-PyBDSF S/N-15 integrated-flux p95 moved from pass to fail. One formerly passing Continuum filament flux tail also failed on the larger population. |
| Post-failure to current development candidate | Fitted-component semantics repair the compact flux error; the independent free ellipse improves the marginal fitted-axis tail. The Continuum development replay repairs the observed flux and position tails. | The free component also republishes the position-angle behaviour responsible for the seven confirmation failures. |

The last point is confirmed independently of the campaign decisions. A
diagnostic rerun of the current code on 20 evenly spaced images from the sealed
post-failure compact population used only temporary products and treated the
population as viewed development evidence. Marginal fitted-axis p95 improved
from 0.172 to 0.166. However, overall fitted-position-angle median changed from
effectively zero in the closed beam-or-free product to 1.145 degrees, while
Aegean measured 0.475 degrees. Unresolved fitted-position-angle p95 was 4.972
degrees versus Aegean's 0.814 degrees. Those differences exceed the unchanged
0.5-degree median and 1.0-degree p95 non-inferiority margins and reproduce the
same seven failed endpoint strata seen in confirmation. This is a regression
diagnostic, not a rescore of the closed campaign.

The internal Phase 5 sequence does not show the same oscillation. The paired
filter and three corrective reviews all rejected their candidates rather than
promoting and later losing a pass. The separately reviewed extended-position
follow-up passed both its 80-image development matrix and its 400-image
one-look confirmation. The current denoised-position change must nevertheless
retain that complete position matrix in the cumulative ledger because it
changes the confirmed estimator.

## Decision and next evidence

The current implementation remains useful development evidence, but it is not
ready to freeze as the next external candidate. First select a scientifically
coherent Gaussian-component model that passes position, flux, fitted-axis, and
fitted-position-angle requirements simultaneously. Then produce a
machine-readable cumulative ledger on the complete viewed compact and
Continuum regression populations. The ledger must show every historical
pass-to-fail and fail-to-pass transition and must separate algorithm changes
from truth, catalogue-semantics, compiler, and population changes.

Only after that ledger has no unapproved regression may the next external
evidence:

1. use seeds disjoint from all development and closed external populations;
2. retain every absolute, paired non-inferiority, failure-denominator,
   excess-variance, and one-look rule from the failed campaign;
3. compare compact Gaussian components with PyBDSF Gaussian catalogues and
   Aegean components, without Rapthor source canonicalization;
4. bind the reviewed aperture, multiscale boundary refinement, concentration
   threshold, source/component model, and exact runtime identities;
5. use no fewer than the previous 1,600 Continuum and 800 compact images until
   a conservative exact-endpoint power audit justifies another count; and
6. obtain a separate named scientific approval before the one-look execution.

The closed result remains `fail`; Step 3 remains blocked pending that fresh
decision.

## Cumulative replay and prospective correction

The complete 800-compact/1,600-Continuum cumulative replay at revision
`f1001c1...` did not reveal another compact reference trade: all 450 PyBDSF
and 143 applicable Aegean component comparisons passed. It did, however,
reject campaign readiness. Three compact absolute fitted-total uncertainty
bias intervals failed, and unrestricted B3 position weighting changed the
previously passing image-edge and filled-diffuse Continuum comparisons to
failures. Ten otherwise favourable Continuum comparisons were underpowered.

Two new seed-disjoint development reviews were therefore completed without
reopening any campaign population:

- On 200 compact realizations, a global uncertainty multiplier was rejected
  because it repaired bias by producing over-coverage. A 0.075-sigma
  fitted-total point correction was the smallest predeclared correction that
  passed all 15 coverage, bias, and dispersion gates. The limiting edge-bias
  interval was [-0.0051, 0.1458] against [-0.15, 0.15].
- On 80 Continuum realizations, unrestricted B3 weighting failed with a worst
  0.5329-beam position-p95 upper bound. A same-unit sum of the direct residual
  and its B3 reconstruction passed every position endpoint, with a worst
  0.4562-beam bound. The existing peak-to-mean concentration safeguard still
  retains direct weighting for compact-dominated segments.

The Continuum estimator is one weighted first moment over a regularized signal
plane. It is not the equal combination of two independently estimated
centroids rejected in Step 2C-A, and it uses neither injected morphology labels
nor campaign outcomes. The next full cumulative replay must retain every
previous pass. If only favourable paired comparisons remain underpowered, an
exact prospective power review must increase the fresh population before any
one-look approval; further algorithm tuning is not justified by power alone.

## Post-correction campaign recovery pre-review

### Status and boundary

This 2026-08-20 addendum is the Step 2C-PC pre-review of the terminal
post-correction failure. Gemma Danks approved its recommendations on
2026-08-20. The approval covers prospective implementation and
viewed-development regression work; it does not rescore the closed campaign,
authorize a fresh campaign, open Step 3, or alter a scientific gate.

The historical compiler has been restored byte-for-byte to SHA-256
`7a0558916ac003b71a781337dc710c99c359899c4d77f88486c1c206916b43f6`.
All 39 inherited compiler and protocol tests pass. The sealed campaign,
analysis, and decision remain unchanged at SHAs `9483abb0...`, `46dab5a12...`,
and `e00f0520...` respectively.

### Root-cause attribution

The terminal result is a valid failure of the products and compiler that ran,
but those products did not implement the candidate composition approved for
the campaign:

| Failure family | Evidence | Attribution |
| --- | --- | --- |
| Candidate identity | Every one of the 2,488 Hebog runs reports configuration SHA `72d5d5c1...`; the approved candidate configuration is `0e5dde51...`. The source revision is the expected `dfc3e25...`, so the discrepancy is behavioural composition rather than source identity. | Execution identity and fail-closed verification defect. |
| Thirteen Continuum integrated-flux p95 tails | The approved cumulative candidate measured original pixels in a 1.5-major-beam nearest-owned aperture. The campaign wrapper called the historical catalogue builder with its four-beam default, so the reviewed aperture never reached the emitted catalogue. | Candidate product translation defect, not evidence against the reviewed photometry algorithm. |
| Overall Continuum mask precision | The absolute precision gate passed at 0.9100, but the pinned-master paired upper confidence limit was 0.05107 against a 0.05 margin. The wrapper retained the earlier sub-beam cleanup rather than the approved residual-B3 multiscale boundary refinement. | Candidate product-generation composition defect. |
| Valid-region mask handling | Direct inspection found zero positive labels in the declared invalid rectangle for all 1,688 Hebog products and for all controlled and operational released/master PyBDSF products. Clipping to the valid domain would not repair the observed mask result. | Prospective compiler-contract hardening; not a cause of this failure. |
| Six compact/Aegean integrated-flux comparisons | The compiler invoked `diagnose_phase_four_realization` with its default Rapthor-source canonicalization. The approved comparison required `fitted-gaussian-component` semantics. The complete cumulative component view at the same candidate revision passed all 450 PyBDSF and 143 applicable Aegean comparisons. | Compiler measurement-semantics defect. |

The frozen matcher is not implicated: completeness, association precision and
recall passed, and the same matcher passed the cumulative like-component view.
The campaign must nevertheless remain a terminal `fail`; a corrected compiler
cannot be used to reinterpret its closed result.

### Recommended recovery

1. Build one shared prospective Hebog product adapter that invokes the full
   approved post-campaign product function, passes the 1.5-beam aperture and
   regularized position signal to catalogue measurement, and serializes the
   exact approved configuration. Reject a run whose reported configuration
   SHA differs from the approved candidate SHA.
2. Compose a new prospective compiler without editing historical programs.
   Its compact path must use fitted-Gaussian-component semantics. Its
   Continuum path must apply the valid-pixel domain symmetrically to every
   finder while keeping catalogue photometry separate from native support
   topology.
3. Add test-first normal, duplicate, merged-support, invalid-pixel,
   all-reference parity, configuration-mismatch, and closed-identity cases.
   Tests must fail if a wrapper silently falls back to historical defaults.
4. Replay the complete viewed cumulative matrix using the exact future runner
   and compiler composition. Require the approved candidate configuration
   SHA, no like-semantics regression, and all scientific gates; do not tune
   from the closed fresh population.
5. Recompute endpoint power and obtain separate named approval of the exact
   candidate, compiler/evaluator, population, and runtime identities before
   freezing any new seed-disjoint one-look campaign.

No new source-finding algorithm change is recommended at this point. The
first scientific question is whether the already reviewed candidate passes
when it is actually executed and measured as approved. Algorithm tuning is
justified only if the corrected cumulative replay exposes a reproducible
candidate-science failure on permitted development evidence.

The approved implementation now routes candidate configuration, refined
Continuum support, 1.5-beam photometry, and regularized position weighting
through one product adapter. A separate prospective compiler composition
enforces the candidate hash, fitted-component compact semantics, and one
symmetric valid-pixel domain for Hebog and both PyBDSF references. The viewed
cumulative replay consumes those shared seams; historical campaign programs
and closed evidence remain unchanged. Its focused normal, topology,
invalidity, reference-parity, failure, and identity contracts pass with 100%
branch-aware coverage of the new modules. The next permitted action is the
complete cumulative replay, not a fresh campaign.
