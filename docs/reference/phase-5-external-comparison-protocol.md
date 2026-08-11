# Phase 5 external source-finder comparison protocol

**Status:** the Step 2C-P protocol, scientific boundaries, isolated runners,
immutable runtimes, sealed complete-population launcher, and scientific
compiler and decision path are ready. Gemma Danks approved the exact
hash-bound one-look
execution on 2026-08-11, and the authorization is frozen in
`config/contracts/phase-5-external-execution-decision.json`. The launcher's
no-write preflight passed over all 1,400 inputs and 7,000 runs; no staging or
finder output was created. The subsequent pre-results review froze the exact
raw-product endpoint registry, compiler, and evaluator identities and checked
the irregular-position adapter against closed development evidence. The
one-look remains unopened. Step 3, optimization, and qualification remain
closed.

This is the first Phase 5 comparison that will place Hebog beside external
source finders. Earlier `paired` Phase 5 results compared only Hebog
representations. The machine-readable protocol is
`config/contracts/phase-5-external-comparison.json`.

## References

| Reference | Exact software | Immutable runtime | Binding scope |
| --- | --- | --- | --- |
| Rapthor release | PyBDSF 1.14.1, commit `1b6e0a0`, published sdist `8d5113f...` | `sha256:dce9399...` | Full continuum |
| Performance reference | PyBDSF `master` `c70103b`, version `1.14.2.dev40+gc70103be3`, wheel `2f1fdfb...` | `sha256:f045820...` | Full continuum |
| Community catalogue reference | AegeanTools 2.3.5, publication commit `bb04f50`, wheel `dda95cb...` | `sha256:ca5fd09...` | Compact, blended, Gaussian-like, and mixed catalogue products |

The two PyBDSF identities are unchanged from Phase 0. They run Rapthor's
5-sigma pixel, 3-sigma island, three-scale residual B3-spline à trous profile.
The controlled diagnostic supplies the same frozen mean and RMS maps through
PyBDSF's documented `rmsmean_map_filename` boundary. PyBDSF's own operational
background/RMS path remains primary. The
[PyBDSF processing reference](https://pybdsf.readthedocs.io/en/stable/process_image.html)
describes the residual à trous module and its scale controls.

PyBDSF checks the RMS-box size before honoring `rmsmean_map_filename`. On the
512-pixel compact/blend lane, the frozen 150-pixel box exceeds one quarter of
the image, so supplied maps would silently be ignored. The runner fails that
controlled diagnostic explicitly instead of giving it a false label. This
does not change the binding operational result, and the 1,024-pixel continuum
lane can use the same-map diagnostic as frozen. The execution review must
accept that scoped diagnostic unavailability or revise the design before any
result is opened.

AegeanTools 2.3.5 is the maintained published release as of the freeze. Its
[published wheel](https://pypi.org/project/aegeantools/2.3.5/) requires NumPy
2.x, whereas the governed Rapthor/PyBDSF runtime retains NumPy 1.26. Aegean
therefore runs in a separate image derived from the same immutable base. The
build verified the published wheel hash and captured dependency-inventory
hash `74f3787...`; its scientific stack includes NumPy 2.5.2, SciPy 1.17.1,
Astropy 7.2.2, and LMFit 1.3.4. This prevents an Aegean dependency upgrade from
changing either PyBDSF reference.

Aegean's primary blind run uses its documented standard 5-sigma seed,
4-sigma flood, covariance-enabled fit, internal background/noise estimation,
and island catalogue. A separately labelled 5/3-sigma diagnostic receives
the same frozen background and RMS products. The
[Aegean command reference](https://aegeantools.readthedocs.io/en/v2.3.4/includes/aegean.html)
documents these controls and the distinction between component and island
catalogues.

## Fresh populations and power

No prior source-finder output or scientific result is reused. Only reviewed
analytic generator geometries, truth definitions, beams, and WCS designs are
carried forward.

| Lane | Images | Purpose | Manifest SHA-256 |
| --- | ---: | --- | --- |
| Continuum | 600 across four beams and geometries | Extended, mixed, edge, invalid-pixel, artifact, scale, and tile strata | `9f88b8904b264e61c5a7445fd8a0cc966cf928d072d010dce3c6d47b6e8e6193` |
| Compact/blend | 800 | Compact, resolved, edge, equal-flux, and 2:1 blend catalogue behaviour | `55c6ecef09711219e45f3e6192cea130b17a02bded6b10e72e1a839743ce2e32` |

All 1,400 noise-seed images are disjoint from every checked-in historical
manifest and from one another. Both lanes have the `regression` role; the
Phase 5 qualification manifest remains unopened and unchanged.

The prospective power audit uses whole-image clustering and conservative
union lower bounds. The continuum lower bound is `0.998392`; the reviewed
Phase 4U compact design supplies `0.969928` for one reference and `0.909784`
after conservatively allowing three references. Their combined lower bound
is `0.908176`, above the frozen `0.90` minimum but intentionally close enough
that its assumptions matter. If an observed per-image paired standard
deviation exceeds a planning bound, the affected comparison is underpowered
and Step 2C-P fails closed. Sample size cannot be adapted after results are
opened.

## Finder-neutral association

Analytic and injected truth is authoritative; the finders are never matched
to one another or treated as votes. Every output is first mapped into the same
pixel-centred coordinate system and associated independently with truth.

- Compact candidates are eligible within half a restoring-beam FWHM.
- Extended candidates are eligible when support overlap relative to the
  smaller support is at least 0.10, or when the candidate centre lies within
  a one-beam dilation of truth support.
- Primary associations maximize cardinality, then overlap, then minimize
  normalized distance, with stable identifiers as the last tie-breaker.
- All eligible secondary edges are retained for duplicate, split, and merge
  metrics; a one-to-one assignment cannot hide topology errors.

Hebog contributes fitted Gaussian centres for compact components and the
confirmed detected-segment centroid for irregular emission. PyBDSF contributes
Gaussian centres for compact components, island masks, and a source moment for
extended position only when its grouping and source-model semantics align.
Aegean contributes component centres and an island-grouped union of fitted
three-sigma ellipses as an association proxy. That proxy is not promoted to a
segmentation mask: Aegean mask precision, recall, and IoU are unavailable,
not passes or failures.

## Binding decisions

Hebog must first pass every unchanged absolute truth gate. It must then be
non-inferior to both PyBDSF references on every applicable continuum metric
and stratum, and to Aegean on compact, blended, Gaussian-like, and mixed
catalogue metrics. Continuum metrics cover completeness, reliability,
integrated-flux median and p95 error, position median and p95 error,
duplicates, mask precision/recall/IoU, and split/merge fractions. Compact
metrics reuse the reviewed Phase 4R registry, including peak and integrated
flux, astrometry, association, and shape products where each finder provides
them.

There is no cross-metric, cross-morphology, or cross-reference compensation.
A reference failure cannot excuse a Hebog absolute failure. Missing binding
output makes that comparison unavailable and fails Step 2C-P. Scientific
outcomes are reviewed before runtime information.

The position contract is explicit by scientific population:

| Population | Binding absolute position checks | Diagnostic only |
| --- | --- | --- |
| Compact/component | radial median at most 0.10 beam; radial p95 at most 0.25 beam | none |
| Irregular detected segment | one-sided 95% upper bounds: absolute signed x/y bias at most 0.10 beam; radial p95 at most 0.50 beam | radial median |

The irregular p95 is repeatability of the reported detected-segment centroid
against the noiseless three-sigma truth-segment centroid. It is not a relaxed
compact astrometry gate and is not a host-galaxy position claim. In
particular, the 0.10-beam signed-axis bias limit must not be relabelled as an
irregular radial-median limit.

A public challenge cut-out is deferred to Step 6 because this controlled host
does not currently hold a redistributable, checksum-bound input with curated
or injected truth. Real-data majority agreement will remain diagnostic, not
ground truth.

## Frozen raw-product compiler and decision boundary

`config/contracts/phase-5-external-evaluation.json` binds the evaluator at
`scripts/validation/evaluate_phase5_external_decision.py`, the external
protocol, Phase 4 and Phase 5 gates, the compact decision engine, and the
confirmed irregular-position contract. It also binds the exact endpoint
registry and compiler:

- compiler SHA-256 `81d1384d2942268b34b52279aafb532ed9bef7dff83f197282b909ee4a033370`;
- endpoint-registry SHA-256
  `a6e469c106cd36800ec775553f1d115523901ab124fc9370eff55522fe7a66d3`;
- evaluator SHA-256
  `df99e10a6fbbe7c4c1b9826c88b0d11908500c817e30aea7750bfc9d920cadab`.

The compiler first verifies the approved execution decision, launcher,
protocol, candidate review, manifests, container digests, source revisions,
dependency inventories, terminal request, every input bundle, every result,
and every artifact checksum. Only then does it read scientific products. Its
prospective registry expands to 143 binding and 15 report-only continuum
endpoints. The compact lane derives 225 exact Phase 4R metric/stratum keys per
PyBDSF reference and 143 applicable Aegean keys; both identity sets are
recomputed from the frozen manifest and registry rather than accepted from
declared totals.

Raw continuum products have one interpretation:

| Quantity | Frozen interpretation |
| --- | --- |
| Catalogue duplicate | More than one eligible catalogue row for one truth group |
| Support split | More than one distinct native support for one truth group |
| Support merge | One distinct native support eligible for more than one truth group |
| Reliability | Primary truth-associated catalogue rows divided by all catalogue rows |
| Mask precision/recall/IoU | Whole valid image; Hebog segment labels versus PyBDSF island labels |
| Flux and position | Conditional on a truth-primary catalogue association; completeness retains unmatched truth separately |
| Compact PyBDSF position and shape | Gaussian catalogue rows, as required by the Phase 4 component contract |
| Compact Aegean position and shape | Component rows grouped by the native island catalogue; deconvolution and joint position/flux uncertainty families remain inapplicable |

All continuum intervals resample complete images as the independent clusters.
Finder failures stay in every endpoint denominator. A stratum with no
conditional flux or position measurement is unavailable rather than silently
dropped, while an unmatched truth group remains visible through completeness.
The irregular signed-axis and radial-p95 absolute bounds use the already
reviewed clustered estimators; the closed development cross-check reproduced
105 estimates, confidence bounds, and medians exactly (maximum absolute
difference zero).

The 50,000-resample path pads each bounded image cluster once and evaluates
SciPy's 500-sample BCa batches with vectorised NumPy reductions. On this
development host, a representative 600-image scalar comparison fell from
5.159 to 0.219 seconds with the identical point estimate and upper bound; a
ragged six-value radial-p95 comparison completed in 4.598 seconds. These are
compiler-kernel checks, not finder or end-to-end campaign speed claims.

The compact manifest remains a `regression`-role external confirmation. The
compiler passes an analysis-only role view to the unchanged Phase 4R
qualification BCa interval implementation because that is the reviewed engine
path; it changes no truth, seed, recipe, stratum, product, threshold, margin,
or gate and records both roles in the output. This is reuse of the frozen
Phase 4 inference implementation, not promotion of the external population to
held-out qualification.

The decision kernel enforces absolute-first decisions, exact binding
references and populations, observed-variance power
audits, recomputation of the paired point-regression direction, and no
compensation. Absolute confidence-bound values remain separate from the point
statistics used for paired comparisons. Synthetic tests cover a complete
pass, higher- and lower-is-better failures, unavailable or missing references,
candidate failure, excess variance, incomplete raw and endpoint populations,
duplicate endpoint identity, and the compact/irregular position split.
The evaluator independently rechecks the exact continuum endpoint population,
both PyBDSF compact key populations, and that the Aegean binding subset is the
unaltered applicable subset of its Phase 4R decision. This separation keeps
raw-product interpretation from changing after the one-look is opened.

## Execution boundary

The finder-neutral matcher retains every eligible topology edge after its
deterministic primary assignment. The materializer publishes one canonical
`input.json` plus checksum-bound four-axis float64 `image.fits`, `mean.fits`,
and `rms.fits`. Every isolated runner consumes that bundle and writes one
atomic `result.json` with checksummed native or normalized artifacts. Failures
remain typed results in the image denominator; partial products are discarded,
and existing results cannot be replaced.

The approved execution decision binds the committed source tree, candidate
review, frozen protocol, four-core PyBDSF allocation, Hebog runtime, and three
runner hashes. `run_phase5_external_campaign.py` expands the complete frozen
matrix before writing anything and binds its own checksum plus the inspected
local image IDs into a canonical request. Containers run by immutable image
ID with networking disabled and only the committed repository read-only and a
hidden campaign directory writable. The 512-pixel PyBDSF controlled leg is
absent from the matrix; its typed unavailability is already represented by the
approved scope rather than by a misleading run.

Opening creates a deterministic hidden sibling of the requested output.
Resume is explicit and accepts only the byte-identical request and opening
state. Materialization and 7,000 finder legs remain serial and private;
container failures are retained as infrastructure logs, while finder failures
remain typed terminal results in the scientific denominator. Publication
requires every expected `input.json` and `result.json`, verified artifacts and
runtime identities, no undeclared result manifest, and no abandoned private
temporary path. A canonical `campaign.json` is written atomically and the
complete staging directory is then renamed once to the public target. A
verified manifest left by an interruption before that rename is safe to
resume. Passing Step 2C-P will still require a reviewed scientific decision
before Step 3 opens.

### Prepared Hebog runtime

Gemma Danks approved the 512-pixel diagnostic limitation, a four-core PyBDSF
allocation, and immutable Hebog-runtime preparation on 2026-08-11. The runtime
was built from a clean archive of commit
`106715b22b9858149e42467f4e2c581f15961cb0`, not from the working tree. Its
frozen identity is:

- Linux/arm64, Python 3.14.7, Hebog 0.6.0;
- image digest
  `sha256:b92080db558246e2ae781c69f6caf39fef8e393ab74ea6774d9b02672981b4ce`;
- 35-distribution inventory SHA-256
  `d383be3a97d716ce033b1151a5282729794dbc5f1734081d3ed36bcd2409b5a2`;
- baked and checkout source-tree SHA-256
  `471bed9a428df10d9139afc334d97b5df190f4f64e6dd6daeb91f9b436d37362`.

The resolved parent images were `python:3.14-slim` at
`sha256:c65a4a1140b75416bbc7f28807f82a3746bd6567645d5848123b6a6587f86962`
and `ghcr.io/astral-sh/uv:0.9.16` at
`sha256:d8b6f79959466b3e45efebd7143f1d6e3bb72a1c6f9482fd154edbc5331b9299`.
The CLI and validation imports passed, as did the residual-B3 kernel on a
64-by-64 zero plane and the complete compact branch on the existing 256-pixel
development fixture. These checks did not materialize, process, or inspect any
frozen external-comparison realization. Final execution authorization remains
present; the one-look population remains unopened.
