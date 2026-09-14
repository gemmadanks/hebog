# How Hebog has been developed

*A short account of the recorded development through 12 September 2026.*

Hebog finds objects that emit radio waves in telescope images and measures
their positions, brightness and sizes. It began in July 2026 with a practical
question: could the source-finding work used by Rapthor, a radio-image
processing workflow, become substantially faster while keeping trustworthy
scientific results?

## From measurements to a working finder

The first step was to measure where the existing tool, PyBDSF, spent its time.
Estimating noise and searching for structures of different sizes dominated
the investigated workload. This shaped the priorities: independently build
the capabilities Rapthor needs and improve the whole workflow's speed.

Development proceeded in stages: establish comparison data and rules; read
large images in manageable pieces; estimate background and noise; detect
compact objects; then measure them and produce catalogues. These stages led
to incremental experimental releases. From August onward, the main challenge
became extended emission: faint clouds, rings and filaments that cannot be
described well as isolated bright spots.

Images are divided into manageable tiles, with neighbouring pixels included
to handle objects crossing their edges. Dask shares work among workers, while
Zarr storage allows image pieces to be read independently. These choices lay
the foundations for images too large to fit in one computer's memory.

## The algorithms we chose

- **Background and noise:** estimate the underlying level and random variation
  in local patches, repeatedly excluding unusually extreme values, then blend
  the estimates across the image. Smaller patches refine estimates near bright
  objects. Later work protects real source emission from being mistaken for
  background or noise.
- **Compact objects:** start at clearly significant bright pixels and grow
  into neighbouring, fainter pixels. Separate overlapping objects using their
  peaks and the brightness dips between them. Fit elliptical bell-shaped
  models, called Gaussians, to measure suitable compact objects.
- **Extended emission:** search what remains after compact models are
  subtracted at several levels of smoothing. The selected B3-spline wavelet
  method reveals structures of different sizes without reducing image
  resolution. Evidence across neighbouring scales helps connect related
  emission. Brightness measurements return to the original image after
  background subtraction, so the search filters do not define the measured
  brightness.

Published astronomy methods and controlled comparisons guided these choices.
An initially favoured template-based filter gave way to wavelets after broader
scientific comparisons and corrective studies. Established numerical tools
were preferred where they met the requirements.

## How decisions were tested

Small, reviewable changes usually began with a test describing the required
behaviour. Artificial images with known answers came first, followed by
simulated sources in noise and public astronomical data. Tests checked missed
objects, false detections, measurement errors, and incorrectly split or merged
objects, including near image edges and missing pixels.

Running the same image with different tiles, worker arrangements and retries
had to preserve the result. Comparisons used both the released and a fixed
development version of PyBDSF, plus Aegean where appropriate. None was treated
as scientific truth. The comparison tools themselves needed testing: several
failures exposed inconsistent definitions of sources or measurements.

For decisive studies, inputs, versions and acceptance rules were recorded
before examining results. Unseen test images were kept separate from
development examples; statistical checks assessed whether differences were
convincing. Failed studies remained in the record. Revised methods or rules
required new documented decisions, supported by scientific review.

## What the experience has shown

Compact-source milestones and an early extended-source qualification passed
their defined tests. Later public-data studies exposed missed faint sources,
incorrect grouping and measurement problems that those synthetic tests had
not revealed. This prompted repeated corrections and broader regression tests
to check that improvements did not lose earlier strengths.

Hebog remains experimental. Development closeout, scientific readiness and
release approval are separate decisions. See
[current release status](../reference/release-status.md) for current capability
and evidence; this account describes the development approach.
Halving Rapthor's complete processing time and scaling across hundreds of
machines remain goals to demonstrate. Timing studies use repeated matched
runs across image sizes; faster individual stages alone do not establish
the overall target.

For the detailed record, see the
[execution log](https://github.com/gemmadanks/hebog/blob/main/LOG.md),
[Git history](https://github.com/gemmadanks/hebog/commits/main/),
[current plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md)
and [Phase 5 campaign overview](../reference/phase-5-campaign-overview.md).
