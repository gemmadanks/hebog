# Internal API

This page is for developers working on Hebog. These modules are **not** a
supported public interface and change without notice. The
[architecture overview](../architecture/index.md) explains how the layers fit
together, and [How Hebog finds sources](../explanation/how-hebog-works.md)
explains the science.

The sections follow the order in which `hebog.find_sources` runs the stages.
Each stage module wraps pure kernels from `hebog.algorithms` with tiles,
halos and executor batches; `hebog.science` holds the reviewed profile and
the composition that turns the stage products into the catalogue.

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

## Workflow adapters

`hebog.adapters` holds the Rapthor compatibility records and the
eight-column catalogue codec. No adapter runs `find_sources` or writes its
products yet.

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
