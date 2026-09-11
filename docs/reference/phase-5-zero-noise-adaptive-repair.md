# Phase 5 zero-noise adaptive-region repair

## Scope and cause — 2026-09-11

The user approved repair, non-regression and Serial/Dask validation, followed
by a corrected-candidate freeze before replay launch. This addresses the
independent [v12 admission failure](phase-5-v12-replay-preparation.md), not a
viewed campaign result. Closed scientific results and the completed notebook
refresh remain unchanged.

The exact independent development fixture has two finite Gaussian components
near the small-coordinate image corner, 512 by 512 pixels, seed `2026981103`,
and no injected noise. A diagnostic trace confirms that source protection removes
emission from the coarse background/RMS statistics, leaving a six-by-six
coarse grid with exactly zero background and RMS. These are defined
zero-variance statistics, not missing input samples. The bright-region work
anchor `(y=47, x=45)` came from the earlier unprotected estimate. Requiring it
to belong to sigma-thresholded support after that correction raised
`adaptive candidate is absent from source-protection support` because
normalization correctly excludes zero RMS everywhere in the bounded region.

## Repair contract

Admit a source-protected adaptive request only when its bounded coarse grid
is scientifically available and contains finite positive RMS. Otherwise
retain the corrected coarse estimate and any independently computed local
noise grid. Other usable regions are admitted independently. Do not
re-estimate unprotected source emission as noise to satisfy an old work
anchor. Unprotected compact refinement and the strict connected-support
anchor validator are unchanged.

This preserves the existing public unavailable-RMS contract: when the final
image has no positive RMS, sigma-based source measurements are unavailable.
The RMS product is explicitly marked unavailable and contains NaNs; no
catalogue rows are produced. This is **not a claim that a noiseless image
contains no real sources**, and must not be interpreted as a successful
scientific non-detection or parity verdict. Ordinary noisy source controls
must retain real detections.

No RMS floor, threshold, estimator clipping policy, association rule,
measurement algorithm, population, comparator or evaluator gate changes.
The admission check uses only bounded grid summaries and existing NumPy;
it adds no scheduler, dependency, pixel loop or global image gather. The
composition is `phase-5-evidence-bound-public-catalogue-v13`; public schemas
are unchanged and old composition identities fail clearly. Old reviews and
closed outputs cannot qualify this candidate.

## Required validation and replay boundary

The exact public regression and zero/unavailable-region unit regressions
were first run red with the reported production exception. Controls cover
positive noise, an independently noisy neighbouring region, local-noise
preservation, real two-component detection and actual caller-owned
two-worker Dask agreement with Serial. The wider required non-regression
suite covers broad-source protection, compact/extended blends, empty and
invalid pixels, catalogue association, bounded background processing and
the current-only capture/evaluation reuse path.

Validation on Python 3.14.2 passes 219 focused tests, 3,778 portable tests
with two existing expected failures, and all 27 frozen equivalence tests.
A 25-test bounded-background supplement includes six explicit rejection
cases proving the strict malformed-anchor guard remains intact. Combined
branch-aware coverage is **95.26468995%**, above the prior frozen
**95.25775988%**. Both changed executable lines are covered; there are no
missing branches in the changed range. All admission outcomes and their
short-circuit cases are exercised explicitly, including unavailable, zero
and positive noise. Ruff, Pyright and standard checks (3,476 quick tests
before the six-case supplement) pass. The noisy public catalogue, RMS and
mask are exactly equal between archived v12 and repaired v13, as well as
between Serial and existing Dask. Review against `CODE_REVIEW.md` finds no
actionable issue; clean all-file hooks are required before each commit.

Freeze the corrected committed source only after focused, coverage,
equivalence, standard checks, documentation and final hook gates pass.
The freeze itself is non-executable and development-unqualified. A new
preparation, representative independent cost/space admission, exact committed
launch owner and exhaustive no-write verification remain necessary before
the authorized isolated replay can start. Never launch v12 or transfer a
closed scientific result to v13. Python 3.12/3.13 and controlled production
scale/performance remain unverified locally.
