# Hebog

[![CI](https://github.com/gemmadanks/hebog/actions/workflows/ci.yaml/badge.svg?branch=main)](https://github.com/gemmadanks/hebog/actions/workflows/ci.yaml)
[![release-please](https://github.com/gemmadanks/hebog/actions/workflows/release-please.yaml/badge.svg)](https://github.com/gemmadanks/hebog/actions/workflows/release-please.yaml)
[![Docs](https://github.com/gemmadanks/hebog/actions/workflows/docs-pages.yaml/badge.svg)](https://gemmadanks.github.io/hebog/)
[![codecov](https://codecov.io/gh/gemmadanks/hebog/graph/badge.svg)](https://codecov.io/gh/gemmadanks/hebog)
[![License](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](https://github.com/gemmadanks/hebog/blob/main/LICENSE)

Hebog is an **experimental** source finder for radio-continuum images. It
runs in a single process or on a Dask cluster. For each FITS image it:

1. estimates the background and noise;
2. detects compact and extended emission;
3. separates, fits and measures sources; and
4. publishes a source catalogue, a noise (RMS) image, a source mask and
   diagnostics.

[How Hebog finds sources](https://gemmadanks.github.io/hebog/explanation/how-hebog-works/)
explains each step with diagrams.

Hebog aims to be a fast, scalable source finder that is easily integrated into
next generation radio astronomy data processing pipelines such as
[Rapthor](https://github.com/darafferty/rapthor). It can also be used on its own from Python.

## Status

- **Experimental.** Releases are `0.x` and may change the API or output
  formats. Pin an exact version and read the
  [release notes](https://github.com/gemmadanks/hebog/releases) before
  upgrading.
- **Not yet scientifically qualified.** Hebog is compared against
  [PyBDSF](https://github.com/lofar-astron/PyBDSF) and
  [Aegean](https://github.com/PaulHancock/Aegean) on simulated images with
  known sources, but these checks are development evidence rather than qualification
  for survey use. See
  [scientific status](https://gemmadanks.github.io/hebog/reference/release-status/#scientific-status).
- **Supported inputs:** one FITS image in `Jy/beam` with ICRS or FK5 J2000 sky
  coordinates and at most 3,000 pixels on each side.

[Current capability and release status](https://gemmadanks.github.io/hebog/reference/release-status/)
lists the full input requirements and known limitations.

## Installation

Hebog is not on PyPI yet: its public input envelope is still too small to be
generally useful. Install a tagged release from GitHub into a Python 3.12 to
3.14 environment, replacing the tag with the
[release](https://github.com/gemmadanks/hebog/releases) you want:

```shell
pip install git+https://github.com/gemmadanks/hebog@v0.12.0
```

Releases are also uploaded to
[TestPyPI](https://test.pypi.org/project/hebog/) to exercise the publishing
workflow. That index is for testing only; install from it just to check
packaging, never for scientific work.

## Example

```python
from pathlib import Path

from hebog import SourceFinderConfig, SourceFinderRequest, find_sources
from hebog.executors import SerialExecutor

request = SourceFinderRequest(
    image_path=Path("image.fits"),
    output_directory=Path("output"),
    run_id="example",
)
config = SourceFinderConfig(
    detection_threshold_sigma=5.0,
    island_threshold_sigma=3.0,
    minimum_island_pixels=7,
)
result = find_sources(request, config, SerialExecutor())
print(result.catalogue_path, result.source_count)
```

The output directory must not already exist. The
[source-finding tutorial](https://gemmadanks.github.io/hebog/tutorials/find-sources/)
explains the settings, the products and how to run on Dask.

## Documentation

- [Find sources in a FITS image](https://gemmadanks.github.io/hebog/tutorials/find-sources/)
- [How Hebog finds sources](https://gemmadanks.github.io/hebog/explanation/how-hebog-works/)
- [Hebog and other source finders](https://gemmadanks.github.io/hebog/explanation/source-finder-comparison/)
- [Catalogue, image and diagnostic outputs](https://gemmadanks.github.io/hebog/reference/public-products/)
- [Interactive notebooks](https://gemmadanks.github.io/hebog/how-to/notebooks/)
- [Architecture](https://gemmadanks.github.io/hebog/architecture/)
- [How Hebog distributes work](https://gemmadanks.github.io/hebog/architecture/distributed-execution/)
- [Integrate Hebog into a pipeline](https://gemmadanks.github.io/hebog/how-to/integrate-into-a-pipeline/)
- [API reference](https://gemmadanks.github.io/hebog/reference/)

## Development

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and
[just](https://just.systems/), then:

```shell
git clone https://github.com/gemmadanks/hebog.git
cd hebog
uv sync --all-groups
just check    # formatting, linting, type checks and fast tests
just --list   # all test, documentation and packaging commands
```

Contributions use [Conventional Commits](https://www.conventionalcommits.org/).
[AGENTS.md](https://github.com/gemmadanks/hebog/blob/main/AGENTS.md) describes
the project's working rules, test suites and review checklist.

## Citation and licence

If Hebog contributes to your research, please cite it using
[CITATION.cff](https://github.com/gemmadanks/hebog/blob/main/CITATION.cff).
Hebog is distributed under the
[BSD 3-Clause License](https://github.com/gemmadanks/hebog/blob/main/LICENSE).
