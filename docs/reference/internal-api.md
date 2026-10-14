# Internal API

This page is for developers working on Hebog. These modules are **not** a
supported public interface and change without notice. The
[architecture overview](../architecture/index.md) explains how the layers fit
together, and [How Hebog finds sources](../explanation/how-hebog-works.md)
explains the science.

The sections follow the order in which `hebog.find_sources` runs the stages.
Each stage module applies pure kernels from `hebog.algorithms` and
`hebog.science` with tiles, halos and executor batches, and
`hebog.stages.composition` runs the stages in order; its first section
documents it. `hebog.science` holds the
reviewed profile and configuration, the composition records and the
catalogue-row kernels; it imports no stage.

## The stage sequence

::: hebog.stages.composition
    options:
      show_symbol_type_toc: true

## Configuration and the reviewed profile

::: hebog.config
    options:
      show_symbol_type_toc: true

::: hebog.science.configuration
    options:
      show_symbol_type_toc: true

::: hebog.science.profile
    options:
      show_symbol_type_toc: true

## Partition planning

::: hebog.algorithms.partitioning
    options:
      show_symbol_type_toc: true

## Background and RMS

::: hebog.algorithms.background
    options:
      show_symbol_type_toc: true

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

::: hebog.stages.detection
    options:
      show_symbol_type_toc: true

## Residual multiscale detection

::: hebog.algorithms.multiscale
    options:
      show_symbol_type_toc: true

::: hebog.algorithms.multiscale_tiles
    options:
      show_symbol_type_toc: true

::: hebog.stages.multiscale
    options:
      show_symbol_type_toc: true

::: hebog.stages.support
    options:
      show_symbol_type_toc: true

## Published support

::: hebog.algorithms.extended_measurement
    options:
      show_symbol_type_toc: true

::: hebog.algorithms.owner_connectivity
    options:
      show_symbol_type_toc: true

::: hebog.stages.publication
    options:
      show_symbol_type_toc: true

## Components: deblending and fitting

::: hebog.algorithms.deblending
    options:
      show_symbol_type_toc: true

::: hebog.algorithms.component_topology
    options:
      show_symbol_type_toc: true

::: hebog.data_models.measurement
    options:
      show_symbol_type_toc: true

::: hebog.algorithms.measurement
    options:
      show_symbol_type_toc: true

::: hebog.data_models.fitting
    options:
      show_symbol_type_toc: true

::: hebog.algorithms.fitting
    options:
      show_symbol_type_toc: true

::: hebog.algorithms.component_measurement
    options:
      show_symbol_type_toc: true

::: hebog.stages.objects
    options:
      show_symbol_type_toc: true

## Source association

::: hebog.algorithms.multiscale_association
    options:
      show_symbol_type_toc: true

::: hebog.algorithms.source_association
    options:
      show_symbol_type_toc: true

::: hebog.stages.association
    options:
      show_symbol_type_toc: true

::: hebog.stages.sources
    options:
      show_symbol_type_toc: true

::: hebog.stages.islands
    options:
      show_symbol_type_toc: true

## Catalogue rows and astrometry

::: hebog.data_models.astrometry
    options:
      show_symbol_type_toc: true

::: hebog.algorithms.astrometry
    options:
      show_symbol_type_toc: true

::: hebog.science.catalogue_rows
    options:
      show_symbol_type_toc: true

::: hebog.science.catalogues
    options:
      show_symbol_type_toc: true

::: hebog.stages.catalogue_rows
    options:
      show_symbol_type_toc: true

::: hebog.science.continuum
    options:
      show_symbol_type_toc: true

## Source-count estimate

`hebog.expected_source_count` counts an image's bright local maxima before
an analysis, so that a caller can reserve `hebog.analysis_memory_bytes`
for them; these are its kernels.

::: hebog.algorithms.source_count
    options:
      show_symbol_type_toc: true

## Workflow adapters

`hebog.adapters.rapthor` runs one Rapthor sector through `find_sources` and
writes the files Rapthor's `filter_skymodel` step reads, under Rapthor's
names; `hebog.adapters.rapthor_catalogue` holds the eight-column catalogue
codec it writes them with, and `hebog.adapters.rapthor_comparison` compares
one sector's Hebog and PyBDSF products for Rapthor's dual-run mode. Rapthor
calls the adapter in the
[prepared local patch](https://github.com/gemmadanks/hebog/blob/main/scripts/validation/patches/README.md),
awaiting upstream publication and merge.

::: hebog.adapters.rapthor
    options:
      show_symbol_type_toc: true

::: hebog.adapters.rapthor_comparison
    options:
      show_symbol_type_toc: true

::: hebog.adapters.rapthor_catalogue
    options:
      show_symbol_type_toc: true
