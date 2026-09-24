# Hebog

Hebog is an **experimental** source finder for radio-continuum images. Given a
FITS image it estimates the background and noise, detects compact and extended
emission, fits Gaussians, and publishes a source catalogue, an RMS image, a
source mask and diagnostics. The same code runs in a single process or across
a Dask cluster that you already own.

!!! warning "Status"
    Hebog is not yet scientifically qualified and currently accepts images of
    at most 3,000 pixels per side. Treat its output as measurements to
    evaluate. See [capability and status](reference/release-status.md).

## I am an astronomer

- [Install Hebog](tutorials/index.md) and
  [find sources in your first image](tutorials/find-sources.md).
- [Choose thresholds and a profile](how-to/configure-a-run.md).
- [How Hebog finds sources](explanation/how-hebog-works.md): the algorithms,
  with diagrams.
- [Hebog and other source finders](explanation/source-finder-comparison.md):
  how it compares with PyBDSF, Aegean, Selavy and others.
- [Output reference](reference/public-products.md): every column, unit and
  flag.

## I am a pipeline developer or architect

- [Integrate Hebog into a pipeline](how-to/integrate-into-a-pipeline.md).
- [Architecture overview](architecture/index.md) and
  [how Hebog distributes work](architecture/distributed-execution.md).
- [Python API](reference/index.md).
- [Contribute to Hebog](how-to/index.md).

## How this documentation is organised

The documentation follows the [Diátaxis](https://diataxis.fr) framework. The
**User guide** holds the tutorial, how-to guides, explanation and reference an
astronomer needs. The **Developer guide** holds the same four kinds of page
for people who integrate or extend Hebog. Dated evidence and decisions live in
the repository's
[execution log](https://github.com/gemmadanks/hebog/blob/main/LOG.md), not in
these pages.
