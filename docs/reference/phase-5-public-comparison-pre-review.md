# Phase 5 public comparison pre-review

**Status:** acquisition, schema review, adapter implementation, and the exact
selected population completed on 2026-08-25. A no-science public-finder
execution pre-review is now ready for named implementation review. Finder
execution, compilation, evaluation, tuning, cutover, and release remain
unauthorized.

## Recommendation

Use two complementary public lanes rather than treating agreement among
source finders as truth:

1. the 1.4-GHz, 1000-hour SKA Science Data Challenge 1 image provides
   truth-bearing simulated SKA-MID evidence; and
2. the published two-degree ASKAP EMU Pilot Hydra field provides real-survey
   evidence and the published Aegean, Caesar, ProFound, PyBDSF, and Selavy
   products.

This is the smallest design that covers two telescope families, analytic
truth versus real imaging systematics, compact and extended populations, and
community-standard comparators. It also avoids inventing a common catalogue
from incompatible finder semantics.

The machine-readable recommendation is
`config/contracts/phase-5-public-comparison.json`. It names every upstream
artifact but deliberately contains no artifact checksum: every download must
be SHA-256 bound before cut-out selection or finder execution. The contract
therefore remains execution-disabled.

The named approval and exact seven direct-download requests are frozen in
`config/contracts/phase-5-public-comparison-scientific-decision.json`. That
record authorizes acquisition only and binds 15,053,995,875 expected bytes;
all scientific execution flags remain false.

The terminal acquisition record has SHA-256 `a74e60de...`: all seven files
match their exact byte sizes and source SHA-256 values. The checked schema
review has SHA-256 `409318f5...` and binds inspector SHA-256 `074e4df9...`.
It records a 32,768-square, 0.6-arcsec-beam SDC1 image and its 12-column truth
schema, nine applicable submitted catalogues, matched 3,600-square Hydra
deep/shallow images, and ten published catalogues across Aegean, Caesar,
ProFound, PyBDSF, and Selavy. The inspector read headers, table schemas, and
archive layout only; it did not read image pixels, catalogue distributions,
or finder products.

A procedural deviation is retained in the machine record: while the final
Hydra archive was still downloading, headers and the first five truth rows of
already complete exact-sized files were inspected before the aggregate record
sealed. No pixel arrays, finder products, or catalogue distributions were
inspected, and observed values did not inform the proposed formulas. The
deviation is not concealed or treated as approval to select cut-outs.

The repository's required JSON formatter later canonicalized the acquisition
decision's object-key order and whitespace. Serialization amendment SHA-256
`243d1680...` retains the historically approved byte hash `7bfd3866...`, binds
the canonical byte hash `d5762063...`, and validates that all seven requests
and every authorization flag are unchanged. It neither reopens the sealed
acquisition nor grants scientific execution authority.

## Why these datasets

The [official SDC1 release](https://www.skao.int/en/464/ska-science-data-challenge-1)
provides total-intensity simulations at three SKA-MID frequencies and three
depths, ancillary beam products, revealed truth catalogues, submitted team
catalogues, and a scoring implementation. Its 1.4-GHz, 1000-hour product is
the most direct public test of Hebog's intended SKA continuum domain. The
official truth is an independent oracle; submitted catalogues remain
comparators, not votes.

[Bonaldi et al. (2021)](https://doi.org/10.1093/mnras/staa3023) show that SDC1
contains crowded and morphologically complex source populations and that
performance depends on source properties and observing depth. The official
score includes source-population classification, which Hebog does not
produce. The total score is therefore report-only. Matching completeness,
reliability, position, integrated flux, fitted extent, duplicate, and merge
metrics use the already frozen Phase 5 meanings where the SDC1 fields are
semantically compatible.

The [CIRADA Hydra release](https://cirada.ca/hydra) publishes a real ASKAP EMU
Pilot deep image, a controlled shallow image, and the associated multi-finder
archive. [Hydra I](https://doi.org/10.1017/pasa.2023.24) defines the
deep/shallow and inverted-image comparison framework. [Hydra II](https://doi.org/10.1017/pasa.2023.29)
applies it to Aegean, Caesar, ProFound, PyBDSF, and Selavy and reports
finder-specific differences in completeness, reliability, flux, size, and
complex-source behaviour. These published products make Selavy especially
appropriate for ASKAP data and make ProFound and Caesar useful diagnostics
for complex emission.

The real EMU field has no astronomical truth catalogue. Deep-image detections,
Hydra's deep/shallow metrics, and cross-finder agreement are useful external
validity evidence, but none can establish an absolute pass. Each finder is
reported separately and unmatched objects remain auditable.

## Frozen scientific roles

| Lane | Role | Binding evidence | Diagnostic evidence |
| --- | --- | --- | --- |
| SKA SDC1 1.4 GHz, 1000 h | Truth-bearing public challenge | Frozen Phase 5 absolute gates where the catalogue fields have matching meanings | Official SDC1 score, population classification, and submitted-team comparisons |
| ASKAP EMU Pilot Hydra 2-degree field | Real-survey external validity | None: there is no ground truth | Hebog deep/shallow stability, each published finder separately, residual summaries, and unmatched-source audit |

There is no cross-metric, cross-finder, or cross-lane compensation. A public
comparator cannot excuse an SDC1 absolute failure. Conversely, a disagreement
with Selavy, ProFound, Caesar, Aegean, or PyBDSF is not automatically a Hebog
failure; it requires morphology-aware review of the image, residual, and
association semantics.

## SDC1 selection before Hebog

The full SDC1 image is approximately 4 GB. Phase 5 will use eight disjoint,
aligned 2048-square cut-outs so this public-science check does not silently
become the Phase 6 distributed-scale qualification.

After the image, primary beam, truth catalogue, and submitted-catalogue archive
have been downloaded and hashed, but before Hebog or any newly run reference
finder is executed:

1. admit only complete tiles whose mean primary-beam response is at least
   0.5;
2. derive tile attributes only from the official truth catalogue and fixed
   image/WCS/beam metadata;
3. select one unique tile for each of `sparse`, `ordinary`, `crowded`,
   `resolved`, `close-pair`, `high-dynamic-range`, `low-apparent-SNR`, and
   `primary-beam-boundary`, in that order;
4. rank low, median, or high according to the named attribute and break ties
   by increasing global pixel `(y, x)`; if a tile has already been selected,
   take the next ranked unique tile; and
5. seal source SHA-256 values, pixel bounds, WCS and beam metadata, truth
   membership, selection attributes, and cut-out SHA-256 values in a
   write-once population record.

The pending amendment now makes the formulas exact. Truth membership uses
centroid WCS coordinates and half-open tile bounds. SDC1 size codes are
converted to Gaussian FWHM with `2.355/5`, identity, or `sqrt(2)`; apparent
flux includes bilinearly interpolated primary-beam response. Peak SNR uses the
convolved Gaussian area, the FITS 0.6-arcsec beam, and the published
73-nJy/beam 1400-MHz/1000-hour noise. Empty-tile fractions and dynamic range
are zero, closest-pair separation is infinite below two sources, and all ties
use increasing global tile `(y, x)`. The official population class remains a
report-only code because Hebog does not classify sources. Selection still may
not begin until named review accepts this amendment.

## ASKAP/Hydra execution

Use the complete published deep and shallow two-degree images, not a
candidate-selected crop. Run Hebog with one frozen configuration on both
images. Compare deep/shallow stability within Hebog and reproduce Hydra's
published summaries for every finder where the archive provides the required
fields.

Report at least:

- catalogue overlap and unmatched components for each finder separately;
- deep-to-shallow completeness and reliability surrogates;
- position and flux ratios stratified by SNR and source complexity;
- residual RMS, MADFM, and squared-residual summaries where semantics match;
- edge, blend, compact, extended/diffuse, and bright-source case studies; and
- unavailable metrics explicitly, especially incomplete island semantics.

Do not rerun the five Hydra finders merely to force them onto Hebog's
configuration. The published finder-specific optimization is part of the
Hydra result and must be recorded as such. A separate like-configuration run
would be a different experiment requiring its own frozen identities.

## Evidence and review boundary

Raw public products, cut-outs, catalogues, and generated results remain
ignored benchmark evidence. The durable repository retains only acquisition
URLs, source and cut-out hashes, exact software/configuration identities,
metric definitions, compact summaries, and reproducible commands. Before
execution, the implementation must add and validate:

- ~~a write-once acquisition manifest and checksum freeze;~~ complete;
- ~~explicit SDC1 column/unit mappings and exact ranking proposal;~~ complete
  and approved by schema/selection review `409318f5...`;
- ~~a write-once selected cut-out population manifest;~~ complete as terminal
  population `0a7c2b18...`, with 32 admitted and eight selected tiles;
- ~~a finder-neutral SDC1 association adapter;~~ complete;
- ~~a Hydra catalogue adapter that preserves native finder and island
  identity;~~ complete;
- result population and checksum verification; and
- a terminal evaluator that keeps qualification and cutover false.

Named scientific review has approved the dataset, exact post-acquisition
schema, selection formulas, adapters, and one selected population. The sole
official truth row with a non-finite centroid (ID `32397377`) cannot satisfy
half-open tile membership and is recorded explicitly as excluded. All seven
source identities, eight FITS checksums, truth memberships, disjointness, and
implementation hashes verify. A separate frozen public finder protocol and
named execution approval are still required. Independent radio-astronomy
review must interpret the completed public evidence before the Phase 5
readiness record can pass; public selection did not authorize qualification,
cutover, or release.

## Public finder execution pre-review

The no-science execution pre-review is
`config/contracts/phase-5-public-finder-execution-pre-review.json`, SHA-256
`476265e1b4e4ef1356f62a1b31ce4eb4ba3db995c84feddd8134da94bdb5ce4a`.
It binds the passing final-qualification candidate and runtime to selected
population `0a7c2b18...`, but authorizes no implementation or execution.

The recommended program has ten Hebog runs: eight selected SDC1 output cores
and the complete Hydra deep and shallow images. It reuses the published SDC1
truth and Hydra finder catalogues; it does not rerun the comparison finders.
Hebog must estimate its own background and RMS with the frozen candidate
configuration. Each SDC1 run reads its frozen stage-specific halo from the
parent image, while candidate and truth admission remain bound to the selected
half-open output core.

SDC1 is the only binding truth lane. It uses maximum-cardinality association,
then matched flux, then separation, with a maximum separation of half the
0.6-arcsecond restoring beam. Truth requires a finite centroid in the output
core and apparent peak signal-to-noise ratio of at least five after the
approved primary-beam attenuation. Halo truth may explain a core candidate
but cannot contribute to completeness. Candidate admission is by centroid in
the output core. The overall population and every one of the eight selected
strata must pass independently; compensation between strata is forbidden.

| Binding SDC1 endpoint | Limit |
| --- | ---: |
| Completeness | at least 0.90 |
| Reliability | at least 0.95 |
| Duplicate fraction | at most 0.02 |
| Merge fraction | at most 0.10 |
| Median absolute integrated-flux error | at most 0.10 |
| 95th-percentile absolute integrated-flux error | at most 0.25 |
| Absolute mean x and y position offsets | at most 0.10 beam |
| 95th-percentile radial position error | at most 0.50 beam |

Axis and position-angle errors remain diagnostics because Phase 5 has no
frozen axis-error limit. The Hydra lane is also non-binding: it reports exact
pairwise overlap, position, flux-ratio, and unmatched-candidate diagnostics
for Hebog deep versus shallow, Hebog versus each published finder at each
depth, and each published finder deep versus shallow. Missing native fields
remain explicit, and the evaluator must not invent a Hebog residual proxy.

Two named approval boundaries remain:

1. approve implementation and validation of the protocol, runner, compiler,
   and evaluator, then freeze their exact non-executable identities; and
2. separately approve those exact identities before one public finder
   campaign, compilation, and evaluation.

Suggested first approval:

> I approve the Phase 5 public finder execution pre-review SHA-256
> `476265e1b4e4ef1356f62a1b31ce4eb4ba3db995c84feddd8134da94bdb5ce4a`
> and its recommendations. This authorizes implementation and validation of
> the public protocol, Hebog runner, compiler, and evaluator, followed by
> freezing exact non-executable identities against selected population
> `0a7c2b18...` and the qualified Hebog runtime. It does not authorize finder
> execution, compilation or evaluation of public results, optimization,
> tuning, rescoring, cutover, or release.

## Decision

Recommend SDC1 plus ASKAP/Hydra. Do not add LoTSS or another survey merely to
increase the finder count: the two selected lanes already meet the telescope-
family requirement and have complementary truth roles. A third survey is
appropriate later if independent review identifies a frequency, instrument,
or morphology gap that materially affects readiness.
