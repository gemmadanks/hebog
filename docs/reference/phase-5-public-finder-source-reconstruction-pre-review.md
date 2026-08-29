# Phase 5 public-finder source-reconstruction pre-review

**Status:** ready for named scientific and engineering approval of
fixture-only implementation. This review is non-executable. It does not
authorize implementation, a cumulative replay, viewed SDC1 or Hydra
execution, a campaign, fresh qualification, threshold or photometric tuning,
rescoring, optimization, cutover, or release.

## Recommendation

Replace the failed pairwise source-association layer with a deterministic
multiscale source hierarchy, measure every resulting catalogue source once,
admit reconstructed mask support only through a connected path to an accepted
seed, and prospectively score catalogue topology at the catalogue-source
layer. Keep the immutable detection components as diagnostic evidence.

These are four related corrections, not a change to the detection threshold:

1. group components through an explicit common undilated multiscale parent,
   not through straight centroid chords and complete-link pair tests;
2. measure one source on one disjoint source-owned aperture, rather than
   summing independently measured components;
3. require reconstructed support to be connected to an accepted source seed,
   while retaining the existing radius and thresholds; and
4. make source-union split and merge the binding catalogue topology, while
   retaining native-component split and merge as non-binding diagnostics.

The machine-readable review is
`config/contracts/phase-5-public-finder-source-reconstruction-pre-review.json`,
SHA-256
`528f18a661bb2391018c458a29aace2757762e58107650e6ae01d05adc85347f`.

## Evidence boundary

The review is bound to terminal ledger
`benchmark-results/phase-5/cumulative-regression-ledger-public-finder-source-association-measurement-repair.json`,
SHA-256
`6b2aa4deb306e0d7ba8285aae1e18bfb4f4e838b57aecd0497bec990e8a8c842`.
That immutable record binds:

- candidate `6184a32648eee637f0aca03ab2ec0249bd0510f0`;
- source tree
  `517d56e19a5d58eb386d96bdb181d36afb574ad018222f870cc8434c398044ff`;
- configuration
  `78dbb230cbb726cbbe02b74f2e7fe96bc42801e2102bf15f0580c0643befe946`;
- preserved candidate product set
  `dbc317fa98638d96ebecac26d98014a953defc96ed48a741f42f48954daa48ab`;
- reconstructed references `48209eae...`; and
- closed baseline `a45303df...`.

The completion process did not execute the candidate. It compiled and
evaluated the already verified 2,400 products exactly once. Compact passed
with zero like-semantics regressions. Continuum recorded 89 passing, 44
failing, and 10 underpowered endpoints, including 37 like-semantics
regressions. The result is terminal and may not be overwritten or rescored.

## Complete failure census

All 44 failures are accounted for below. The counts are disjoint.

| Workstream | Failures | Principal observation | Required correction |
| --- | ---: | --- | --- |
| Reliability | 1 | 0.62375 against a 0.95 floor, despite completeness 1.0 | Reduce inflated catalogue cardinality by reconstructing real image-domain sources. |
| Duplicate and split topology | 18 | Overall duplicate and split are both 0.25295; shell is 1.0 and tile boundary is 0.5 | Replace under-association and prospectively separate source topology from component diagnostics. |
| Integrated flux | 11 | Shell median error is 0.76457; overall p95 is 0.79260 | Measure the source once on unique source-owned pixels. |
| Astrometry | 13 | Overall position p95 is 4.18028 beams; shell is 5.08070 beams | Associate the complete source and compute one source-level moment. |
| Mask precision | 1 | Absolute precision 0.88406 passes 0.85, but paired UCLs 0.06944 and 0.07689 exceed the 0.05 margin | Exclude disconnected reconstructed support without changing thresholds. |

### Reliability

The single reliability failure is
`continuum--reliability--overall`. Hebog is better than both PyBDSF references
on this endpoint, but 0.62375 remains far below the truth-based 0.95 absolute
gate. Completeness is 1.0, so the dominant problem is not missing the governed
truth population. The catalogue contains too many rows for the number of
unique matched sources.

This is consistent with the topology evidence: several detection components
that belong to one image-domain source survive as separate catalogue sources.
Grouping them correctly reduces the denominator without weakening detection.

### Duplicate and split topology

Nine duplicate and nine split endpoints fail in the same strata:

- overall;
- above the compact-deblend limit;
- artifact morphology;
- shell morphology;
- scale 1 beam;
- scale 4 beam;
- tile boundary;
- tile corner; and
- varying noise.

The duplicate and split values are numerically identical in every stratum:
0.25295 overall, 1.0 for the shell, 0.74188 for the artifact, 0.375 at one
beam, 0.20575 at four beams, 0.5 at a tile boundary, and 0.17146 under varying
noise. The shell is also the above-deblend and tile-corner truth group, which
explains the repeated 1.0 failures rather than three independent numerical
defects.

Two causes overlap:

1. The implementation requires a bright *straight line* between component
   centroids, separation within half the summed directional FWHM, and a valid
   edge for every pair in a complete-link group. A ring, curved filament, or
   multiply peaked source can have continuous image-domain support without a
   bright centroid chord or all-pairs proximity. The rule therefore rejects
   real common-source structure by construction.
2. The temporary evaluation adapter uses source-union labels for catalogue
   matching but still computes split fraction from native component labels.
   Native fragmentation is useful diagnostic evidence, but it cannot become
   zero when association deliberately preserves every component. Those nine
   split endpoints could not demonstrate the intended catalogue behaviour
   under the approved metric definition.

The second issue does not explain the duplicate failures: duplicate fraction
already uses catalogue-source rows. Their failure shows that the association
algorithm itself was ineffective on the binding cases.

### Integrated flux

Four median and seven p95 endpoints fail.

Median failures:

- above the compact-deblend limit: 0.76457;
- shell: 0.76457;
- tile boundary: 0.45697; and
- tile corner: 0.76457.

P95 failures:

- overall: 0.79260;
- above the compact-deblend limit: 0.84683;
- shell: 0.84683;
- scale 4 beam: 0.79969;
- tile boundary: 0.82736;
- tile corner: 0.84683; and
- varying noise: 0.79260.

The current associated-source row sums the integrated fluxes already measured
for its components. Those component values come from independently expanded
component apertures. This has two failure paths:

- when association fails, matching observes only one incomplete fragment of
  the truth source; and
- when association succeeds, summing component measurements is not equivalent
  to measuring the source once, because component apertures were constructed
  before source membership and are not the binding source-owned measurement
  domain.

The correction must map component owners to a source label first, construct
one nearest-source aperture, and sum each background-subtracted pixel at most
once:

\[
F_s = \frac{1}{A_{\rm beam}}
      \sum_{p\in A_s} (I_p-B_p),
\qquad
A_s\cap A_t=\varnothing\quad(s\ne t).
\]

Here \(A_s\) is the exact member-owner union plus one uniquely owned source
aperture. Component photometry remains available as a diagnostic. The
existing source-level positive-support fallback remains explicit and flagged;
it must run once per source, not once per component.

### Astrometry

Seven position-p95 endpoints fail: overall, above the compact-deblend limit,
shell, scale 4 beam, tile boundary, tile corner, and varying noise. Overall
p95 is 4.18028 beams and shell p95 is 5.08070 beams, versus a 0.5-beam limit.

Six mean-offset endpoints also fail for the shell-equivalent strata. Their
point estimates are not evidence of a large global bias: shell x and y points
are 0.07974 and 0.00685 beams. They fail because their one-sided decision
bounds are 0.18458 and 0.12887 beams, above 0.1. This combination—small mean,
very large p95, and wide bounds—is a tail and dispersion problem, not a
coordinate-frame offset.

Under-association leaves a fragment centroid on a shell rim or one side of a
boundary-crossing source. The associated row then averages component
positions using component integrated flux. The correction should instead
compute one positive denoised first moment on the complete source-owned
support:

\[
\boldsymbol{x}_s=
\frac{\sum_{p\in S_s} w_p\boldsymbol{x}_p}
     {\sum_{p\in S_s} w_p},
\qquad
w_p=\max(D_p,0),
\]

where \(S_s\) is the source support and \(D_p\) is the already reviewed
denoised position signal. This targets the tail without applying an empirical
coordinate correction.

### Mask precision

Mask recall is 0.91965 and the 0.90 absolute gate passes. Mask precision is
0.88406 and passes its 0.85 absolute floor, but it is non-inferior to neither
PyBDSF reference: the released and pinned-master UCLs are 0.06944 and 0.07689
against a 0.05 margin.

Source association cannot change this mask because association only remaps
catalogue and label identities. The current support assignment admits a
significant reconstructed pixel when it is within the fixed recovery radius
of the nearest seed; it does not require a connected significant-support path
to that seed. The strongest prospective explanation is therefore isolated
nearby reconstructed support entering the retained mask.

This cause has **moderate**, not definitive, confidence: the terminal ledger
retains aggregate statistics rather than the per-pixel causal products. The
implementation may proceed only if analytic fixtures reproduce the
disconnected-support false positive. The fix is topological—require the same
valid eight-connected component in the union of direct seeds and significant
support inside the existing recovery radius—not a new numeric threshold.

## Causes excluded as primary explanations

- **Gross sensitivity loss:** all completeness endpoints pass and overall
  completeness is 1.0.
- **Candidate overmerge:** all merge endpoints pass. False association remains
  a critical negative-control risk for the replacement hierarchy, but it does
  not explain this ledger.
- **Global astrometric bias:** mean x/y point estimates are small; the failures
  arise from dispersion and extreme fragment positions.
- **Power:** 43 endpoints fail absolute gates, mask precision fails both paired
  gates, and 37 like-semantics regressions remain. Ten underpowered endpoints
  cannot compensate for those failures.

## Proposed source hierarchy

Detection components and their owner pixels remain bitwise unchanged. At each
already reviewed significant à trous reconstruction scale, retain exact
eight-connected *undilated* feature identities. Link overlapping features at
adjacent scales to form a bounded component tree. Attach every direct owner to
the finest feature it intersects. Owners form one catalogue source only when
they share one unambiguous common parent feature.

This should reuse Hebog's existing `ScaleDetectionPlane` and
`associate_adjacent_scale_detections()` kernel in
`hebog.algorithms.multiscale_association`. That code already joins exact
supports only by overlap at adjacent scales and has bounded, deterministic
identity records. The implementation should adapt those records to direct
component ownership; it should not create a parallel graph framework or reuse
the later half-beam compact-context dilation.

The aggregate parent currently computed by `source_association.py` is not
enough: it is only a prerequisite for a pair edge, after which the straight
chord, directional-FWHM, and complete-link tests still apply. Conversely,
grouping that aggregate connected component directly would repeat the
bridge-driven overmerge risk that the pairwise implementation was intended to
avoid. Per-scale exact identities preserve the scale lineage needed to
distinguish a common parent from a coincidental aggregate bridge.

This differs from both failed approaches:

- it does not recreate the historical three-beam dilation that bridged deep
  Hydra fields; and
- it does not require a straight centroid chord, pairwise FWHM proximity, or
  a complete-link edge between every pair.

Paths follow the significant support itself, so a shell may connect around
its ring and a curved filament along its emission. A transitive chain without
one explicit common parent remains separate. Ambiguous parents fail closed and
are flagged. The rule introduces no new numerical threshold and may not use
truth identities, terminal products, viewed public outcomes, or reference
finder products.

## Prospective evaluation semantics

Future evidence must expose two topologies explicitly:

| Topology | Role |
| --- | --- |
| Catalogue-source union | Binding completeness, reliability, duplicate, split, merge, flux, and position. |
| Native detection component | Diagnostic fragmentation and ownership; never hidden or relabelled. |

This is a prospective protocol correction for a future candidate. It does not
change, reinterpret, or rescore ledger `6b2aa4de...`.

## Test-first acceptance matrix

Implementation may begin only after approval of this exact review. Tests must
precede production behaviour.

Association fixtures must include:

- a single compact source;
- a multi-peak shell at image centre, tile boundary, and tile corner;
- the three-lobe artifact group;
- curved and straight filaments;
- scale-one and scale-four emission;
- a varying-noise source;
- two independent nearby sources with a faint bridge;
- a deep crowded many-seed field;
- an invalid-pixel and masked-gap barrier; and
- a transitive three-component chain with and without one common parent.

Measurement fixtures must prove exact analytic flux and centroid recovery in
the noiseless case, disjoint source apertures, one count per owned pixel,
boundary/corner equality, and the source-level nonpositive-aperture fallback.

Mask fixtures must reproduce and then exclude disconnected nearby support,
retain connected analytic extended wings, preserve direct seeds bitwise, and
prevent an invalid-pixel gap from creating connectivity.

Evaluation fixtures must prove that source-union split and merge are binding,
native-component topology remains a distinct diagnostic, duplicate and
reliability use catalogue-source rows, and no closed ledger can be loaded as a
rescoring input.

Every fixture passes independently with no compensation. Serial and
existing-Dask results must remain invariant to label permutation, tile shape,
partition origin, worker count, task order, and retry. Terminal per-realization
products, viewed SDC1/Hydra products, and PyBDSF/Aegean catalogues are forbidden
implementation inputs.

## Approval boundary and sequence

Named approval of this exact pre-review would authorize only:

1. test-first source-hierarchy and association implementation;
2. test-first source-level measurement implementation;
3. test-first connected-support admission implementation;
4. a prospective source-topology evaluator;
5. fixture, serial, existing-Dask, coverage, typing, and documentation
   validation; and
6. freezing exact non-executable candidate and replay identities.

After implementation, the complete candidate must pass a no-write identity
verification without opening terminal products or viewed public data. One
complete cumulative replay requires a newly frozen exact composition and a
separate named approval. A passing cumulative ledger would then be followed by
a separately frozen fresh held-out qualification. Campaign execution,
qualification, tuning, rescoring, cutover, and release remain outside this
review.

The exact approval wording is:

> I approve the Phase 5 public-finder source-reconstruction pre-review SHA-256
> `528f18a661bb2391018c458a29aace2757762e58107650e6ae01d05adc85347f`
> and its recommendations. This authorizes test-first implementation and
> fixture-only validation of the deterministic multiscale source hierarchy,
> source-level measurement, connected support admission, and prospective
> catalogue-source topology evaluator, followed by freezing exact
> non-executable candidate and replay identities. It does not authorize a
> cumulative replay, viewed SDC1/Hydra execution, another campaign, fresh
> qualification, threshold or photometric tuning, rescoring, optimization,
> cutover, or release.
