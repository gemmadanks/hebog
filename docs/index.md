# Hebog

Hebog is a Dask-aware radio-continuum source finder for SKA Science Data
Processor pipelines. It is being developed first as a faster, scientifically
compatible replacement for the PyBDSF work performed by Rapthor's
`filter_skymodel` task.

Its scope is deliberately limited to the behaviour and products Rapthor consumes,
with a target of reducing the complete filter step's matched median wall time
by at least 50% relative to released PyBDSF and also outperforming a pinned
PyBDSF `master` reference.

Scalability is a core requirement. Hebog's target architecture processes
images up to 100,000 by 100,000 pixels as bounded haloed tiles and distributes
them across 100 to several hundred nodes on an existing Dask cluster, without
materialising a complete plane on any worker.
Production nodes are expected to provide hundreds of GB of RAM, which the
executor can use for larger bounded batches and caches without changing
scientific partition ownership.

## Current status

The public records, configuration, executor interface, serial and Dask
executors, CLI, test lanes, and delivery plan are scaffolded. Scientific
source-finding algorithms are not implemented yet.

Start with the [quick start](tutorials/index.md), read the
[architecture](explanation/index.md), or review the complete
[implementation plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md)
and [execution log](https://github.com/gemmadanks/hebog/blob/main/LOG.md).
