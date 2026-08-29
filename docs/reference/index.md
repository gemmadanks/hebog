# API

Related project references:

- [Source-finding domain glossary](domain-glossary.md)
- [Internal catalogue and result schemas](internal-schemas.md)
- [Rapthor source-finding contract](rapthor-source-finding-contract.md)
- [Scientific pre-review findings](scientific-pre-review.md)
- [Phase 0 starting revisions](starting-revisions.md)
- [Phase 0 baseline results](phase-0-baseline-results.md)
- [Validation dataset manifests](dataset-manifests.md)
- [Scientific comparison reports](scientific-comparison.md)
- [Evidence documents](evidence-documents.md)
- [Performance and scalability contracts](performance-scalability-contracts.md)
- [Phase 0 review record](phase-0-review-record.md)
- [Phase 1 release readiness](phase-1-release-readiness.md)
- [Phase 2 release readiness](phase-2-release-readiness.md)
- [Phase 3 release readiness](phase-3-release-readiness.md)
- [Phase 3 scientific review record](phase-3-review-record.md)
- [Phase 4 release readiness](phase-4-release-readiness.md)
- [Phase 4 scientific review record](phase-4-review-record.md)
- [Phase 4 paired non-inferiority protocol](phase-4-paired-noninferiority.md)
- [Phase 4S compact qualification protocol](phase-4s-qualification-protocol.md)
- [Phase 4T compact confirmation protocol](phase-4t-confirmation-protocol.md)
- [Phase 4U compact-blend qualification protocol](phase-4u-qualification-protocol.md)
- [Phase 5 multiscale contract and development review](phase-5-contract.md)
- [Phase 5 scale-filter selection](phase-5-filter-selection.md)
- [Phase 5 regression fixtures](phase-5-regression-fixtures.md)
- [Phase 5 astrometry technical pre-review](phase-5-astrometry-pre-review.md)
- [Phase 5 public-finder source-association pre-review](phase-5-public-finder-source-association-pre-review.md)
- [Phase 5 public-finder source-association implementation](phase-5-public-finder-source-association-implementation.md)
- [Phase 5 source-association replay-composition pre-review](phase-5-public-finder-source-association-replay-composition-pre-review.md)
- [Phase 5 public-finder source-reconstruction pre-review](phase-5-public-finder-source-reconstruction-pre-review.md)
- [Phase 5 scientific campaign overview](phase-5-campaign-overview.md)
- [Phase 5 final-qualification evaluation-repair pre-review](phase-5-final-qualification-repair-pre-review.md)
- [Phase 5 release readiness](phase-5-release-readiness.md)
- [Compact deblending](compact-deblending.md)
- [Extended-emission measurement](extended-emission-measurement.md)
- [Compact moment measurement](compact-measurement.md)
- [Compact Gaussian fitting](compact-fitting.md)
- [Compact astrometry and beam deconvolution](compact-astrometry.md)
- [Compact catalogue and Rapthor FITS view](compact-catalogue.md)

## Top-level package

::: hebog
    options:
      show_symbol_type_toc: true

## Configuration

::: hebog.config
    options:
      show_symbol_type_toc: true

## Request and result records

::: hebog.data_models
    options:
      show_symbol_type_toc: true

## Executors

::: hebog.executors
    options:
      show_symbol_type_toc: true

## Pipeline

::: hebog.pipeline
    options:
      show_symbol_type_toc: true

## Image input

::: hebog.io
    options:
      show_symbol_type_toc: true

## Partition planning

::: hebog.algorithms.partitioning
    options:
      show_symbol_type_toc: true

## Background and RMS window statistics

::: hebog.algorithms.background
    options:
      show_symbol_type_toc: true

## Background and RMS execution stage

::: hebog.stages.background
    options:
      show_symbol_type_toc: true

## Detection and island topology

::: hebog.algorithms.detection
    options:
      show_symbol_type_toc: true

::: hebog.algorithms.labelling
    options:
      show_symbol_type_toc: true

::: hebog.algorithms.reconciliation
    options:
      show_symbol_type_toc: true

::: hebog.algorithms.deblending
    options:
      show_symbol_type_toc: true

## Residual multiscale detection

::: hebog.algorithms.multiscale
    options:
      show_symbol_type_toc: true

::: hebog.algorithms.extended_measurement
    options:
      show_symbol_type_toc: true

::: hebog.algorithms.measurement
    options:
      show_symbol_type_toc: true

## Compact-detection execution stage

::: hebog.stages.detection
    options:
      show_symbol_type_toc: true

## Compact measurement records and execution stage

::: hebog.data_models.measurement
    options:
      show_symbol_type_toc: true

::: hebog.stages.measurement
    options:
      show_symbol_type_toc: true

## Compact fitting and astrometry

::: hebog.data_models.fitting
    options:
      show_symbol_type_toc: true

::: hebog.algorithms.fitting
    options:
      show_symbol_type_toc: true

::: hebog.stages.fitting
    options:
      show_symbol_type_toc: true

::: hebog.data_models.astrometry
    options:
      show_symbol_type_toc: true

::: hebog.algorithms.astrometry
    options:
      show_symbol_type_toc: true

## Compact catalogue construction

::: hebog.data_models.catalogue_construction
    options:
      show_symbol_type_toc: true

::: hebog.algorithms.catalogue
    options:
      show_symbol_type_toc: true

::: hebog.stages.catalogue
    options:
      show_symbol_type_toc: true

## Workflow adapters

::: hebog.adapters.rapthor
    options:
      show_symbol_type_toc: true

::: hebog.adapters.rapthor_catalogue
    options:
      show_symbol_type_toc: true

## Validation contracts

::: hebog.validation.contracts
    options:
      show_symbol_type_toc: true
