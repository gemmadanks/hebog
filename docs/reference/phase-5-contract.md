# Phase 5 multiscale contract and development review

**Status:** reviewed for development and amended through the Step 2C-H
[astrometry pre-review](phase-5-astrometry-pre-review.md). Residual B3 passes
every paired gate and every absolute domain except five astrometry-variance
strata on the independent confirmation. The pre-review recommends prospective
endpoint, estimator, and uncertainty revision. Gemma Danks approved those
recommendations on 2026-08-09 for prospective development under
`config/contracts/phase-5-astrometry-human-decision.json`. Step 3 and
representation-specific optimization remain blocked pending fresh astrometry
confirmation and the Step 2C-P external source-finder comparison.
Qualification remains frozen and unopened; this contract does not establish
multiscale equivalence.

The 2026-08-08 community-practice review nominated residual B3-spline à trous
reconstruction, morphology-independent support growth, and original-image
measurement. Steps 2C through 2C-A evaluated it without changing the frozen
gates or opening qualification. The independent astrometry confirmation did
not pass, so the representation remains unselected.

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
- Unsupported scales fail at configuration validation. Unavailable
  measurements and ambiguous associations are typed omissions. Every accepted
  or deferred island requires one terminal disposition, and any incomplete
  result forbids catalogue publication.

The internal version-one records are `ScaleDetection`,
`CrossScaleAssociation`, `ExtendedEmissionMeasurement`, `MultiscaleOmission`,
`CombinedIslandDisposition`, and `CombinedCatalogueState`. They are strict,
immutable, scheduler-safe records; they contain no arrays, files, clients, or
mutable execution state.

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
| Median / 95th-percentile position error | at most 0.10 / 0.25 beam FWHM |
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
- Step 2C-A left five absolute astrometry tails above the frozen gate despite
  passing all paired endpoints. Curved-filament variance and uncertainty
  undercoverage require human scientific review before another estimator or
  endpoint design.
- The Step 2C-H technical pre-review found that the frozen position statistic
  nests a per-image group p95 inside a population p95, so its meaning changes
  with the number of groups in a stratum. It also found that the durable median
  position gate was not bound by the Step 2B--2C-A review implementation. These
  findings do not rescore the closed confirmation; a successor protocol must
  address them prospectively on fresh data.
- The internal records establish meanings, not a supported public API or
  completed combined catalogue implementation.

The Step 2C-H human decision approved the
[technical pre-review](phase-5-astrometry-pre-review.md). The prospective
successor design is now frozen in
`config/contracts/phase-5-astrometry-revision-review.json`, with a fresh
40-image development population and a sealed, seed-disjoint 400-image
confirmation population. Development may compare the direct-pixel and
covariance-gated model-assisted estimators. Confirmation remains unauthorized
until that comparison freezes one estimator. The viewed Step 2C-A confirmation
is closed to tuning, rescoring, and reuse. Step 2C-P execution and Step 3 remain
blocked until the successor astrometry gate passes.

## Frozen identities

| Document | SHA-256 |
| --- | --- |
| Multiscale contract | `1fbfb8e3026178dc539b5d0b76cec6f46d7bf73b67ac2a10ed3c77d0f3e092cd` |
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
