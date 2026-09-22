# Python API

This is the supported public API. Start with the
[tutorial](../tutorials/find-sources.md); see
[capability and status](release-status.md) for current limits. The API is
experimental and can change between `0.x` releases.

| Need | Use |
| --- | --- |
| Run the finder | `hebog.find_sources`, `hebog.SourceFinderRequest`, `hebog.SourceFinderConfig` |
| Choose where work runs | `hebog.executors` |
| Read products | `hebog.io.read_catalogue_fits_product`, `hebog.io.read_diagnostics_product` |
| Handle failures | `hebog.SourceFinderError` and its subclasses |

Developers extending Hebog will also want the
[internal API](internal-api.md).

## Top-level package

::: hebog
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

## Reading products and images

::: hebog.io
    options:
      show_symbol_type_toc: true

## Errors and entry point

::: hebog.pipeline
    options:
      show_symbol_type_toc: true
