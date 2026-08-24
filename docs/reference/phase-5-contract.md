# Phase 5 multiscale contract and development review

**Status:** the external recovery decision passed every applicable absolute
and cross-finder gate, and Phase 5 Step 3 is complete. Compact Gaussian
astrometry remains unchanged; bounded multiscale detection, deferred-island
completion, original-pixel extended measurement, and the compact-preservation
boundary are implemented. Step 4 adjacent-scale association, compact context,
stable combined identities, bounded terminal-state reduction, and final
product construction are also implemented. The first two Step 5 tasks now
derive and admit every stage-specific halo and prove complete one-tile/many-
tile scientific equality across the reviewed boundary matrix. Step 5 is now
complete: executor and retry invariance, bounded byte-level execution evidence,
and the complete Phase 4 compact regression are also green. The controlled
incremental performance gate and untouched qualification remain open. This
contract does not yet establish production multiscale equivalence.

The approved Step 4 policy is recorded in the
[compact/extended association pre-review](phase-5-association-pre-review.md).
Named approval on 2026-08-24 froze the association rules in schema 2. Schema 3
adds the implemented combined-island, extended-source, and zero-extended-
Gaussian identity rules without changing that approved association policy.
Schema 4 adds the implemented catalogue-row, mask, RMS-reuse, provenance,
diagnostics, and Rapthor-view semantics. Schema 5 adds the reviewed
stage-specific halo formulas and fail-closed geometry and task-pixel
admission. Schema 6 adds the core-only tile-filter ownership boundary, the
three-beam segment-association halo, and the reviewed one-tile/many-tile
equality matrix. The [bounded-execution review](phase-5-bounded-execution.md)
records the derivation, proof, and remaining evidence boundary. The bounded
adjacent-scale and compact-context kernels, deterministic combined identity
derivation, terminal-state reduction, and final product construction are
implemented.

The 2026-08-08 community-practice review nominated residual B3-spline à trous
reconstruction, morphology-independent support growth, and original-image
measurement. Steps 2C through 2C-HR evaluated and confirmed its explicit
detected-segment position without changing the frozen gates or opening
qualification. The recovery campaign established it as the passing
development selection. It is not a production selection until untouched
qualification, bounded execution, performance, and independent review pass.

Gemma Danks asked Codex to complete Phase 5 Step 1. Codex performed the named
scientific and engineering review recorded here as an AI-conducted synthesis
of the governed compact evidence, analytic truth design, and cited literature.
It is not independent human, institutional, or SKA science approval. An
independent radio-astronomy review and controlled real-residual evidence remain
mandatory before production cutover.

## Inventory of inherited multiscale work

| Input or path | Frozen observation | Products or decisions affected |
| --- | --- | --- |
| Rapthor compatibility profile | The pinned profile enables PyBDSF a-trous processing with `atrous_jmax=3`, hard 5-sigma detection, and 3-sigma island thresholds. | Catalogue rows and fluxes, island mask, source count, diagnostic summaries, and sky-model membership. |
| Representative 3,000-square comparison | Released and pinned-`master` PyBDSF each contain 12 mask objects. Phase 3 recovers the seven compact objects with reliability 1.0; five reference objects remain unmatched and full-mask recall is about 0.405. | The missing foreground can change mask-based filtering, island grouping, catalogue membership, and retained/rejected Rapthor components. |
| Compact deblend admission | An island above `maximum_compact_island_pixels` or `maximum_compact_bounds_pixels` becomes an explicit `DeferredDeblendIsland`. | Phase 4 catalogue publication fails closed while any deferral remains; Phase 5 must produce one terminal disposition rather than dropping it. |
| Phase 4 catalogue boundary | Compact catalogues require every admitted fit and contain no Phase 5 deferral. Phase 4U is the passing compact baseline. | Enabling multiscale work must leave compact-only output unchanged when no scale evidence changes an association. |
| Rapthor filtering join | The mask is sector-clipped, selects sky-model membership, and supplies island grouping; the catalogue supplies astrometry, photometry, extent, and counts. | Phase 5 must validate both scientific objects and the final retained/rejected component decision, not catalogue recovery alone. |

The five representative objects are compatibility evidence rather than
scientific truth. Their reference labels depend on a particular mask file and
are intentionally not promoted to durable Hebog identities. The Phase 5
comparison must match by governed overlap, sky position, and flux.
None of these paths may modify the RMS product: every scale reuses the Phase 2
background and RMS, and a multiscale-only change leaves RMS status and bytes
unchanged.

## Frozen scientific meanings

The machine-readable meanings are in
`config/contracts/phase-5-multiscale.json`.

- Scale orders are `1`, `2`, and `3`, reported nominally as `1`, `2`, and `4`
  restoring-beam major-axis FWHM. This freezes the Rapthor-used dyadic scale
  sequence without copying PyBDSF's implementation.
- A scale response is normalized to unit integrated-flux response in Jy/beam.
  Detection and island thresholds are the explicit scientific configuration
  thresholds applied to that normalized response.
- Phase 2 background and RMS products are reused. A scale pass may not rerun
  ingestion, background estimation, or the complete compact pipeline.
- A valid response requires finite input, background, and RMS with positive
  RMS. At least 50% of the filter support must be valid. Masked or clipped
  support is renormalized and its visible fraction is retained; insufficient
  support is a typed unavailable result.
- Step 2 compared a beam-aware matched-filter bank with an undecimated
  wavelet construction and provisionally selected the matched-filter bank
  after both passed the initial analytic gates. The much smaller wavelet error
  in the masked and edge probes requires the paired Step 2B scientific
  comparison before final selection. The support threshold changed from 80%
  to 50% because the original value made the required image-edge stratum
  unavailable.
- Cross-scale identities derive from global overlap, flux, and retained scale
  provenance. Local label, tile, task, retry, and worker order have no
  scientific meaning.
- Duplicate detections retain every contributing scale but select one
  catalogue representation. Isolated compact measurements remain unchanged
  when no multiscale evidence changes their association.
- Compact context is an array-free many-to-many edge set between accepted
  Phase 4 source identities and reconciled extended identities. Reference
  containment, exact support overlap, and the frozen half-major-beam context
  dilation provide spatial evidence only; no edge merges, suppresses, or
  relabels either source. Conflicting exact extended ownership fails closed.
- A compact-only graph component keeps its exact Phase 4 island, source, and
  Gaussian-component identities. A mixed or extended graph component derives
  its island ID from canonical compact-island and association membership.
  Each extended association derives one source ID from its association ID, so
  a change in spatial context can change grouping without relabelling the
  extended source.
- An irregular extended source has zero Gaussian compatibility components.
  Hebog does not claim that a segment was fitted by inventing a Gaussian.
  Compact Gaussian components remain exact, and the Rapthor view can consume
  the extended `SourceCandidate` row directly because it materialises source
  rows rather than requiring one component per source.
- Extended rows use the detected-segment flux centroid, original-pixel peak
  brightness and integrated flux, and local RMS. Their segment-moment major
  extent is exposed in the Rapthor `DC_Maj` field as a characteristic extent,
  with an explicit quality flag; it is not represented as a fitted or
  deconvolved Gaussian ellipse.
- The final source-filtering mask is the bounded blockwise union of the Phase
  4 compact mask and accepted extended support. The Phase 2 RMS
  `MaterializedProduct` is reused exactly rather than recomputed or rewritten.
  Diagnostics schema 2 records one canonical scale/support provenance record
  per extended source; compact-only results retain diagnostics schema 1.
- The pre-association preservation boundary recognizes only `extended-only`
  evidence with no compact source identities as non-altering. It returns the
  exact completed compact object. Any compact-touching or ambiguous relation
  fails closed until Step 4 makes the governed association decision.
- Unsupported scales fail at configuration validation. Unavailable
  measurements and ambiguous associations are typed omissions. Every accepted
  or deferred island requires one terminal disposition, and any incomplete
  result forbids catalogue publication.
- Terminal state carries separate canonical accepted- and deferred-island ID
  sets. Pairwise fan-in-two reduction is independent of shard order and records
  its depth and maximum input-shard size. Completion additionally requires an
  explicit positive in-memory record cap; missing dispositions, omissions,
  failed dispositions, duplicate ownership, or unknown terminal evidence
  block every downstream publication path.

The internal records include `ScaleDetection`, `CompactSourceSupport`,
`CrossScaleAssociation`, `CompactExtendedContextEdge`,
`CombinedIslandIdentity`, `ExtendedSourceIdentity`,
`ExtendedEmissionMeasurement`, `MultiscaleOmission`,
`CombinedIslandDisposition`, `CombinedCatalogueShard`,
`CombinedCatalogueReduction`, `CombinedCatalogueState`, and
`CompletedCombinedCatalogueState`.
`CrossScaleAssociation` is version 2 and uses the approved explicit spatial
relationship vocabulary. `ExtendedEmissionMeasurement` is version 2: it
distinguishes the
detection-conditioned segment centroid from the brightest original pixel,
denies a host-position claim, and keeps position uncertainty unavailable until
support selection is calibrated. `CombinedCatalogueState` is version 2 so the
required accepted and deferred island populations are explicit. The remaining
records are version 1. All records are strict, immutable, and scheduler safe;
bounded label planes remain worker-local inputs and never enter result records.

## Frozen datasets

The generator remains version 3. Phase 5 morphology is represented as
version-three truth metadata over deterministic Gaussian basis emitters. A
group supplies its catalogue role, beam-normalized extent, contributing scale
orders, reference centroid and integrated brightness, edge and tile-boundary
state, and morphology. This records analytic truth without committing the
production algorithm to a Gaussian decomposition.

| Manifest | Role | Images | Purpose |
| --- | --- | ---: | --- |
| `phase-5-development.json` | development | 10 | Fast scale-response, schema, failure, and association TDD. |
| `phase-5-regression.json` | regression | 100 | Seed- and geometry-disjoint morphology, scale, mask, edge, artifact, and boundary regression. |
| `phase-5-corrective-a-confirmation.json` | regression confirmation | 100 | One-look seed-disjoint confirmation of the frozen Step 2C-A estimator. |
| `phase-5-astrometry-follow-up-development.json` | development | 80 | Fresh geometry and noise validation of the detected-segment position. |
| `phase-5-astrometry-follow-up-confirmation.json` | regression confirmation | 400 | Sealed one-look confirmation, unauthorized pending development and human review. |
| `phase-5-qualification.json` | qualification | 400 | Untouched one-look population spanning every governed stratum. |

Each image contains diffuse, filamentary, curved-filament, shell,
mixed compact/extended, and artifact truth, plus an image-edge object. The
filament crosses a nominal 512-pixel tile edge; the shell crosses the tile
corner and is predeclared for the deferred extended path above the governed
compact-deblend test limit. A governed invalid rectangle overlaps the mixed
object's wider support, the RMS varies
across the image, and the noise is beam-correlated. Artifact groups are
positive deterministic sidelobe analogues whose catalogue role is explicitly
`artifact`; they are not claimed to reproduce real calibration residuals.

The image/noise seed is the independent unit. Seed ranges do not overlap:

- development: `2026700001`--`2026700010`;
- regression: `2026710001`--`2026710100`;
- Step 2C-A confirmation: `2026730001`--`2026730100`; and
- Step 2C-HR development: four 20-image ranges beginning at `2026760001`,
  `2026761001`, `2026762001`, and `2026763001`;
- Step 2C-HR confirmation: four 100-image ranges beginning at `2026770001`,
  `2026771001`, `2026772001`, and `2026773001`; and
- qualification: `2026720001`--`2026720400`.

The qualification population is frozen before algorithm selection, tuning,
or result generation. No Phase 5 output path existed at review time.

## Scientific gates and statistical design

`config/contracts/phase-5-scientific-gates.json` is conjunctive. Analytic and
injected truth provide the absolute oracle; released PyBDSF and pinned
PyBDSF `master` are separate compatibility comparators. A better flux result
cannot compensate for worse completeness, reliability, astrometry, mask
topology, duplicate control, or Rapthor filtering.

The Step 2B through 2C-A paired endpoints compared Hebog representations with
each other; neither PyBDSF nor Aegean was executed in those reviews. They
therefore do not satisfy the external-comparator clause above. Before Step 3,
a successor pre-results protocol must preserve the numerical gates and bind a
fresh comparison population, both exact PyBDSF references, and a maintained
Aegean release.

PyBDSF with `atrous_do=true` is binding over the applicable full-continuum
scope: catalogue completeness and reliability, astrometry, flux, masks,
duplicates, and split/merge topology. Aegean is binding for compact, blended,
and Gaussian-like catalogue completeness, reliability, astrometry, flux,
association, duplicate, and split/merge metrics. Its extended-island results
are diagnostic because Aegean is a compact-source finder without an à trous
diffuse-reconstruction product. An unavailable Aegean extended mask is not a
failure by either finder. Hebog must still pass every absolute injected-truth
gate; a weak reference result cannot legitimize a weak Hebog result.

The following absolute margins apply independently to generated regression
and held-out qualification, overall and in every applicable governed stratum:

| Metric | Gate |
| --- | ---: |
| Completeness | at least 0.90 |
| Reliability | at least 0.95 |
| Median / 95th-percentile integrated-flux fractional error | at most 0.10 / 0.25 |
| Compact/component fitted-position median / p95 error | at most 0.10 / 0.25 beam FWHM |
| Irregular detected-segment signed-axis bias / radial p95 upper bound | at most 0.10 / 0.50 beam FWHM |
| Duplicate fraction | at most 0.02 |
| Mask precision / recall / IoU | at least 0.85 / 0.90 / 0.80 |
| Island split / merge fraction | at most 0.10 / 0.10 |
| Rapthor retained/rejected component agreement | at least 0.995 |

Low-SNR threshold crossings remain report-only completeness and reliability
curves. The same result must also be non-inferior to each PyBDSF reference.
The one-sided 95% upper regression limits must remain within these practical
margins:

| Paired metric | Maximum regression |
| --- | ---: |
| Completeness or reliability loss | 0.02 |
| Integrated-flux error increase | 0.05 |
| Position-error increase | 0.05 beam FWHM |
| Duplicate-fraction increase | 0.01 |
| Mask-IoU loss | 0.05 |
| Split- or merge-fraction increase | 0.02 |
| Rapthor decision-disagreement increase | 0.005 |

The frozen design requires at least 400 independent noise-image
realizations, a 90% minimum joint power target, whole-image fixed-seed
bootstrap intervals with 10,000 resamples, retained failure denominators, and
one terminal opening. Independent development/regression estimates must pass
the pre-opening power audit before qualification results are generated. If
they do not, this population remains unopened and any replacement design must
be frozen under a new identity rather than silently changing this manifest.

## Review decision

**Decision:** approve the contract, datasets, metrics, practical margins, and
statistical design for Phase 5 development. The design is deliberately broad
enough to reject a compact-only solution and narrow enough to test the
Rapthor-used MFS three-scale scope. Its absolute truth gates prevent PyBDSF
compatibility from legitimizing poor extended flux or topology.

Residual risks are explicit:

- Gaussian-basis morphology does not replace controlled real-residual or
  realistic complex-source injection.
- The 50% support threshold and numerical margins are reviewed-development
  values; opening qualification requires the registered power audit and
  independent review remains a cutover gate.
- Step 2C-A left five astrometry tails above the old gate. Step 2C-H corrected
  the nested tail statistic and omitted median endpoint prospectively, but its
  two candidates still failed endpoint and coverage strata on fresh
  development data.
- The Step 2C-HR technical review found that those offsets were unbiased and
  that the former target conflated compact-component astrometry with the
  threshold-dependent location of irregular emission. The new half-beam tail
  is a segment-repeatability gate and does not replace the compact 0.10/0.25
  astrometry requirement.
- The internal records and product constructors establish development
  semantics, not a stable public API or a qualification result.

The Step 2C-H human decision approved the
[technical pre-review](phase-5-astrometry-pre-review.md). The prospective
protocol then compared its two frozen candidates on 40 fresh development
images. The direct estimator's overall median/p95 was 0.0974/0.2730 beam; the
model-assisted result was 0.0860/0.3068 beam. Both had stratum failures, so the
decision in `config/contracts/phase-5-astrometry-selection-decision.json` is
`reject-astrometry-candidates`. The viewed Step 2C-A population remains closed
and the fresh 400-image confirmation remains sealed. Step 2C-P execution and
Step 3 remain blocked.

The later Step 2C-HR
[development review](phase-5-astrometry-follow-up-development-review.md)
evaluated the frozen detected-segment centroid on 80 new images and 480
eligible astronomical groups. All 60 endpoints passed. Overall x/y bias upper
bounds were 0.0105/0.0147 beam, and the radial-p95 upper bound was 0.3183 beam.
The shell cohort was limiting at 0.4887 against the 0.50-beam gate. The
technical decision retains the candidate for named human scientific review;
Gemma Danks subsequently approved confirmation-only execution. It does not
authorize external-finder comparison.

The single Step 2C-HR
[confirmation](phase-5-astrometry-follow-up-confirmation-review.md) passed all
60 endpoints. Overall x/y bias upper bounds were 0.0043/0.0041 beam and the
radial-p95 upper bound was 0.3103 beam. The independently repeated limiting
shell/tile-corner bound was 0.4883 beam. The reviewed decision confirms the
candidate for Step 2C-P protocol design only; external execution remains
closed.

The [Step 2C-P external protocol](phase-5-external-comparison-protocol.md)
freezes 1,400 fresh seed-disjoint images, the exact PyBDSF and Aegean
runtimes, operational and controlled-background configurations, truth-first
matching, metric scope, and a 0.9082 conservative joint-power lower bound.
Execution remains closed until the matcher and isolated runners are committed
and hash-bound.

## Frozen identities

| Document | SHA-256 |
| --- | --- |
| Multiscale contract | `7e79935d4870223d9448efb8c98407de63ecb148d98a4b8f5ef5c684cf55c5fe` |
| Filter-selection decision | `38c2340c1e49a30178dd866bcb587f8f0bcd9cfc00e76bb496e6e93da5ed4e46` |
| Paired filter-review protocol | `749d2393c485239bea6a897beaeb4a97b0b8ab7d8aff851646e43e857b4c993d` |
| Scientific gates | `cbf467f517af40be798eb4cfbf68315b7b5a11f96688af51973730f7b9cef70b` |
| Development manifest | `b3c9594efa0c39ce30f3b287988f3fca90f69c5ccb8507adc463b37fed0b8350` |
| Regression manifest | `7188b1c65b7d193e27f5bca3cf5b427874f97cea87fb206000a591460f95b85e` |
| Step 2C-A confirmation manifest | `7576f8e6e373b12a42c9820ee381750c32208444682bde4a52a1311cccfc6011` |
| Step 2C-A review protocol | `b7bcf5d85cef13fea7a32a4128ab7cb89f1a90bb8f4e066ab3cda618aae2220b` |
| Successor astrometry review protocol | `de7265384d8c591e776bbd21bd5488e68144ee8d3dd670277f496dea46a5d917` |
| Successor astrometry development manifest | `5e9da7471f9ca33053421bf3fed6e9583e4ac0e9c3a0b230cd15f48b35159636` |
| Successor astrometry confirmation manifest | `0cb216ad04469169a45a19e0d2b9eb51b84d4fee6f03ffd6dccce413c00659f7` |
| Successor astrometry selection decision | `567512af8220c041767d08f6313b8ccc62b0f429e77758f2e39075751314a2a5` |
| Step 2C-HR position protocol | `0fec937aeb90dec119993529af04fb5a431aeb070ab483d713abf8c91972037f` |
| Step 2C-HR development manifest | `c96faa8e6bf15bd324a56a5ca37c036f5361f678d1722d6d775c8a2e929587eb` |
| Step 2C-HR sealed confirmation manifest | `0e0c360a95044e155b489670d50de6c0ef41ccb3b314354a56388e208d2b87c7` |
| Step 2C-HR development decision | `cd6d54cf1c22daf3d68423bc931b58bb81ec192d30ec9c1472bdabcd22969c72` |
| Step 2C-HR human confirmation decision | `02124201a45ecc9e88ac9542de1f6ee0fa5a5a0a43759247bc696c68170664ab` |
| Step 2C-HR confirmation decision | `61eff7dd2c3785a82b3048ebdfc88a3f6004f34e1b1183be2e409ceab4094b75` |
| Step 2C-P external comparison protocol | `7c981658195f70cbe710b608746a9568bf57efbabb00ada54f5d3dffdbc89f6d` |
| Step 2C-P continuum manifest | `9f88b8904b264e61c5a7445fd8a0cc966cf928d072d010dce3c6d47b6e8e6193` |
| Step 2C-P compact/blend manifest | `55c6ecef09711219e45f3e6192cea130b17a02bded6b10e72e1a839743ce2e32` |
| Qualification manifest | `40f1d0cfd173947e323cc35ff140c04f25fdd5c8303fbab8c138dc058fb0235f` |
| Development complete dataset record | `319b43f99e0ff5d771f1f79721eb228b82f5e478d921f9dad6f0a2f1caf8d13d` |
| Regression complete dataset record | `70a7288ccd6230695f906e40d51a3509497ac4f88ba4e94e1174a29ef4017ec5` |
| Qualification complete dataset record | `b93b0b180341bdeeb4a4ee18398e5203ef83437375b731c8e4bbc550017216a1` |

## Scientific basis

- [ASKAP/EMU Source Finding Data Challenge](https://doi.org/10.1017/pasa.2015.37)
- [ATLAS Data Release 3](https://doi.org/10.1093/mnras/stv1866)
- [ProFound radio source-finding comparison](https://academic.oup.com/mnras/article/487/3/3971/5511783)
- [SKA Science Data Challenge 1 results](https://academic.oup.com/mnras/article/500/3/3821/5918002)
- [PyBDSF process documentation](https://pybdsf.readthedocs.io/en/latest/process_image.html)
- [Aegean compact source-finding method](https://doi.org/10.1111/j.1365-2966.2012.20768.x)
- [Aegean 2.0](https://doi.org/10.1017/pasa.2018.3)

These sources motivate truth-based, morphology-stratified completeness,
reliability, flux, and topology evaluation. They do not make any one source
finder scientific ground truth.
