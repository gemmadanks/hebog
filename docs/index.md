# Hebog

Hebog is a Dask-aware radio-continuum source finder for SKA Science Data
Processor pipelines. It is being developed first as a faster, scientifically
compatible replacement for the PyBDSF work performed by Rapthor's
`filter_skymodel` task.

Its scope is deliberately limited to the behaviour and products Rapthor consumes,
with a target of reducing the complete filter step's matched median wall time
by at least 50%.

## Current status

The public records, configuration, executor interface, serial and Dask
executors, CLI, test lanes, and delivery plan are scaffolded. Scientific
source-finding algorithms are not implemented yet.

Start with the [quick start](tutorials/index.md), read the
[architecture](explanation/index.md), or review the complete
[implementation plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md).
