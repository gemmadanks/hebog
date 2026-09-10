# Phase 5 public-catalogue repair contract

Date: 2026-09-09; fixture validation updated 2026-09-10.
Status: **development repairs validated; replay not admitted**.

The user requested completion of R6-C0--C7 and preparation of the next
replay after reviewing the conservative compact-source recommendation.
This authorizes implementation and synthetic validation of that plan, not
execution of a new campaign or conversion of a closed failure into a pass.
New scientific choices outside these recommendations require renewed review.

## Witness index and boundaries

The user's diagnostic refresh is
`390efa7-cc1db52e4e30-4f8f357a`, labelled `Repaired estimators`.
Its source is `cc1db52e4e3088794b8d5c4f41b9301daedb848bcd5a282a3b6b381b585a7715`,
configuration `5eca0efc1995f206900506c87f2ca3cba6aa4a2f1a5155bc3e58863bf3cb75c4`.
The request record SHA-256 is
`ff78add743ebd364b8328acc4e81d21994395d1ab360341332a0774179e157b4`;
the sealed campaign record SHA-256 is
`7106495713decb8a3ef07dfd3e1ec1bf2fecaf483f6ac1039b598e502f574ab9`.
Products remain under the ignored public-notebook refresh namespace.
The request explicitly authorizes no scientific claims. Its recorded dirty
checkout is not an immutable execution candidate; the source digest, not
its checkout's abbreviated revision alone, identifies these diagnostics.

The following is an index of previously inspected native dispositions,
not new matching, scores, a population census or truth labels. Coordinates
are notebook core pixels; native full-input coordinates include the crop
offset and must be transformed using the declared celestial frame.

| Case / witness | Native identity / location | Question or confirmed defect |
| --- | --- | --- |
| Hydra disconnected remainder | Source `source-associated-a5e1f35bb8a777c36c98b3297ceb79a7342ac58d7c0bdd50ea8f943146d3d6cf`, near (2315.15, 1524.27) | Five components on five patches remain one hierarchy source. Membership needs positive evidence; moving the centroid is not a repair. |
| Hydra extended override | Source `source-associated-720e343450e277908e5cca218c0cd1e9c9fce81d33a52dbc60811b9eda0ea150`, near (1539.66, 1558.64) | Three components on three patches; trace the extended override and protect independent compact neighbours. |
| Hydra transitive grouping | Source `source-associated-0d2d75a8d8272796e766ec88cd0de2ab331ab4f38f704b8a35752948dda21b02`, near (1113.87, 1667.61) | Seven components on six patches, including off-view members; trace every accepted merge and protection override. |
| SDC1 ordinary mixed publication | Source `source-associated-0f50bd502f6a20b47b0453cff6aab69cd7f94b7e4d80050629e2e9069f33a3ef`, near (1331.65, 1795.92) | An unpublished neighbour contributes to an associated-source position. Association and declared contributing population need separate tests. |
| Hydra joint-fit ridge | Component `component-detection-3e18efae95438ae6e9b676755da44a5d0f5b372f57e4058323ee51040b7a9802`, label 2250 | Fitted centre near (983.90, 1910.50) versus owned peak (986, 1903); relative bound distance about 6.6e-11 but no bound flag. Joint uncertainties are unavailable. The physical cause of the displaced optimum is not established by a screenshot. |
| SDC1 HDR work limit | Source hierarchy `source-associated-c6c2bf9d7f6a0bcc3d3bad17bc63c54153a70bf442f981ac1ecd5147340e908c` | A 101-component parent requires 606 parameters, exceeding the 96-parameter limit. Separate computational fit work from morphological association without raising the limit. |
| SDC1 HDR bright body | Core pixel (1730, 340), plus broad-emission neighbourhood | Saved positive emission is suppressed by background/RMS estimation and support admission. Reference RMS is also elevated; source contamination versus valid noise inflation remains an attribution question. |

These images are viewed diagnostic evidence. Do not fit or tune these pixels,
rescore their closed results, use their seeds for qualification or treat
PyBDSF/Aegean group IDs as astrophysical truth.

## Prespecified repair rules

1. Final source grouping needs explicit observable evidence. A reconciliation
   hierarchy, absent fit, failed fit or computational batch is not a source
   identity. Unconstrained compact neighbours remain separate. Explicit
   compact-overlap or resolved-morphology groups remain available, with
   independent negative controls and bounded provenance for merges/overrides.
   Do not force every Gaussian into a separate source or snap source centroids
   to peaks. Arcs, shells, lobes and core-halo structures remain binding guards.
2. Fit work must follow bounded model-interaction context, not an arbitrary
   large source hierarchy. Preserve neighbour models wherever they influence
   the retained likelihood and preserve joint uncertainty. Existing context,
   parameter, Jacobian and memory bounds stay in force. Inseparable work that
   cannot be admitted remains explicitly deferred, never silently successful.
3. Enforce the existing numerical identifiability rule consistently. Bound
   contact must be dimensionless and translation/unit invariant, using the
   existing 1e-10 proximity scale relative to the admitted interval. Numerical
   rank and covariance must be computed in equilibrated parameter coordinates
   and transformed back to physical units. A singular joint model cannot
   borrow identifiability from its individual component blocks. Preserve the
   existing circular-coordinate recovery before declaring joint information
   unavailable. Do not change the likelihood, detection threshold, extension
   significance, BIC rule or fit-quality cutoff to repair these numerical bugs.
4. Catalogue membership and disposition are explicit. All contributing
   component IDs, measurement domains and unavailable/deferred reasons must
   survive public records and round-trips. Faint measurement-only wings are
   not invalid merely because they are absent from a display mask. A failed
   native fit must not erase its detected owner or fabricate valid Gaussian
   parameters. Source measurement availability is distinct from Gaussian fit
   availability and from processing completeness.
5. Attribute the bright-body case on independently specified broad emission,
   cores and spatially varying/correlated noise. Change background/support
   only for a reproduced defect with joint compact/extended retention.
   Neither forcing zero background nor matching a viewed reference mask is
   permitted. A legitimate detection limit must be documented, not renamed
   a successful recovery.
   On 2026-09-09 the user additionally approved the small-image RMS-policy
   repair after the independent high-noise control failed. The prospective
   public policy first tested the unchanged 150-pixel mesh instead of a
   constant map: this improved but did not pass the independently declared
   noise-patch control (estimated RMS 1.81 versus truth 4; required >2).
   The next development hypothesis uses the existing image-relative fraction
   as a mesh-size cap for images that can contain a configured coarse window:
   shrink the window/stride together to at most a quarter of the limiting
   dimension, without enlarging either. Images smaller than one configured
   window retain the bounded constant fallback; images at least 600 pixels
   retain the existing 150/50 mesh. Clipping and source-protected adaptive
   estimation are unchanged. Test both sides of these transitions as well as
   the noise/halo controls before admission. This is analytic development,
   not selection on the notebook pixels or closed campaign outcomes. Failure
   of any binding noise or source-retention guard blocks replay preparation.
   The expanded mesh-only ladder failed two broad-halo controls at height
   150 (background bias 0.559/0.561 RMS, limit <0.5). The user then approved
   source-protected coarse estimation before replay. For the intermediate
   images previously admitted to a bounded constant-map read, use the existing
   connected/multiscale protection before fine-grid refinement. Coarse windows
   exclude protected samples, retaining their uncontaminated samples; fine
   windows retain the existing whole-window exclusion. The source guard uses
   the established fine-estimator footprint, not the larger coarse mesh.
   Coarse protection includes ordinary 5/3-seeded emission (minimum seven
   pixels) and existing persistent-scale support, not only 75-sigma adaptive
   candidates. To avoid calling genuine local noise excursions source support,
   use an unmasked pilot at the existing fine-noise resolution for mask
   admission. The pilot is not a published noise map and does not change
   the bright-candidate trigger. Empty protection stays empty; an unavailable
   pilot must not fabricate finite noise or measurements.
   Keep the existing one-million-pixel admission bound;
   this must not introduce a full-plane read for larger spatial-grid images.
   An absence of available unprotected estimator cells remains explicitly unavailable,
   not fall back to a known source-contaminated coarse estimate. Retest noisy
   neighbours, broad halos and the complete previous geometry ladder.
6. Plots identify native catalogue types, proxy masks, member links and
   measured/published/deferred/failed states. Display changes cannot change
   positions, membership, thresholds or scientific scores.

Numerical reuse remains NumPy/SciPy rather than another solver or dependency.
For Jacobian column norms D, compute information in coordinates J D^-1 and
transform its covariance by D^-1 on both sides. This is algebraic
equilibration of the same model, not additional noise or regularization.
[SciPy's least-squares contract](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html)
separates bounded numerical convergence from physical interpretation; solver
success alone is not evidence that a mixture is identifiable.

The RMS policy follows the mesh-size trade-off documented by
[Photutils](https://photutils.readthedocs.io/en/stable/user_guide/background.html):
windows must sample background without smoothing away its spatial variation
or absorbing source emission. This change reuses the existing estimator;
it introduces neither a new dependency nor a claim that every noise field is
resolved by the fixed mesh.

## Acceptance and replay preparation

Every changed branch needs a red-before-fix test and normal, boundary and
failure guards. Use independently constructed pixel scenes and deterministic
fault injection, not campaign-directory dependencies in ordinary tests.
Vary compact separation/SNR/flux ratio, shared context, unit scale, translation,
beam, frame/orientation, masks and corners; retain all extended-source guards.
Source-level false merges and false splits both matter, even with unchanged
Gaussian counts. Require the complete 108-case development matrix, exact
public Serial/existing-Dask and partition/order/retry conformance, branch and
patch coverage, existing equivalence and all engineering/documentation gates.

After those pass, freeze new non-executable source/composition/runner identities
and verify actual notebook review selection. Then complete reuse-aware replay
orchestration using the unchanged scientific evaluator and comparator records,
verify its late terminal path on fixtures, measure cost and disk admission,
and freeze/exhaustively verify the immutable replay preflight. The full 2,400
candidate cases, 1,187 comparisons, five safety checks and original confidence
rules remain required. Recheck comparator reuse against the final transitive
closure; no old candidate verdict transfers. The user's final campaign time
budget remains below 12 hours and must not be claimed without evidence.

No campaign starts from this contract. A confirmed correctness regression,
unresolved scientific-policy change or insufficient resource admission blocks
the next executable freeze. Rapthor priority is not permission to release
known incorrect supported public products.

## Boundary audit and local-noise repair

The implemented coarse protection and unmasked pilot pass the complete
108-case development matrix and the original 16 halo/noise controls together.
The four exact public Serial/existing-Dask normal/fault comparisons also pass.
These are independent fixture results, not campaign parity.

The original height-599/600 controls had width 512. They exercise intermediate
meshes but not the actual limiting-dimension transition. The additional
599x640 and 600x640 controls expose four noise failures: estimated RMS
1.71--1.73 versus truth 4 and the unchanged >2 guard. Background accuracy and
extended-support guards still pass. Keep all original cases and these eight
new cases, including both halo widths and noise-free controls.

The configured coarse mesh averages over the localized noise patch; the
75-sigma bright-source refinement and its 75-pixel influence radius do not
admit that independent patch. The unmasked fine pilot affects source-mask
admission only and cannot correct the published noise there. This is an
estimation-policy gap, not a plotting error or evidence for changing source
thresholds. In particular, the 600x640 case uses the existing 150/50 coarse
mesh, so the defect is not confined to the new intermediate-image policy.

Before further implementation, review source-protected local-noise refinement
independent of bright-source admission, with separate background/RMS domains,
noise-only and compact/extended controls at several spatial scales, explicit
unavailability and bounded/tiled execution. Do not unconditionally publish
the unprotected pilot or use an uncalibrated maximum to clear this test.
The user authorized this additional review and test-first repair on 2026-09-10.
The failures below are retained development history. The authorized repair
must clear them jointly before C5/C7 and the candidate freeze can complete.

### C5a fixture-validated development policy (2026-09-10)

Separate noise resolution from the bright-source background refinement. For
spatially admitted continuum images, estimate RMS on the existing global
35/7 fine lattice even without a 75-sigma source. Retain the coarse/protected
background and existing bright-region background blend. Do not select the
maximum of two noise estimates or publish the unmasked pilot. Use that pilot
only to admit ordinary and persistent-scale source protection. Reject whole
fine estimator windows overlapping guarded source support; interpolate the
remaining statistics with the existing nearest-cell/linear-grid policy.
Fine RMS uses constant edge extension outside the estimator-centre domain:
linear extrapolation of stochastic slopes can invent zero noise even though
all measured cells are positive. Background interpolation remains unchanged.
If no clean cells exist, noise is unavailable, not replaced by a contaminated
coarse value. Invalid coverage remains invalid.

Noise protection is a bounded estimation context, not catalogue association.
Use globally anchored blocks of at most 256 fine cells, independent of output
tiles and executor batching. Extend each read by the filter footprint, source
guard and configured coarse-window span. Threshold support touching an
internal context boundary is conservatively protected: a truncated seed
search must not admit source pixels into noise statistics. Actual observed
image edges are not truncated work boundaries; ordinary source admission
still applies there. Assemble raw cell statistics
before any missing-cell filling; never fill independently per work block.
This supplies bounded work rather than a full-image mask or a task per window.
The block/context policy is part of the candidate identity, not a scheduler
choice. Validate noise-only patches at multiple widths/correlation scales,
smooth gradients, source/blank controls, unavailable coverage, boundary
translations and Serial/existing-Dask/retry conformance. Keep all 24 existing
halo controls and all 108 geometry cells unchanged. A failed guard rejects
this development policy; it does not authorize adjusting the guard.

The new noise-only trigger test first failed at RMS 1.2237 versus truth 4.
The bounded protected-noise implementation then passed all 20 independent
noise controls and all 24 unchanged halo controls. A warning audit exposed
zero edge RMS from linear extrapolation; a new strict-positive noise test
reproduced that failure before the edge-extension repair. The combined
48-test rerun (44 controls plus four exact public Serial/existing-Dask normal
and fault cases) passes without that warning. A separate injected patch
also reproduced a coarse >75-sigma work anchor falling below the island
threshold under the fine pilot. Such an anchor no longer forces a source-mask
seed: independent pilot admission owns the mask while the bright work list
is unchanged. All 78 focused availability, boundary, source-protection and
RMS-kernel tests pass. Whole-suite coverage, final geometry confirmation,
engineering checks and review are still required before admission.

The additional 18 corner-noise controls exposed an image-edge distinction:
an unseeded noise excursion was being protected merely because it touched
the observed edge (RMS 1.6723 versus truth 4, required >2). Restricting the
truncated-seed rule to internal work boundaries passes all 18 corner cases
and 79 focused kernel tests. The complete noise ladder now has 38 cases,
including the original 20. The compact-only profile retains its prior
background/RMS policy; a separate public-boundary regression rejects
accidental inheritance of the continuum mesh without its source protection.

The final combined integration ladder passes 203 tests: 38 independent noise
controls, 24 bright-halo controls, the unchanged 108 geometry cells, six
background Serial/existing-Dask cases and 27 public-API cases (including four
exact public normal/fault comparisons). The final compact-policy regression
and existing compact-profile test also pass. All 79 focused RMS/protection
tests pass. These establish the bounded repair behaviour on independent
fixtures, not a renewed verdict on the viewed notebook or any closed campaign.

Final stable-source portable coverage passes 3,697 tests, with 157 deselected
and two expected failures. A 49-test supplement covers the final malformed
blend-request guards and read-only notebook preflight. Combined branch-aware
coverage is 95.2377727%, above the 95.1905998% baseline, with 221/221 changed
executable lines and all changed branches covered. The 27 frozen equivalence
tests, strict documentation and Marimo checks, Pyright and isolated wheel
smoke also pass. Only Python 3.14 was executed locally; the supported 3.12/3.13
matrix and production-scale runtime remain unverified by this local run.

This diagnosis is consistent with the documented mesh trade-off, not evidence
that another finder supplies truth. [PyBDSF's processing documentation](https://pybdsf.readthedocs.io/en/latest/process_image.html#rms-box)
warns that large boxes smooth away local noise while small boxes can absorb
source emission. Its [worked examples](https://pybdsf.readthedocs.io/en/latest/examples.html)
illustrate both oversmoothed artefact regions and extended-source bias.
[Photutils Background2D](https://photutils.readthedocs.io/en/stable/api/photutils.background.Background2D.html)
supports excluding source samples and interpolating estimates into masked
regions, while distinguishing missing coverage. These support reviewing
source-protected spatial estimation; they do not prescribe a universally
valid box size, authorize a new policy or justify copying a reference's code.
