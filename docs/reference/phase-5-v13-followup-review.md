# Phase 5 v13 quick-screen follow-up

## Status — 2026-09-11

**Diagnosis, bounded F1 repair, F3 tests, v14 candidate freeze and paired
confirmation complete. Resource and exact immutable execution admission
remain pending. F2 remains deferred.**
This follow-up finds
reproducible faint-source fragmentation and, separately, a pathological
Gaussian fit published in the user's completed notebook. It does not supply
a probability of campaign success or change any scientific gate.

The [paired screen](phase-5-v13-replay-preparation.md#paired-quick-screen-2026-09-11)
remains unchanged: 49 point-margin warnings are not 49 powered failures.
Retained diagnostics were read without changing matches or scores. New
diagnostic experiments use independent development seeds, checked against every
checked-in dataset manifest. No external finder, held-out qualification or
full replay ran. That diagnosis did not modify production science; the
subsequently approved initial F1 implementation is described below.

## Later decision — final campaign, then development closeout

**V14 confirmation:** candidate `cf6d9da` completes the frozen 24-input
screen and both Serial/existing-Dask comparisons. All 1,187 paired point
rows equal the earlier v13 screen, including 49 warnings; no powered parity
claim follows. The 2,400-input replay preparation is bound separately to
v14. The live disk reserve is not yet met, so no full replay is launched.

**Launch approval, 2026-09-11:** the user authorizes completing the necessary
repairs, then the isolated replay and process-bug retries, with disk space
available. A final independent boundary probe finds that the single-fit
`free-only`/beam-unavailable branch bypasses the existing identifiability
gate used by joint and beam-selected fits. Converged clipped-source ridges
are published despite a physical centroid bound or information condition
above the unchanged configured maximum. The bounded repair removes
that legacy bypass and uses the same publication gate for every selected
model. No new residual threshold or finder-specific flagging cut is adopted.
Three single-fit actual solves fail before implementation; the corresponding
joint controls already reject them. All twelve cases pass after also checking
`beam-or-free` with absent beam metadata. Centre-masked and
compact-on-diffuse controls increase the independent whole-model matrix from
seven to eleven cases. All 263 focused fitting/component/source tests pass.
Preserve support and explicit
unavailability rather than inventing an off-image Gaussian. The broader
residual/model-selection problem remains a documented approximation limit,
not permission to label every converged model physically exact.

**Latest amendment:** after reviewing the code and current evidence, the user
approved updating the plan and beginning F1 before replay. Reproduce the
numerical failure with independent bright/oversampled and modest noise/model
mismatch fixtures, retain good-fit and unavailable-fit controls, and preserve
detection/source support. Validate Serial/existing-Dask and non-regression,
freeze the corrected candidate, and perform a small paired confirmation
before exhaustive resource/execution admission. The unlaunched v13 identity
does not transfer to repaired code. Broader faint association improvements
remain deferred; the development-closeout severity policy below is unchanged.
The following paragraphs retain the earlier decision's context; references
to running unchanged v13 are superseded by this amendment.

**Initial F1 implementation:** independent 21-by-21 single/joint fit fixtures
exercise well-defined bright subpixel Gaussians with noiseless controls,
weak unresolved pixel-frequency perturbations and a one-percent asymmetric
envelope. They confirm that a declared covariance unresolved at float64
precision was still used as exact GLS. The bounded repair removes silent
diagonal jitter and checks a LAPACK reciprocal-condition estimate before
whitening. It retains explicit diagonal estimation and correlated sandwich
errors on numerical fallback. This is not a new residual acceptance cutoff
or proof that the viewed Hydra source is corrected. At that checkpoint,
broader Gaussian model adequacy, candidate freeze and campaign admission
remained open. See the
[numerical policy](compact-fitting.md#numerical-model).

**Whole-ellipse review follow-up:** independent analytic fits expose an
axis-order admission defect. A true 3:1 ellipse with a declared maximum ratio
of 2 is rejected from one initializer, but was accepted from a 90-degree
rotated initializer, in both single and joint fitting. The optimizer simply
exchanges its two axes. The corrected check requires both axes positive and
compares the larger with the smaller; it does not change the configured
limit, optimizer, selection statistic or detection policy. Five intended
test-first failures cover this bypass and non-positive first-axis values.

Twenty numerical admission cases now pass, along with seven independent
bright asymmetric, overlapping, masked and edge fits. The latter compare
centroids, amplitudes, integrated flux and every sampled model pixel against
separately parameterized Astropy Gaussian fits to the same original valid
pixels and varying RMS. Initializers come from positive analytic signal;
the fitted data retain signed perturbations. These are bounded fit controls,
not full-pipeline or PyBDSF comparisons. The asymmetric case checks agreement
on a best Gaussian approximation, **not** that all emission is Gaussian.
A separate public-composition control exercises an actual rejected ellipse
and verifies unchanged source flux and measurement support, no Gaussian row,
and a serializable `fit-invalid-result` disposition.

The bounded F1 review closes with consistent selected-model admission and
the controls above, not a new astrophysical residual rejection rule. Three
legacy edge expectations now require explicit invalid-fit disposition while
retaining their detailed bound diagnostics; separate beam-selected edge
controls retain independently fitted truncation positions and covariance.
The current composition advances to v14, without inheriting v13 evidence.

The remaining limitation is explicit: finite convergence and a
resolved covariance do not establish residual model adequacy. Existing
residual tests govern source grouping, not Gaussian-row publication. Do not
apply that parent-level grouping test indiscriminately to components: valid
compact emission can coexist with unmodelled diffuse emission. The bounded
review addresses numerically unresolved, physically bound and axis-invalid
solutions with independently tested unavailable dispositions. It does not
prove that every finite, identifiable Gaussian is a faithful physical source.
No screenshot-derived residual cutoff, peak substitution or viewed-data refit
is performed. F3 tests, candidate freeze and paired confirmation are now
complete; resource and exact execution admission remain pending. Replay
authority comes from the user's explicit launch approval, not fixture results.

A future broader model-adequacy review should assess whether a component's
reported amplitude,
centre and footprint are supported by its local original pixels, rather than
demanding that every parent residual be Gaussian noise. This is a proposed
direction, not an adopted cut. PyBDSF documents rejecting Gaussians with
implausible amplitudes, sizes or centres outside their island, while Aegean
documents explicit failed-fit and constrained-shape flags.
See the [PyBDSF flagging reference](https://pybdsf.readthedocs.io/en/latest/process_image.html#flagging-options)
and [Aegean catalogue flags](https://aegeantools.readthedocs.io/en/v2.3.4/includes/aegean.html).
These motivate local physical-consistency checks; neither their outputs nor
their parameter defaults become Hebog's truth or an automatically approved
threshold. Include overlapping components, invalid central pixels, real edge
truncation and compact-on-diffuse emission before adopting any rejection rule.

The user requests one final campaign, but does not want minor scientific
limitations to delay Phase 5 development closure and runtime/scalability work.
This supersedes this review's initial recommendation to repair every issue
before replay. It does not approve release, default cutover, changes to
scientific scoring, or a claim that visual inspection establishes parity.

Run the prepared v13 cumulative regression with its unchanged 2,400 inputs,
1,187 comparisons, safety checks, reference identities and confidence rules.
This is the last currently planned campaign, **not fresh held-out
qualification**. Preserve its exact terminal scientific verdict, including
failures and underpowered comparisons. Issue a separate human-readable
development closeout decision; do not rewrite machine readiness flags.

Before viewing that terminal, apply this severity policy:

| Finding | Development closeout treatment |
| --- | --- |
| Corrupt/missing products, silent incomplete processing, false success, non-finite or misregistered outputs, or Serial/Dask scientific disagreement | Serious; block closeout until diagnosed and resolved or the unusable path is explicitly removed from the proposed supported scope. |
| Confirmed material loss in Rapthor-critical behaviour: missed or spurious ordinary compact sources, unusable high-SNR measurements, or RMS/support errors that materially change filtering | Serious; block closeout. Use existing truth-based endpoint populations, practical margins and confidence evidence, not visual preference or newly selected tolerances. |
| Isolated difficult morphology, faint association ambiguity, uncertainty/tail differences, or an inconclusive comparison without demonstrated critical impact | Record the exact failure/uncertainty and defer improvement; not automatically a development-closeout blocker. These are not statistical passes. |
| Uncertain impact of a potentially serious finding | Perform bounded read-only triage and report the uncertainty for human disposition; do not silently downgrade it or start another science-repair campaign. |

Review **all** failed comparisons, not only pooled summaries. A failed
non-inferiority test does not automatically establish a serious regression,
but neither does an improvement elsewhere cancel a demonstrated loss.
The [Rapthor contract](rapthor-source-finding-contract.md) consumes catalogue
astrometry/photometry as well as masks and RMS; catalogue defects cannot be
assumed irrelevant. This campaign is a source-finder regression, not an
end-to-end `filter_skymodel` qualification or a 50% speedup demonstration.

The figure-12 Gaussian is a confirmed public-catalogue correctness concern.
Its frequency and downstream impact remain unresolved; a synthetic campaign
pass cannot erase this viewed witness. Known incorrect supported outputs
remain **release/cutover blockers**, even if the development phase closes
with the limitation explicitly carried forward. Retain the PyBDSF fallback.

After a complete campaign and severity review with no unresolved serious
issue, close Phase 5 **development** with documented exceptions and hand off
to profiling, complete-path runtime baselines and bounded scalability work.
Do not require all F1--F3 science improvements or another fresh campaign before
starting that engineering work. Scientific qualification/readiness stays
incomplete until its own gates pass; Release Please remains the release owner.

## Compact science and uncertainty

The eight compact screen inputs do not establish a universal astrometric
offset: their SNR-10 median position errors are worse than released PyBDSF
on four inputs and better on four. Existing uncertainty comparisons use
position and flux parameters, not the candidate's extra fitted-shape error
fields. A mismatch in available shape-uncertainty fields therefore does not
explain the incumbent uncertainty warnings.

An independent causal probe uses 64 seeds, SNR 10 and 25, a subpixel Gaussian
on a 21-by-21 image, known background/RMS and exact Gaussian-correlated noise.
It compares the configured owned-region likelihood with a bounded-context
control. All **256 fits complete with valid fit records**, in 2.36 s.
At SNR 10 the median position errors are 0.16029 and 0.15948 pixels,
respectively; at SNR 25 they are 0.06375 and 0.06399. Uncertainty coverage
does not improve consistently. **Do not promote a larger likelihood window
as a demonstrated fix.** This small, correctly specified noise model cannot
exclude noise-model mismatch or failures at different beam sampling.

The low-SNR position/flux/shape and uncertainty point warnings consequently
remain unresolved statistical risks, not proven evaluator defects and not
waived retention gates. Do not inflate errors, splice a different position
into a native Gaussian or select a favourable seed subset to clear them.

## Faint extended-source fragmentation

The prior 108-case joint development matrix exercises 36 geometries with
analytic, noisy and public-background variants, but its source amplitudes
are much brighter than these new faint witnesses. The follow-up uses four
independent analytic morphologies on 97-by-129 images: a modulated shell,
curved arc, filament and edge-clipped Gaussian. Each has amplitude 6 or 12,
one noiseless control and four correlated-noise seeds: **40 executions**
with supplied true background zero and RMS one. For the modulated shell,
the peak can reach 1.6 times the amplitude; amplitude 6 is not peak SNR 6.

All 40 executions complete in 5.94 s. Three noisy amplitude-6 cases divide
one injected object into two associated sources:

| Independent witness | Source grouping | Mechanism localized in retained diagnostics |
| --- | --- | --- |
| Shell, seed 951201 | Five components together, one separate | One lobe remains protected as an independent compact model |
| Shell, seed 951202 | Five components together, one separate | The same conservative per-component morphology decision |
| Edge-clipped Gaussian, seed 951202 | Three components divided into two sources | Noise-created peaks are not reconciled as one extended envelope |

The eight noiseless controls and all 16 noisy amplitude-12 cases remain
single-source. Ownership intersection with noiseless support is used only
to localize contributing rows; it is not a new campaign matcher or gate.
These are reproducible single-truth-object fragmentations, not a demand
that every low-SNR realization must be perfectly classified.

All three witnesses also reproduce through the **unchanged public FITS
path with estimated background/RMS**. Three Serial captures and three
caller-owned, two-worker Dask captures complete in 7.83 s. Every full
scientific digest agrees between Serial and Dask. Thus the fragmentation
is neither a notebook plotting issue nor an executor inconsistency, and
correct background/RMS alone does not eliminate it.

In `component_measurement.py`, resolved-loop/open-arc evidence tests fitted
shapes individually. An uncertain lobe can fail that test while the other
five pass, leaving it protected from residual grouping. The joint fitter
selects free versus beam-constrained shapes for the supplied peaks; it does
not compare the proposed peak count with a one-envelope explanation.
These protections also prevent the previously reported compact over-merges.
Removing them or merging every connected island would reintroduce known
errors. Repair requires competing morphological/model evidence with negative
controls, not an unconditional association rule.

Source fragmentation explains some large flux/centroid errors by assigning
only part of the emission to the matched source. It does not explain every
extended flux tail. Signed aperture noise, finite aperture extent and support
errors remain separate: even the noiseless faint filament loses about 5.65%
of total analytic flux in this diagnostic. Retained screen RMS estimates
also have modest negative mean bias, but no causal intervention establishes
that bias as the explanation of the master mask-precision warning. Do not
change photometric apertures or RMS policy solely to improve viewed results.

The screen's single `fit-invalid-result` is a different case: its diagnostics
retain centroid-bound contact, and an extended source is still measured.
There is no evidence that overriding that rejection would be a valid repair.

## Notebook figure 12: an incorrectly placed Gaussian, not a source centroid

The user's Hydra-deep example is traced to the completed **v12** notebook
refresh at `76e4a31`, source `838e2846...`, not a new v13 notebook run.
Its counts match the figure: 4,381 Gaussian components and 2,364 sources.
The input, result and consumed artefact checksums verify. The plotting path
loads `component_catalogue.json`, converts ICRS coordinates through Astropy
and draws circles; associated-source positions are separate crosses.

The suspect component is `component-detection-58345f52...`:

| Retained quantity | Value |
| --- | ---: |
| Plotted/native catalogue position, x/y pixels | 1783.31972 / 1256.50002 |
| Original background-subtracted peak in its owned region | 1780 / 1268 |
| Offset from that peak | 11.97 pixels, approximately 1.33 beam FWHM |
| Detection-region centroid, x/y pixels | 1780.39234 / 1268.25171 |
| Local peak significance using saved RMS | 207.65 |
| Fit reduced chi-squared | 524,528.40 |
| Fitted model fraction sampled in its region | 0.3781 |
| Relative distance from lower centroid-y bound | 8.12e-7 |

The peak is not treated as a known true subpixel position, and PyBDSF is not
used as truth. Nevertheless, this displacement, distorted model and enormous
residual statistic are strong evidence of a pathological measurement, not
the legitimate centre of an associated multi-component source.

**Confirmed acceptance gap:** the fit is recorded as converged, finite and
measured. The bound-contact tolerance is 1e-10, so the near-bound solution
does not receive a bound flag. Its information condition number, 2.88e6,
is below the configured 1e8 ceiling. Residual model adequacy affects source
grouping later, but does not retract this published Gaussian measurement.
A converged optimizer and finite covariance are insufficient evidence that
the Gaussian is a scientifically useful representation.

**Numerical hypothesis, not yet an independent reproduction:** this fit uses
446 correlated-GLS samples. Reconstructing the declared beam-noise matrix
on the saved owner yields an eigenvalue range of roughly -4.0e-15 to 73.49
and requires the existing factorization-jitter path. That suggests extreme
sensitivity to small departures from the ideal Gaussian noise/model
assumption. This is a read-only matrix reconstruction, not the original
factorization trace and not proof that GLS alone caused the displacement.
The fitter, component-measurement and astrometry files are byte-identical
between this notebook revision and v13. The later zero-noise repair does not
change their acceptance logic; it is not evidence that this problem is fixed.

## Deferred repair and confirmation sequence

These are tracked scientific follow-ups, not prerequisites to the final v13
campaign under the later user decision. Reopen them for a serious finding or
before claiming corrected public-catalogue behaviour and scientific readiness.

1. **Gaussian validity first.** Add independent bright, oversampled,
   mildly non-Gaussian and covariance-mismatch fixtures alongside exact
   correlated-noise controls. Exercise near-bound but nominally converged
   solutions, unphysical/sub-beam distortions and model residuals. Diagnose
   numerical conditioning separately from morphology; reuse the bounded
   fitter and its explicit fallback/disposition machinery. A proposed
   covariance fallback or residual-adequacy rule needs predeclared synthetic
   normal/boundary/failure checks. Preserve the detection and source support
   when a Gaussian is unavailable. Never just move its circle to the peak,
   censor the detection, or choose a chi-squared cutoff from this screenshot.
2. **Faint topology next.** Extend the joint geometry matrix into the faint
   regime. Test a single shell/arc/filament/clipped envelope jointly with
   independent compact pairs, polygons, chains and compact companions on
   extended emission. Assess bounded one-envelope versus multiple-object
   evidence while preserving component identities and explicit ambiguity.
   The loop's aggregate evidence must not absorb an unrelated compact lobe.
3. **Retain all science, then freeze.** Check source and component positions,
   membership, flux, shape, uncertainty, completeness/reliability, masks and
   explicit unavailable/deferred counts. Run Serial/existing-Dask and
   partition/order/retry controls, focused and broad non-regression,
   branch/patch coverage, equivalence, docs and clean hooks. Reassess compact
   uncertainty and extended mask/flux warnings using result-neutral paired
   evidence only after a corrected candidate is frozen. Keep all comparators,
   truth, margins, confidence rules and the 2,400-input population unchanged.

These implementation tasks are **not completed by this review**. Any future
science repair needs a new candidate and validation before its own execution
freeze. The authorized final v13 run may proceed unchanged after its existing
resource and exhaustive immutable admission; preserve the closed screen.

## Evidence and validation

Independent follow-up audit SHA-256:
`a737add821c6f2ea582122a0047b7ce644ade5541445949e01b697674bcc132d`.
All 134 audited files are copied byte-for-byte to the ignored
`benchmark-results/phase-5/v13-followup-20260911/` namespace. It binds the
v13 source, unchanged test helpers/resources, all 68 development seeds,
checked-in manifest disjointness, programmes, plans and complete outcomes.
The original evidence remains in `/private/tmp/hebog-v13-followup.s9IQlk/`.

Figure-12 trace SHA-256:
`c9b1c2b082b6e73b55c4e93148b56da089d1c0a4d115bda955efdaad69bc0673`.
It is retained separately under
`benchmark-results/phase-5/v13-followup-figure12-20260911/` because viewed
notebook diagnostics are not independent synthetic or qualification evidence.
No viewed image was rerun or fitted and no closed score was recomputed.

The independent harness had three setup/summary errors before its complete
runs (a moment pixel-count mismatch and two incorrect diagnostic attributes).
The read-only screenshot tracer needed a correction for singleton leading
FITS axes. Failed script versions remain preserved. These are diagnostic
harness errors, not finder process failures. An interrupted public-probe
approval left no process or output namespace; the later complete run is
separately recorded. All successful-run census and digest checks pass.

Focused existing tests pass **210 tests**, with four slow tests deselected,
in 42.84 s, including the actual existing-Dask capture boundary. No production
code, scientific rule or permanent fixture expectation changed. Full coverage,
full equivalence, alternate Python versions and a fresh parity campaign are
not rerun for this diagnostic/documentation-only change. Passing process
tests cannot override the scientific findings above.
