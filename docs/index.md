# Hebog

Hebog is an **experimental** Dask-aware radio-continuum source finder for SKA
Science Data Processor pipelines. It is being developed as a scientifically
compatible, faster alternative to the PyBDSF work used by Rapthor's
`filter_skymodel` step. Its scientific library also works independently of
Rapthor, Prefect and LSMTool.

## What Hebog does

The public finder reads one ICRS or FK5 J2000 `Jy/beam` FITS image up to 1,024 pixels on
either spatial axis and publishes a catalogue, RMS image, source mask and
diagnostics. It implements background/noise estimation, compact and multiscale
detection, Gaussian fitting and associated-source measurements. Use Serial
execution or supply an existing Dask client; Hebog does not create a cluster.

Hebog is experimental and not yet scientifically qualified. Treat its outputs as
measurements to evaluate, not as established astrophysical truth or automatic
evidence that a survey configuration is suitable. See
[current capability and release status](reference/release-status.md) for the
supported input envelope and known limitations.

- [Find sources in a FITS image](tutorials/find-sources.md)
- [See how the finder makes each decision](explanation/how-hebog-works.md)
- [Interpret every public output field](reference/public-products.md)
- [Install and get started](tutorials/index.md)
- [Public API](reference/index.md)

## Where it fits

The scientific library is independent of Rapthor, Prefect, and LSMTool. A
pipeline supplies a serial executor or an existing Dask client and receives
small records pointing to closed files. Hebog does not create a cluster,
filter a sky model, or place scheduler objects in public results. See the
[architecture](architecture/index.md) for execution and ownership boundaries.
