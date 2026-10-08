# FAQ for developers and architects

This page is for people who build pipelines around Hebog or work on its
code, and assumes no radio astronomy. Most questions are answered on other
pages, linked in the first section. The rest of the page answers what those
pages do not: the background a newcomer needs, how a result can be checked
when no exact answer exists, and what Hebog depends on.

## Answered elsewhere

### Getting started

| Question | Answer |
| --- | --- |
| What does Hebog do? | [What Hebog is](../architecture/index.md#what-hebog-is) |
| What is Rapthor, and why is Hebog built for it? | [What Hebog is](../architecture/index.md#what-hebog-is), the [domain model](domain-model.md) and [ADR-003](../architecture/adr/003-limit-hebog-to-rapthor-source-finding-contract.md) |
| How do I install it, and on which platforms and Python versions? | [Install Hebog](../tutorials/index.md) |
| How do I run it once to see what it does? | [Find sources in a FITS image](../tutorials/find-sources.md) |
| What is the public API? | [Python API](../reference/index.md) |
| Where does the project stand, and what is left before 1.0.0? | [Progress against goals](../reference/progress-against-goals.md) |

### Calling Hebog from a pipeline

| Question | Answer |
| --- | --- |
| How do I call it, and what goes in and comes out? | [The contract in brief](../how-to/integrate-into-a-pipeline.md#the-contract-in-brief) |
| Do I need Dask, and which executor should I use? | [Choose an executor](../how-to/integrate-into-a-pipeline.md#1-choose-an-executor) |
| Will Hebog start its own cluster or processes? | [Who owns what](../architecture/distributed-execution.md#who-owns-what) and [ADR-004](../architecture/adr/004-keep-top-level-scheduling-in-rapthor.md) |
| Can one call analyse several images? | [System context](../architecture/index.md#system-context) |
| What storage do the workers need? | [Put files where workers can reach them](../how-to/integrate-into-a-pipeline.md#2-put-files-where-workers-can-reach-them) |
| How do I know the output is complete, and what does a failed or killed run leave? | [Treat the output directory as one atomic product](../how-to/integrate-into-a-pipeline.md#3-treat-the-output-directory-as-one-atomic-product) and [what a failed or killed run leaves](../reference/public-products.md#what-a-failed-or-killed-run-leaves) |
| Which exceptions can it raise, and which are worth retrying? | [Handle errors by type](../how-to/integrate-into-a-pipeline.md#4-handle-errors-by-type) |
| Is an empty catalogue a failure? | [Handle errors by type](../how-to/integrate-into-a-pipeline.md#4-handle-errors-by-type) and [persist and verify results](../how-to/integrate-into-a-pipeline.md#5-persist-and-verify-results) |
| What files does it write, and how do I read and verify them? | [Product set at a glance](../reference/public-products.md#product-set-at-a-glance) and [persist and verify results](../how-to/integrate-into-a-pipeline.md#5-persist-and-verify-results) |
| How large an image can it take, and how much memory does a run need? | [Supported inputs](../reference/release-status.md#supported-inputs-and-behaviour), [storage](../architecture/distributed-execution.md#storage) and [what a run allocates](../reference/performance-profile.md#what-a-run-allocates) |
| Is it faster than PyBDSF, and does it scale beyond one machine? | [Performance](../reference/progress-against-goals.md#performance) and [scalability](../reference/progress-against-goals.md#scalability) |
| Will an upgrade break my pipeline? | [Versioning](../how-to/integrate-into-a-pipeline.md#versioning) and [compatibility between releases](../reference/release-status.md#compatibility-between-releases) |
| Can Rapthor use it yet? | [Integration status](../reference/release-status.md#integration-status) and the [Rapthor source-finding contract](../reference/rapthor-source-finding-contract.md) |

### Design

| Question | Answer |
| --- | --- |
| How is the code organised, and where does new code go? | [Layers](../architecture/index.md#layers) |
| How is one image split across many machines? | [Tiles, cores and halos](../architecture/distributed-execution.md#tiles-cores-and-halos) and [passes](../architecture/distributed-execution.md#passes-where-the-global-steps-go) |
| Do the results depend on the number of workers or the tile size? | [Guarantees and how they are tested](../architecture/distributed-execution.md#guarantees-and-how-they-are-tested) |
| Why Zarr for intermediate data, and FITS only for input and output? | [Storage](../architecture/distributed-execution.md#storage) and [ADR-007](../architecture/adr/007-use-zarr-for-intermediate-image-storage.md) |
| Why not run PyBDSF on a cluster instead? | [Hebog and PyBDSF](source-finder-comparison.md#pybdsf) and the context of [ADR-005](../architecture/adr/005-scale-large-images-with-hierarchical-tiles.md) |
| Why does Hebog implement only part of what PyBDSF does? | [ADR-003](../architecture/adr/003-limit-hebog-to-rapthor-source-finding-contract.md) |
| Can I add an executor, a storage backend or an output format? | [The executor contract](../architecture/distributed-execution.md#the-executor-contract), [conventions a change must keep](../how-to/index.md#conventions-a-change-must-keep) and [ADR-006](../architecture/adr/006-isolate-compatibility-with-versioned-schemas.md) |
| Why is there no C++ or Rust? | [Native-code assessment](native-code-assessment.md) |
| Why are there no compatibility shims or deprecation periods? | [Why the code looks the way it does](quality-attributes.md#why-the-code-looks-the-way-it-does) |
| Why was each design decision made? | [Decision records](../architecture/adr/index.md) |

### Working on Hebog

| Question | Answer |
| --- | --- |
| How do I set up a checkout and run the checks? | [Set up a source checkout](../how-to/index.md#set-up-a-source-checkout) and [checks and test lanes](../how-to/index.md#checks-and-test-lanes) |
| How do I check that a change does not alter the science? | [Run the quick science check](../how-to/index.md#run-the-quick-science-check) |
| How do I measure a performance or memory change? | [Run the quick benchmark](../how-to/index.md#run-the-quick-benchmark), [measure the traced-allocation peak](../how-to/index.md#measure-the-traced-allocation-peak) and [profile complete execution](../how-to/index.md#profile-complete-execution) |
| Which rules must a change keep? | [Conventions a change must keep](../how-to/index.md#conventions-a-change-must-keep) and [quality attributes](quality-attributes.md) |
| What does a domain term mean? | [Glossary](../reference/domain-glossary.md) |
| How is a release published? | [Publish releases](../how-to/publish-releases.md) |

## Background for non-astronomers

### What do I need to know about radio images?

Enough to read the code's names and the products:

| Term | In plain terms |
| --- | --- |
| FITS | Astronomy's standard file format. Hebog's input is one FITS image: a two-dimensional array of brightness values and a header of keyword cards that describes them. Its catalogue output is a FITS file of tables. |
| WCS | The header's World Coordinate System: the mapping from pixel position to position on the sky, given as right ascension and declination, the sky's longitude and latitude. |
| Jy/beam | The brightness unit Hebog accepts: janskys (a unit of radio flux) per beam, the area of the blur described below. |
| Beam | The blur every radio image has: a point on the sky appears as a small ellipse, whose size the header states. It sets the finest detail the image shows, and Hebog refuses an image whose beam is [wider than 10 pixels](../reference/input-header-contract.md#limitations). |
| Noise and RMS | Every pixel holds signal plus random noise, whose level varies across the image. Hebog estimates the noise level locally, as a root mean square (RMS), and publishes that map as `rms.fits`. |
| σ thresholds | Thresholds are multiples of the local noise: 5σ means five times the local RMS above the local background level. |
| Island, Gaussian component and source | An island is a connected patch of pixels above the threshold. A Gaussian component is a two-dimensional bell-shaped model fitted to part of an island. A source is the group of components Hebog judges to be one object. The catalogue has one table for each, and they need not correspond one to one. |
| Mask | `source-mask.fits` marks the pixels of each detection. Rapthor uses a source finder's mask to keep only the entries of its sky model, the list of known sources it calibrates with, that lie on detected emission. |

[How Hebog finds sources](how-hebog-works.md) describes the processing in
astronomers' terms, and the [domain model](domain-model.md) the products
Rapthor uses.

### How can a result be checked when the sky has no answer key?

A real image has no list of the true sources in it, so Hebog is checked
against three references, none of them the whole truth:

- **Generated images with known contents.** Sources injected at known
  positions and brightness show how many are found, how many detections are
  real and how large the position and flux errors are. The
  [quick science check](../how-to/index.md#run-the-quick-science-check) runs
  such cases on every scientific change.
- **PyBDSF**, the finder Rapthor uses today. Agreement shows compatibility,
  not truth. The target is that Rapthor makes the same decisions downstream
  within measured limits, not that every number matches; the
  [scientific gates](../reference/progress-against-goals.md#gates) state the
  limits.
- **Hebog itself.** The serial executor is the reference, and every other
  executor and tiling must reproduce its products byte for byte
  ([guarantees](../architecture/distributed-execution.md#guarantees-and-how-they-are-tested)).

Passing tests, coverage and a successful run establish none of the first
two.

## Dependencies

### What does Hebog depend on?

Six runtime packages, declared with version bounds in `pyproject.toml`:

| Package | Used for |
| --- | --- |
| NumPy and SciPy | Arrays, filters, labelling and fitting |
| Astropy | FITS files and sky coordinates |
| Zarr | Intermediate image planes, only in `hebog.io` |
| pydantic | Validating records and their JSON |
| `distributed` (Dask) | `DaskExecutor` only: installed with Hebog, imported only when you request it |

Hebog itself is pure Python under the
[BSD-3-Clause licence](https://github.com/gemmadanks/hebog/blob/main/LICENSE),
so installing it needs no compiler. It does not import Rapthor,
Prefect or LSMTool, and a test keeps them out.
