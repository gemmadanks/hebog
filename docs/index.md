# Hebog

Hebog is an **experimental** Dask-aware radio-continuum source finder for SKA
Science Data Processor pipelines. It is being developed as a scientifically
compatible, faster alternative to the PyBDSF work used by Rapthor's
`filter_skymodel` step. Its scientific library also works independently of
Rapthor, Prefect and LSMTool.

## Current capability

The public finder reads one ICRS `Jy/beam` FITS image up to 1,024 pixels on
either spatial axis and publishes a catalogue, RMS image, source mask and
diagnostics. It implements background/noise estimation, compact and multiscale
detection, Gaussian fitting and associated-source measurements. Use Serial
execution or supply an existing Dask client; Hebog does not create a cluster.

The current composition is scientifically unqualified. Compact measurement,
uncertainty and faint extended-source association/photometry risks remain
under review. Earlier campaign passes apply only to their exact candidates.
See [current capability and release status](reference/release-status.md) for
the supported input envelope, limitations and evidence boundaries.

- [Find sources in a FITS image](tutorials/find-sources.md)
- [Install and get started](tutorials/index.md)
- [Public API](reference/index.md)
- [Remaining merge and release tasks](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md)

## Delivery direction

Hebog will ship useful experimental `0.x` increments as their scoped checks
pass. General scientific qualification, Rapthor integration and larger-image
support are separate increments; the experimental label never excuses a
confirmed incorrect supported output.

For supported Rapthor deployment, the target is at least a 50% reduction in
matched median complete `filter_skymodel` time relative to released PyBDSF,
and better performance than pinned PyBDSF `master`. Those confidence-bound
gates remain unproven for the current complete workflow. Individual-stage
speed measurements cannot establish them.

The scale target is 100,000-by-100,000-pixel images across 100 to several
hundred nodes with bounded Zarr tiles and hierarchical reconciliation.
Production nodes are expected to have hundreds of GB of RAM. This is an
architecture and qualification target, beyond the current public size limit.
See the [architecture](architecture/index.md) and
[performance/scale contracts](reference/performance-scalability-contracts.md).

Current science is summarized in the
[campaign overview](reference/phase-5-campaign-overview.md). Dated evidence
reviews remain available under Reference; development chronology belongs in
the [execution log](https://github.com/gemmadanks/hebog/blob/main/LOG.md).
