# Current scientific campaign overview

This page summarizes the current finder candidate and unresolved scientific
work, as recorded on **13 September 2026**. Phase 5 remains part of immutable
campaign names; it no longer defines the size of a release. See
[release status](release-status.md) for current public capabilities and the
[implementation plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md)
for merge, experimental release and later qualification tasks.

## Current candidate and evidence

Composition **v17** adds stable background/coarse-RMS boundary extrapolation
to the v16 Gaussian-fallback admission repair. Independent numerical,
public Serial/existing-Dask and installed-wheel checks pass. The release
handoff and non-executable candidate identities are recorded in `LOG.md`;
they do not qualify the candidate or transfer the v15 campaign result. The latest completed
campaign is for **v15**, science commit `73ab5af...`, which includes the Gaussian-validity
repair and the approved F4 filtered-response correction. The
[frozen identity review](https://github.com/gemmadanks/hebog/blob/main/config/contracts/phase-5-filtered-response-domain-repair-identity-review.json)
binds its source, configuration and validation. It remains
`development-unqualified`.

| Evidence | What it establishes | Limit |
| --- | --- | --- |
| Focused F4 fixtures and Serial/existing-Dask checks | Each significance plane is paired with its physical filtered response; finite-positive validation, thresholds and original-pixel measurement ownership are retained. | Mechanism and execution correctness, not population parity. |
| V15 portable suite and frozen equivalence checks | 3,992 portable tests, 95.2963% branch-aware coverage and 27 frozen equivalence tests pass for that repair. | Does not replace candidate-bound held-out qualification or the full platform matrix. |
| Exact previously failing input | One complete public capture succeeds after F4. | No scientific evaluation or parity verdict from that control. |
| Result-neutral 24-input public screen | Captures, native product reading, evaluation and aggregation complete; two Serial/Dask scientific digests agree exactly. | All 1,187 point rows are unchanged: 1,138 within margin, 49 beyond. No powered confidence-bound pass is claimed. |
| V15 cumulative replay | Completed normally on 12 September: **scientific fail**, with 1,115 passing, 32 failed and 40 underpowered binding comparisons. All five safety checks pass. | Neither cumulative readiness nor all-required-endpoints pass. This is regression evidence, not fresh qualification. |

Terminal verification accounts for all 2,400 current-Hebog Serial captures and
evaluations, 12 exact existing-Dask agreements and 8,000 reused comparator
records. It checks all 9,600 underlying retained native reference runs,
candidate/configuration/program identities, immutable checkout, seals and
process provenance. No new incumbent or external finder ran. The atomic
terminal is preserved byte-for-byte in the main ignored evidence namespace;
exact paths, checksums and validation are in
[LOG.md](https://github.com/gemmadanks/hebog/blob/main/LOG.md).

## Comparison with the references

Each finder is evaluated independently against analytic injected truth before
comparing like semantics. PyBDSF is not truth. These are the terminal's binding
comparison arrays, not raw diagnostic decisions before semantic applicability:

| Comparator | Pass | Fail | Underpowered |
| --- | ---: | ---: | ---: |
| Released PyBDSF | 327 | 0 | 11 |
| Pinned PyBDSF master | 330 | 0 | 8 |
| Aegean, applicable compact endpoints | 139 | 0 | 4 |
| Earlier Hebog incumbent | 319 | 32 | 17 |

**Compact first:** all binding position, peak-flux and integrated-flux
comparisons against both PyBDSF references pass. Overall completeness is
99.8704% versus released PyBDSF's 99.9954%; reliability is 99.7549% versus
99.8682%. Median position error is 0.02077 beam versus 0.02252; p95 integrated
flux fractional error is 0.1752 versus 0.3450. These favorable point estimates
are not a new prospectively tested superiority claim. Uncertainty calibration
and unresolved-axis retention regress against the earlier Hebog incumbent.

**Continuum second:** all 113 released-PyBDSF comparisons pass. Against master,
112 pass and overall mask precision is underpowered. Overall completeness is
1.0 and reliability 0.9294, versus released PyBDSF's 0.9994 and 0.5670.
Integrated-flux p95 fractional error is 0.3074 versus released PyBDSF's 0.8518,
but the incumbent is better at 0.2694. Some extended flux tails and signed
source-centroid offsets regress against that incumbent. Those centroid
endpoints describe irregular source segments, not Gaussian peak positions.

There is **no definite failed binding external-reference comparison**, but
underpowered comparisons prevent general parity; incumbent failures prevent
quality-retention readiness. Finite/product-validity checks do not prove that
a numerically accepted model is a scientifically adequate description.

## Complete non-passing endpoint inventory

The following groups account for all **32 failures and 40 underpowered
comparisons**. Counts are comparisons, not independent defects; related
availability endpoints share missing-source witnesses. Exact endpoint IDs,
native values, frozen margins and confidence limits remain in the terminal.

| Issue and affected strata | Fail | Underpowered | Interpretation and next disposition |
| --- | ---: | ---: | --- |
| Compact uncertainty: bias (edge, overall, unresolved, SNR 10/15/25/50); dispersion and one-sigma coverage (edge, overall, all three shape classes, SNR 10/15/50) | 23 | 4 | Failures are incumbent retention. Underpowered rows are released-PyBDSF dispersion at edge/clearly resolved and incumbent bias at clearly/marginally resolved. These values are calibration distances, not raw coverage fractions. Statistical release limitation needs human review; do not inflate errors to pass. |
| Compact p95 fitted axis, unresolved | 1 | 0 | Incumbent retention: 0.0760 versus 0.0605, exceeding the 0.01 regression margin. Review classification/model selection with the validity issue below; not evidence for changing the margin. |
| Compact SNR-10 completeness, association identity/pair recall, fitted-shape availability; applicable deconvolution/uncertainty availability and point specificity | 0 | 25 | Four comparisons with Aegean and seven with each other comparator. Completeness is 99.5833%; the regression upper bound versus released PyBDSF is 0.5104 percentage points against a 0.5-point margin. Inconclusive, not a pass or a measured 0.51-point loss. |
| Compact edge resolved-classification recall and deconvolved-shape availability | 0 | 2 | Released-PyBDSF comparisons; review edge model admission with the stored high-SNR cases below. |
| Compact edge p95 integrated flux | 0 | 1 | Incumbent retention: 0.1940 versus 0.1780; upper regression bound 0.0211 exceeds margin 0.02. Retain as an inconclusive tail warning. |
| Continuum absolute mean x offset: shell, above compact-deblend limit, tile corner, tile boundary | 4 | 0 | Incumbent retention. The first three overlapping strata have 0.1075 versus 0.0238 beam; tile boundary 0.0595 versus 0.0090. Source-centroid/association limitation, not a global WCS shift. |
| Continuum integrated-flux p95: image edge, curved filament, filament, scale 2 beams | 4 | 7 | Incumbent retention. Errors are 0.1676–0.2686 versus 0.1098–0.1925. Underpowered strata: invalid pixels, diffuse, mixed, overall, scales 1/4 beams and varying noise. Broader faint-association F2 remains a proposed deferral, not a repaired or passing endpoint. |
| Continuum mask precision, overall | 0 | 1 | Versus master: 0.9105 versus 0.9597; regression upper bound 0.05053 against margin 0.05. Inconclusive mask/contamination limitation. |

The earlier screen's 49 point warnings are superseded for current inference
by this complete terminal, not erased. The
[follow-up review](phase-5-v13-followup-review.md) retains independent mechanism
tests, including negative controls: a larger fitting window did not reliably
repair uncertainty coverage, and faint fragmentation was not explained solely
by background/RMS error. These do not establish one cause for all current
failures. Planning deviations and longer-term absolute objectives remain
report-only under the unchanged contract.

## Correctness inventory and recommended next action

Read-only inspection of all 800 saved compact evaluations finds 38,344 matched
and 56 unmatched truth rows. Forty unmatched rows are SNR 10, six SNR 15 and
ten SNR 50. All ten SNR-50 misses involve the same clearly resolved edge/corner
source (`source-00048`) across different noise realizations; do not describe
them as ordinary interior-source losses or harmless without diagnosis.

There are also two **published SNR-50 model failures** at that same corner:

| Seed | Native fallback | Integrated-flux error | Peak-flux error | Reduced chi-squared |
| --- | --- | ---: | ---: | ---: |
| 2026870667 | Free model ill-conditioned → beam-constrained | −82.42% | −1.97% | 356.02 |
| 2026870777 | Free model at a bound → beam-constrained | −56.70% | +141.47% | 145.74 |

Both have `status=measured`, a published Gaussian row, available position/flux
covariance and `deconvolution_status=unresolved`, despite clearly resolved
analytic truth. The native records and already-frozen matches establish these
errors; no finder was rerun and no match or gate was recomputed. The existing
catastrophic-outlier endpoint still passes overall (18/38,344), which cannot
waive a confirmed incorrect supported output.

Code inspection identifies a credible admission gap: rejection of an invalid
free Gaussian in `fitting._select_joint_candidates` can select a beam-shaped
alternative; `fitting._selected_fit_result` checks
convergence, numerical validity and identifiability, but these do not establish
model adequacy. The two alternatives are well-conditioned and away from their
own bounds. A condition-number-only repair would therefore miss them. This
explains their acceptance, not yet the initiating free-fit failure or all ten
missing detections. Treat this as a **serious Gaussian-output correctness
blocker**, with a narrow test-first repair recommended before development
closeout or an experimental release, rather than a reason to retune the whole
finder or repeat the campaign.

The human approved a bounded repair on 13 September, prioritizing truth-based
PyBDSF parity/improvement over optimizing against previous Hebog. V16 reuses
the existing direct/multiscale residual-adequacy rule for beam fallbacks from
invalid free fits, on the declared likelihood support and with per-component
attribution. Failed admission reports `fit-model-inadequate`; source support
and independent aperture photometry remain intact. Other components retain
the same joint parameters/covariance, not separately refitted substitutes.
Independent point/resolved, interior/edge/corner and invalid-pixel controls
reproduce the defect and preserve valid point models. Open-arc controls exposed
overly broad whole-parent rejection during development: retain the three valid
resolved components while explicitly omitting two inadequate beam fallbacks.
Their independent shape evidence still supports the source's arc association.
No chi-squared cutoff was selected from closed seeds. All 4,082 portable tests,
27 frozen equivalence checks and exact public Serial/Dask checks pass;
branch-aware coverage is 95.3141%, with every changed executable line and
instrumented branch covered. The exact notebook/identity tests also pass.
Candidate identities and full validation belong in the log; this is not a new
parity verdict. New Gaussian omissions require paired-screen review before
any further campaign.

Read-only inspection of the saved input/background/support planes narrows the
corner-miss diagnosis. At the local source peak, **all ten missing SNR-50
cases have positive estimated backgrounds between 0.00466 and 0.01769 Jy/beam**,
versus the injected mean of approximately −0.000230 Jy/beam. Four retain no
direct-detection pixels in the inspected corner at all. The bad-fit seed
2026870777 instead has background −0.01355 Jy/beam there; 2026870667 is close
to the true mean. Background corruption and fallback admission are thus
distinct issues; repairing Gaussian admission cannot restore lost detections.

The boundary interpolator supplied a concrete instability hypothesis: on a
512-square image the protected coarse mesh has 128-pixel windows and a
42-pixel step, but its final two centres are only **six pixels apart**.
Bilinear extrapolation from them to the image corner amplifies an independent
`0.0001` Jy/beam last-cell perturbation to `0.01341736` Jy/beam. This bounded
analytic conditioning check neither reruns the finder nor scores campaign
data. Subsequent read-only inspection isolates the actual saved excursions
more precisely: the **fine 35/7 mesh ends at centres 493 and 494**, only one
pixel apart. Extrapolating the four saved values at those centres reproduces
the corrupt background at `(510, 510)` in all twelve missing/bad-fit witnesses
to within `7e-18` Jy/beam. The final 17-by-17 block is bilinear to `3e-17`.
Thus excessive fine-grid boundary gain explains these saved excursions;
the coarse-grid instability was a related independent conditioning witness,
not proof that the coarse stage produced these particular values.

On 13 September, the release-clearance task independently reproduces this
numerical defect using coarse and fine synthetic grids, both perturbation
signs and all four corners. The v17 correction retains the existing windows
and interior interpolation, but computes edge secants over at least the
extrapolation distance. Endpoint-error gain is then at most two per axis
where that span is available; real affine backgrounds remain exact. Short
grids use their full span, singleton grids constant extension. Bounded subsets
carry the required anchors and agree exactly, including invalid pixels.
The same stable extension applies to extrapolated coarse RMS; the existing
fine-noise constant-edge policy is unchanged.

Four independent noisy, clipped-source scenes pass through the public finder
and caller-owned Dask with exact maps/masks/catalogues. All corner peaks retain
support, estimated background is within one noise RMS, and broad-source/noise
controls pass. An old-interpolator ablation also passes those four unperturbed
scenes: they are retention controls, **not** a reproduction of the closed
ten-source miss. The conditioned-grid failure is the independent numerical
reproduction. No recovered-source count or repaired campaign verdict is
claimed for closed data. As a diagnostic only, applying the independently
specified secant to saved fine-grid samples uses centres 472 and 494 instead
of 493 and 494. Its predicted peak backgrounds range from −0.000344 to
−0.000034 Jy/beam, within one injected RMS of the mean. This is a read-only
conditioning calculation, not new background estimation or a recovery verdict.
The numerical amplification defect is repaired; ordinary statistical error
in source-protected samples is not claimed eliminated. Full validation and
exact identities belong in `LOG.md`.

The earlier public Hydra figure-12 displacement belongs to v12, not v15.
Under the release-clearance request, a single bounded diagnostic refit uses
its verified saved 446 pixels, background, RMS and ownership unchanged. The
current fitter explicitly selects diagonal weighting because correlation
factorization fails. Its Gaussian centre is `(1780.21517, 1268.14008)`, **0.257
pixels** from the saved peak instead of 11.970; reduced chi-squared is 2.212
instead of 524,528.4. Independent oversampled/asymmetric/invalid-pixel fitting
controls already test that fallback mechanism. This closes the specific
displaced-Gaussian witness at the fitting boundary, not the entire 3,600-square
FK5 notebook input (outside the standalone public envelope), every position
failure, or scientific qualification. No detection, matcher, evaluator,
parameter tuning or rewrite of historical products was performed. The exact
diagnostic is retained in the ignored release-clearance evidence namespace.

The agreed
[severity policy](phase-5-v13-followup-review.md#later-decision-final-campaign-then-development-closeout)
blocks development closeout for serious operational/public-contract defects
or material loss of ordinary Rapthor-critical behaviour. Difficult faint
morphology and inconclusive comparisons can be deferred only with their
impact explained. Uncertain serious impact requires bounded triage and human
disposition. A confirmed incorrect supported output remains a release blocker.

Terminal handling and the bounded Gaussian/background correctness repairs are
complete; the historical displacement witness is resolved at the fitting
boundary. On **13 September 2026**, the human accepted the documented
uncertainty-calibration, measurement-tail and faint-association limitations
for the v17 experimental standalone release. The bounded release disposition is:

| Item | Disposition | Required follow-up |
| --- | --- | --- |
| Inadequate beam fallback after invalid free fit | Repaired; omit unsupported Gaussian measurements explicitly, retain independent source products. | Review omission/completeness effects in a paired development screen before any new scientific campaign. |
| Corner background amplification | Repaired by independent coarse/fine conditioning regressions and exact public execution controls. | Keep noisy/gradient/corner controls in non-regression; do not claim the closed misses have been rescored or recovered. |
| Historical displaced Gaussian | Specific saved-pixel fitting witness resolved; not a whole-image qualification. | Retain diagonal-weighting provenance and independent position controls. |
| Uncertainty calibration, unresolved-axis and extended centroid/flux tails, faint association | Human-accepted documented limitations for the v17 standalone experimental release. | Retain later repair/qualification tasks; no general parity, precision-uncertainty or Rapthor-deployment claim. Reopen if a confirmed incorrect supported output is identified. |
| Inconclusive completeness/mask comparisons | Remain inconclusive and prevent a general parity claim; the standalone release does not make that claim. | Resolve through candidate-bound qualification before promoting scientific readiness; no margin or confidence-rule change. |

M2 severity acceptance and the bounded E1 correctness inventory are complete
for this reviewed standalone scope. This is not an assertion that every
production use is safe, permission to ship a known incorrect supported output,
or blanket acceptance of future scientific changes. After merge/platform
checks, prioritize complete-path profiling and bounded scalability with these
limitations visible. The immutable v17 freeze retains its original bytes;
this later risk acceptance does not grant it execution or release authority.
There is no recommendation for another long campaign now. Scientific readiness
still needs candidate-bound parity/retention, fresh evidence and independent
acceptance; neither operational success nor favorable PyBDSF results qualifies
this candidate or authorizes release.

## Where the historical evidence lives

Earlier compact/continuum qualifications, public-data failures, source-aligned
sentinels and cumulative failures apply to their exact frozen candidates.
V14's terminal is a capture exception, not a scientific verdict. Failed or
underpowered decisions are never rescored, erased or transferred to a repaired
candidate; an old uncertainty exception is not inherited by v15.

Use the [execution log](https://github.com/gemmadanks/hebog/blob/main/LOG.md),
[immutable contracts](https://github.com/gemmadanks/hebog/tree/main/config/contracts)
and dated evidence reviews for exact decisions and reproduction identities.
The former chronological overview is available in
[Git history](https://github.com/gemmadanks/hebog/blob/0ce253cf26a7954a58dc9a211eb01d8502e69025/docs/reference/phase-5-campaign-overview.md).
Update this page by replacing current conclusions; append material history to
the log rather than adding competing “latest” sections here.
