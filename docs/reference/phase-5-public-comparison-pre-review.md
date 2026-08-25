# Phase 5 public comparison pre-review

**Status:** proposed before human review, data acquisition, checksum freeze,
or execution. This review does not open the untouched Phase 5 qualification
population and does not authorize a public-data run or backend cutover.

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

The acquisition implementation must translate the qualitative stratum names
above into exact units and formulas from the downloaded SDC1 schema and put
those formulas in a reviewed amendment before it may create the population.
If the public files or columns do not match the documented release, it fails
before any candidate execution. Selection may not depend on a Hebog product.

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

- a write-once acquisition and population manifest;
- explicit SDC1 column/unit mappings and exact cut-out ranking formulas;
- a finder-neutral SDC1 association adapter;
- a Hydra catalogue adapter that preserves native finder and island identity;
- result population and checksum verification; and
- a terminal evaluator that keeps qualification and cutover false.

Named scientific review must approve this dataset selection and the exact
post-acquisition amendment. Independent radio-astronomy review must then
interpret the completed evidence before the Phase 5 readiness record can
pass. Neither approval authorizes opening the untouched qualification
population; that remains a separate one-look decision.

## Decision

Recommend SDC1 plus ASKAP/Hydra. Do not add LoTSS or another survey merely to
increase the finder count: the two selected lanes already meet the telescope-
family requirement and have complementary truth roles. A third survey is
appropriate later if independent review identifies a frequency, instrument,
or morphology gap that materially affects readiness.
