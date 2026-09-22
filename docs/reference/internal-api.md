# Internal API

This page is for developers working on Hebog. These modules are **not** a
supported public interface and change without notice. The
[architecture overview](../architecture/index.md) explains how the layers fit
together.

## Configuration

::: hebog.config
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

::: hebog.adapters.rapthor_products
    options:
      show_symbol_type_toc: true

## Validation contracts

::: hebog.validation.contracts
    options:
      show_symbol_type_toc: true
