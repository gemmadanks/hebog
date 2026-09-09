# Phase 5 R6 estimator and source-domain repairs

Date: 2026-09-09. Status: **development implementation; not qualification**.

The scientific owner approved the recommendations in the
[R6 root-cause review](phase-5-r6-root-cause-review.md). The original review
and failed terminal remain immutable. These changes implement prospective
repairs on independent analytic and seed-distinct development fixtures.
They do not rescore R6, change its verdict, or authorize a campaign.

## Compact estimators: C1--C3

Joint fits now honour the configured beam/free policy. Significantly extended
components retain free shapes in the joint alternative; other components use
the beam-constrained alternative. The existing BIC rule compares the complete
joint residual and total fitted parameter count once. Parameters, flux and
their marginal covariance come from the same selected joint solution.
Native component selection uses the already declared component-extension
rule, not the stricter Gaussian-source surrogate rule. Source rows are no
longer Gaussian surrogates. Detection and five-sigma intrinsic-axis
classification thresholds are unchanged.

The configured owned-region likelihood uses the union of component owners.
Every Gaussian still contributes at every retained fit pixel; neighbours
are not fitted independently or truncated at ownership boundaries. The much
larger adequacy window remains available to test residual emission but does
not silently enter the likelihood. Dense GLS admission stays at 512 pixels;
larger cases retain the explicit existing diagonal/sandwich fallback.

Two further numerical cases appeared in the independent regression work:

- At a circular Gaussian, ellipse position angle is undefined. A singular
  angle coordinate must not force a beam-sized model with biased flux.
  Singular joint information is re-expressed using the Cartesian precision
  matrix of the **same Gaussian**, retaining cross-component covariance.
  Truly singular information remains unavailable. Flux, position and area
  errors survive a circular-coordinate singularity, but ordered-axis/angle
  errors remain unavailable rather than falsely zero.
- An eigenvector sign could initialize an angle against the optimizer's
  fixed periodic boundary. The same full-turn interval is now centred on
  the initializer. Equivalent orientations no longer create an artificial
  optimizer wall; physical parameter bounds are unchanged.

Tests cover exact and mixed beam/free models, neighbour order, failure of an
alternative, retained support versus adequacy context, work limits, analytic
Jacobian finite differences and periodic orientation. A separate correlated
noise ensemble uses 48 new realizations at each of four masked corners
(192 fits), testing centroid/axis standardized residuals against a declared
99.9% variance interval. This is calibration evidence for those fixtures,
not proof that the closed campaign's 800 corner rows would now pass.

## Observable sources and association: E1--E3

Native Gaussian components keep their full-model centres, shapes and total
fluxes. **All associated source rows, including compact singletons, use
signed, single-owner apertures on finite valid pixels.** A successful
Gaussian cannot substitute unseen off-image flux for the source measurement.
Unavailable signed measurements remain unavailable; component measurements
survive independently. Source shapes and uncertainties are not invented from
auxiliary Gaussian or aperture-moment rows.

Position support is the unexpanded source-owned footprint. Persistent
measurement-only wings still contribute to flux but cannot pull the source
position towards a neighbour. The existing signed/denoised concentration
selector is unchanged. Diagnostics retain both candidate positions and their
domains; one-factor fixtures isolate masking and residual background effects.
Estimated background is not labelled as known background error on real data.

Extended association now subtracts only independently admitted compact
models, not auxiliary fits already rejected by model adequacy. A compact
group can be superseded by seeded adjacent-scale residual emission within
its half-maximum fitted core; broad-envelope overlap alone is insufficient.
This preserves the independent compact-neighbour counterexamples.

Open arcs need not enclose the hole required by the earlier loop diagnostic.
Bounded curvature proposals use fitted centres on a connected, finest
beam-scale significance feature. The existing per-component covariant
tangential-shape test remains required, at the unchanged island significance.
Point polygons, unavailable shapes and collinear centres provide no such
evidence. The connected support is only a bounded work unit, not permission
to merge all its components. Four new open/incomplete, symmetric/asymmetric
arc fixtures complement the closed-shell, filament, core/halo and independent
compact-source guards. This is an image-domain association hypothesis, not
an assertion that radio morphology uniquely identifies physical objects.

## Public contract and evidence retention

Composition is `phase-5-observable-source-and-joint-estimator-v10`; public
diagnostics schema is **7**. Catalogue JSON/FITS schemas remain 3/4, with the
changed source measurement semantics documented in the
[public tutorial](../tutorials/find-sources.md). Stale public diagnostics fail
clearly. No legacy reader or migration is introduced.

Array-free component dispositions retain model selection, sample count,
noise fallback, bound/conditioning and covariance-basis evidence. Original
hierarchy, compact-model and extended-morphology group IDs preserve competing
decisions using linear-size references, not repeated member lists. Source
records retain both centroid estimates, selector, unavailable reason,
position/aperture sizes, signed weight/flux and estimated background mean.
These records add no truth-dependent decision or scientific endpoint.

## Validation and next gate

The combined changes pass the 108-case independent development matrix
(36 geometries under analytic, noisy and public-background conditions), the
focused numerical and association suite, exact public Serial/existing-Dask
conformance, branch-aware project/patch coverage, normal checks, frozen
equivalence fixtures, strict documentation and isolated-wheel smoke tests.
The final coverage suite passes 3,526 tests with 95.1906% branch-aware coverage;
all 184 changed executable lines and changed branches are covered. Normal
checks pass 3,304 tests and all 27 frozen equivalence tests pass. Counts,
intermediate failures, validation limits and review results are in `LOG.md`.

The native 96-parameter/1,000,000-Jacobian-element limits and bounded
morphology-window limit remain enforced before allocation. Reparameterized
information and the second nested solve remain within those admitted
windows. Test durations are engineering checks, not a campaign runtime or
Rapthor speedup claim.

Only after these gates pass may a non-executable candidate identity be
frozen. New candidate-bound cumulative evidence is required for changed
measurements. Reference reuse needs a separate exact provenance and semantics
check. No finder, replay, evaluator, PyBDSF job, qualification or release is
started by this repair. R6 and Phase 5 remain open.
