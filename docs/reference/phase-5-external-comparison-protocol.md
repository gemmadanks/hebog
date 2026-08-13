# Phase 5 external source-finder comparison protocol

**Status:** the Step 2C-P protocol, scientific boundaries, isolated runners,
sealed complete-population launcher, and scientific compiler and decision path
are ready. Gemma Danks approved an exact hash-bound one-look execution on
2026-08-11; that superseded authorization remains in Git history and `LOG.md`.
Its no-write preflight passed over all 1,400 inputs and 7,000 runs; no staging
or finder output was created. The four approved local images were then lost
before execution. The reconstructed external-reference identities are now
protocol-bound, smoke-tested, and aligned to the originally frozen scientific
stack. The final Hebog runtime has been rebuilt from the committed fail-closed
source and bound into the checked-in decision. Gemma Danks renewed named
approval for all four exact identities, four PyBDSF cores, the scoped
512-pixel diagnostic limitation, and one sealed terminal execution on
2026-08-11. The renewed no-write preflight passed with request `31a56c50...`,
exactly 1,400 inputs, and 7,000 runs while leaving terminal and private paths
absent. The one-look then completed all 8,400 isolated invocations and
atomically published checksum-verified terminal raw evidence with manifest
SHA-256 `b9996100...`. The first compiler attempt failed closed before writing
analysis because an analysis-only Phase 4R role copy retained a plain string
instead of its enum type. After the committed, regression-tested type-only
correction, analysis `bdc59fdc...` and frozen decision `73c7e2eb...` closed the
campaign as `fail`/`select-neither`. All 143 Continuum endpoints were
indeterminate, compact comparison also failed, and only 1,492 of 5,000 binding
runs succeeded. Step 3, optimization, and qualification remain closed. The
campaign may support failure diagnosis but may not be rescored or reused as
confirmation.

This was the first Phase 5 comparison to place Hebog beside external source
finders. Earlier `paired` Phase 5 results compared only Hebog
representations. The machine-readable protocol is
`config/contracts/phase-5-external-comparison.json`.

## References

| Reference | Exact software | Immutable runtime | Binding scope |
| --- | --- | --- | --- |
| Rapthor release | PyBDSF 1.14.1, commit `1b6e0a0`, published sdist `8d5113f...` | `sha256:dce9399...` | Full continuum |
| Performance reference | PyBDSF `master` `c70103b`, version `1.14.2.dev40+gc70103be3`, wheel `2f1fdfb...` | `sha256:f045820...` | Full continuum |
| Community catalogue reference | AegeanTools 2.3.5, publication commit `bb04f50`, wheel `dda95cb...` | `sha256:ca5fd09...` | Compact, blended, Gaussian-like, and mixed catalogue products |

These are the originally authorized runtime identities. They remain useful
historical provenance but are no longer present on the controlled host. The
reconstructed identities are listed under the execution boundary below.

The two PyBDSF software and artifact identities are unchanged from Phase 0.
They run Rapthor's
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

AegeanTools 2.3.5 is the maintained published release selected at the freeze. Its
[published wheel](https://pypi.org/project/aegeantools/2.3.5/) requires NumPy
2.x, whereas the governed Rapthor/PyBDSF runtime retains NumPy 1.26. Aegean
therefore runs in a separate image derived from the same immutable base. The
replacement build verified the published wheel hash and captured
dependency-inventory hash `346c1f3...`; its scientific stack includes NumPy 2.5.2, SciPy 1.17.1,
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

- compiler SHA-256 `7a0558916ac003b71a781337dc710c99c359899c4d77f88486c1c206916b43f6`;
- endpoint-registry SHA-256
  `d174fc9e9ab6648427147850e948ee33d77a6cf8cfccc05cb8a82cbd3141ff9b`;
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
resume. Step 2C-P required a reviewed scientific decision before Step 3; its
terminal decision failed and keeps Step 3 closed.

### Terminal decision

The corrected compiler finished against the unchanged terminal manifest and
wrote analysis SHA-256
`bdc59fdc62409c32bba8233b848e93581a5da4131e50c48a5b0771ce2fd2a227`.
The unchanged frozen evaluator wrote decision SHA-256
`73c7e2eb4befb87b35fc9cb4a35a90fe28a5a4f9864c33aa4a5ef77069689dac`.
It records `scientific_outcomes_before_runtime=true`, `status=fail`, and false
values for Step 3, optimization, and qualification.

The terminal campaign contained 2,292 successful and 4,708 failed finder runs.
Aegean completed all 1,600 operational and controlled runs. Hebog completed
692/1,400; 576 failures contained a reconstructed segment with non-positive
aperture flux and 132 lacked a finite positive local RMS. Each PyBDSF version
failed all 1,400 operational runs at the adapter's island-mask/label check and
all 600 controlled-background runs while PyBDSF loaded the supplied mean/RMS
files. These failures made all external science indeterminate; they do not
establish scientific inferiority or non-inferiority.

Runtime is contextual only because Hebog was not scientifically eligible. The
serial campaign took about 7 h 12 min. Aegean's median controlled/operational
wall times were 1.56/1.79 seconds, and successful Hebog runs had a 2.85-second
median. PyBDSF and failed-Hebog timings terminate on errors and are not
comparable performance evidence. Per-run CPU and peak memory were not captured
and are explicitly unavailable.

### Prospective failure correction

Step 2C-PF diagnosed the terminal failures without rescoring the closed
campaign. PyBDSF stores `pyrank` in internal x/y order and transposes it when
exporting FITS products; the adapter had compared its untransposed labels with
the exported mask. Native PyBDSF detection islands can also remain fitless, so
Gaussian island IDs are required to be a subset of source island IDs, which
are in turn a subset of label IDs. In controlled mode PyBDSF resolves supplied
mean/RMS names relative to the input-image directory, so the corrected runner
passes adjacent basenames instead of absolute paths. Both pinned PyBDSF
versions emitted their four expected products in operational and applicable
controlled diagnostics after these changes.

Hebog's segment catalogue had grown accepted support by four beam widths only
for photometry. Negative noise in that larger aperture caused positive
detections to abort. Segment position and flux now use the same exact accepted
support; detections without a physical signed-flux measurement remain in the
mask and labels without an invented catalogue row. Local RMS sampling now
normalizes bilinear weights over finite positive neighbours, while retaining
explicit unavailability when none exist. The two already-opened representative
failures now complete and emit all four products.

A 12-cell diagnostic matrix then passed with zero unexpected runner failures:
Hebog on compact/blend and continuum inputs; each PyBDSF reference on compact
operational and continuum operational/controlled modes; and Aegean on both
inputs in both modes. The continuum input includes diffuse, shell, filament,
edge, invalid-pixel, and varying-noise strata. The approved 512-pixel PyBDSF
controlled diagnostic remains inapplicable. This matrix checked execution and
product validity only; no closed-campaign science metric was inspected,
rescored, or promoted.

The prospective successor science boundary is implemented independently in
`hebog.validation.external_successor_compiler`. It keeps two populations
explicit:

| Population | Included products | Scientific use |
| --- | --- | --- |
| Measurable catalogue rows | Rows whose island IDs refer to positive native labels | Catalogue completeness and reliability; conditional flux and position; catalogue duplicates |
| Native support objects | Every distinct positive label, including fitless and otherwise unmeasurable labels | Mask overlap and support split/merge topology only |

A label-only detection therefore contributes to mask and topology
denominators, but it does not receive an invented catalogue centre, flux,
identity, completeness match, or reliability observation. Its geometric
support centroid is used only as a deterministic topology descriptor when no
catalogue row exists; catalogued supports retain the frozen row-centre
aggregation. Truth recovered only by that label remains unmatched in
catalogue completeness; conditional flux and position remain unavailable.
When every positive label
has a catalogue row, the successor kernel reproduces every terminal continuum
metric exactly.

Twenty-one focused tests cover ordinary, label-only, fitless, artifact, empty,
malformed, and misaligned cases with complete line and branch coverage. On the
already-opened diagnostic continuum realization, released PyBDSF produced 12
catalogue rows alongside 11 native supports, with the catalogue-label set a
strict subset of the native-label set. Pinned master produced 14 rows alongside
11 supports. Both passed the prospective adapter without coercion. These were
product-validity checks only, not science rescoring.

The successor population and prospective power audit are now frozen in
`phase-5-external-successor-population.json`:

| Lane | Images | Seed range | Manifest SHA-256 |
| --- | ---: | --- | --- |
| Continuum | 600 across four reviewed geometries | `2026820001`–`2026823150` in four disjoint blocks | `906a3e8bcc5bbc775418c30b5da08559e1425fbae74dd05fd9b2e96f69df7c46` |
| Compact/blend | 800 | `2026830001`–`2026830800` | `05507a6605873981636b18d1b63e1b6e715937790c290027e72117a5928ce81c` |

All 1,400 seeds are disjoint from 9,053 historical seeds across 35 checked-in
manifests, including the closed campaign. The new population reuses the
reviewed geometry, endpoint, margin, and sample-size design—not any image,
finder product, measurement, or result. The power model was recomputed through
the typed validator and retains lower bounds of 0.998392 for continuum,
0.909784 for the three-reference compact family, and 0.908176 jointly. The
joint result remains above the unchanged 0.90 gate. Excess observed variance
still fails closed; sample size cannot adapt after results are opened.

The freeze binds candidate commit `c1f7eb0...`, source-tree SHA-256
`d50be758...`, the mask-only science kernel `8e38de3...`, all three corrected
runner hashes, and the exact intended package inventories. Read-only local
inspection confirmed the three reference image digests remain present. The
historical Hebog image does not contain the bound candidate source, so its
digest is explicitly absent and its status is `candidate-rebuild-required`.
Execution, output opening, and qualification remain false.

The next gate is to rebuild Hebog from the bound source and freeze the complete
successor verifier/compiler composition, endpoint registry, evaluator,
launcher, gates, runtimes, and one-look rule for named review. The terminal
compiler remains unchanged at SHA-256 `7a055891...`; its closed evidence chain
will not be rebound.

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
frozen external-comparison realization. That exact image is no longer present.
Its scientific inventory and source tree were reproduced below. Its historical
execution authorization could not transfer to the reconstructed image; a
later named review separately authorized the rebuilt identities used by the
now-closed campaign.

### Reconstructed runtime set

The four images were reconstructed on 2026-08-11 without opening or creating
any external-comparison input or result. Each build retained the frozen finder
version or source revision and used the same Linux/arm64 platform. The current
identities are:

| Runtime | Reconstructed tag | Image digest | Dependency inventory SHA-256 |
| --- | --- | --- | --- |
| Hebog 0.6.0 | `localhost/hebog:phase5-external-303a49d-reconstructed-final` | `sha256:728bbd7ab59d0fbb9537d36fac34652e640300091024498cbebdaeb452da55a6` | `d383be3a97d716ce033b1151a5282729794dbc5f1734081d3ed36bcd2409b5a2` |
| PyBDSF 1.14.1 | `localhost/rapthor-dev:ci-aligned-reconstructed` | `sha256:72454074489d5ed0d0ed08781ec11411a3e25ccf75e3378a924152176fa15b37` | `8211043e9fca55d706d1e890e2bf0b630e228a854db0949258c498506975669f` |
| PyBDSF master | `localhost/hebog-pybdsf-master:c70103be3-reconstructed` | `sha256:192964b32d50a6e960cf3710013ffa92d782ecf43a4d6def4309a7cb10911e73` | `83574dd4c15d79f3cf2ac52fb8aa7b5bd2ff323c93343b2f1337eec938e8bf99` |
| AegeanTools 2.3.5 | `localhost/hebog-aegean:2.3.5-step2cp-reconstructed-matched` | `sha256:b496d2907c13d083e7c87eda61a6a40057f92b5cb6e605330bcb1b6db27158b8` | `346c1f32b0d78ce1d22f6d6ff20787a102d8491c14432865465596c9f41ba909` |

Hebog has Python 3.14.7, the exact 35-distribution inventory, implementation
commit `303a49d...`, and source tree `2f80c87...`. The published PyBDSF 1.14.1
sdist, frozen master wheel, and published AegeanTools wheel retained checksums
`8d5113f...`, `2f1fdfb...`, and `dda95cb...`. Both PyBDSF references use the
same Python 3.12.3 scientific stack and differ only in the `bdsf` distribution
version. Their runner imports
and a three-source 256-pixel governed compact fixture passed with identical
three-source/three-Gaussian counts. Aegean's runner import, CLI, and the same
fixture passed, finding three islands and fitting six components. Hebog's CLI,
source, and inventory checks passed.

The first replacement Aegean build resolved newer Astropy and SciPy releases
than the originally frozen environment. It was rejected before authorization,
replaced by the matched stack above, and removed. The earlier Hebog
reconstruction was superseded because the fail-closed runtime validator
changed its source-tree identity. The final image above was built from a clean
archive of the validator commit, then reproduced the exact checkout source and
dependency checksums and the three-source governed compact smoke result. The
execution decision bound it for the single terminal campaign described above.

The checked-in build definitions and artifact requirements are documented in
`scripts/benchmark/containers/phase5/README.md`. They deliberately do not
claim bitwise reproduction of the missing OCI objects. The renewed review
accepted all four bound digests and inventories, the launcher's no-write
preflight passed, and the resulting sealed campaign is now closed as
`select-neither`.

### Successor terminal execution

The seed-disjoint successor used Hebog commit `c1f7eb0...`, source tree
`d50be758...`, and Linux/arm64 image digest `sha256:d0c1319...`, alongside the
three reconstructed references above. Gemma Danks approved those exact four
runtime identities and preflight review `200d107...`. Canonical request
`931df412...` then completed once and atomically published terminal manifest
`6446705f...`: all 1,400 inputs and all 7,000 finder runs verified, with 6,939
successes and 61 typed failures. No partial scientific product was opened.

The first checksum-bound successor compiler invocation failed closed before
writing analysis because the composed terminal request verifier recognized
only the closed campaign's approval names. After that correction was committed,
the second invocation also failed closed before output: the deliberately
minimal successor protocol inherits its reference runtimes from the closed
protocol rather than duplicating them. The composition now uses the same
strictly validated protocol compatibility view as the reviewed launcher and
maps only the successor decision ID and approval value to their terminal
equivalents. No campaign, product, science kernel, endpoint, threshold,
confidence rule, reference scope, or evaluator changed. The corrected
successor compiler is `2fd78b60...`, the refreshed endpoint registry is
`99a79e5e...`, and the evaluation contract is `d69dd830...`; the byte-identical
terminal compiler remains `7a055891...`. Analysis and scientific decision
remained unopened until this technical correction was committed and validated.

The corrected compiler then completed in approximately five hours and
atomically published analysis `b6c77b87...`, covering all 1,400 images and all
5,000 binding runs while retaining 61 typed failures. The first evaluator
invocation failed closed before decision output because its entry point loaded
the deliberately minimal successor registry directly; the immutable evaluator
requires the inherited 158-endpoint policy matrix. The evaluator composition
now uses the same strict successor-registry loader already used to validate the
contract. No endpoint, gate, campaign datum, or compiled scientific value
changed, and the scientific decision remains unopened pending validation and
commit of this final metadata correction.

After that correction was committed, the unchanged evaluator published
decision `1d8c2577...` as `fail`. All 143 binding continuum endpoints are
indeterminate and compact also fails; Step 3, optimization, and qualification
remain closed. All 61 execution failures are Hebog continuum legs: 60 reject a
NaN local RMS (59 in continuum geometry 4 and one in geometry 2), and one
geometry-2 leg contains a compact-fit omission. Because the frozen runner
publishes compact and continuum products transactionally, these failures also
discard otherwise usable segment products. The compact comparison passed 441
of 450 PyBDSF endpoint decisions and 135 of 143 applicable Aegean decisions;
the non-passes concentrate in position tails versus PyBDSF and integrated-flux
tails versus Aegean. This campaign may guide prospective corrections but must
not be rescored, tuned, or reused as confirmation evidence.

## Prospective correction after the failed successor

The closed successor was then used only as development evidence. Hebog now
executes continuum and compact lanes independently, so compact fitting cannot
discard a valid continuum segmentation. Missing centroid RMS support falls
back to the finite owned-region RMS with an explicit quality flag. A region
with finite moment photometry but no acceptable Gaussian retains an explicitly
flagged source row and no fabricated Gaussian component.

The compact comparison boundary now emits the fitted-Gaussian component
catalogue required by the protocol. This keeps the Gaussian integral for the
PyBDSF/Aegean like-product comparison while preserving Rapthor's reviewed
peak-as-total convention on the distinct source record. A full 800-image
development rerun selected the existing free-only, selected-model Gaussian
policy: every image completed; the four formerly failing PyBDSF position point
estimates and seven Aegean flux point estimates moved to the favourable side;
and the marginally resolved fitted-axis p95 improved from `0.20472` to
`0.17292`, compared with Aegean's `0.19026`. These numbers are diagnostic, not
a rescore of decision `1d8c2577...`; new seed-disjoint evidence remains
mandatory before Step 3 can open.
