# Native Rapthor integration container

This isolated Linux image installs a commit of Rapthor's Hebog branch, a
Hebog wheel and pinned LSMTool. It exercises the actual Prefect task, native
Hebog, LSMTool filtering, and the PyBDSF subprocess without adding those
workflow packages to Hebog's dependencies. The branch and its provenance are
in [the Rapthor branch guide](../../rapthor-integration/README.md).

Build the `localhost/hebog-lsmtool:156ae6a` base using
[the LSMTool recipe](../lsmtool/README.md) first. Its pin moved to LSMTool's
`master` head on 17 October 2026. The runtime dependency lock
includes LSMTool's `numpy<2.5` constraint. The native thread limit uses
`threadpoolctl`, already a mature dependency in the scientific Python stack;
Rapthor makes it an optional dependency beside Hebog. PyBDSF here is the
locked release 1.14.1: these are integration checks, not the matched
performance gate against pinned `master`.

## Build and verify

From the Hebog checkout, with any clone of Rapthor and the full hash of the
commit to test; the integration summary's `rapthor_commit` rebuilds the image
it records:

```bash
rapthor_checkout=/path/to/rapthor
rapthor_revision=<rapthor_commit>
git -C "$rapthor_checkout" fetch origin "$rapthor_revision"
context=$(mktemp -d)
cp scripts/validation/containers/rapthor/Containerfile \
  scripts/validation/containers/rapthor/requirements*.txt "$context"
git -C "$rapthor_checkout" archive --output="$context/rapthor.tar" "$rapthor_revision"
test "$(git get-tar-commit-id < "$context/rapthor.tar")" = "$rapthor_revision"
# The released Hebog wheel from PyPI; for unreleased work use
# `uv build --wheel --out-dir "$context"` instead.
python3 -m pip download --no-deps --only-binary :all: --dest "$context" \
  "hebog==<release>"
podman build --platform linux/amd64 --build-arg RAPTHOR_REVISION="$rapthor_revision" \
  --tag localhost/hebog-rapthor:native --file "$context/Containerfile" "$context"
podman image inspect localhost/hebog-rapthor:native --format '{{.Id}}'
podman run --rm --platform linux/amd64 --workdir /opt/rapthor-source \
  localhost/hebog-rapthor:native python -m pytest -q \
  tests/execution/test_hebog_filter.py tests/execution/test_skymodel_filter.py
```

To exercise the installed packages from outside the archived checkout too:

```bash
podman run --rm -i --platform linux/amd64 --workdir /work \
  localhost/hebog-rapthor:native python - <<'PYTHON'
from pathlib import Path
from tempfile import TemporaryDirectory
import runpy
import hebog
import rapthor

assert '/site-packages/' in hebog.__file__
assert '/site-packages/' in rapthor.__file__
checks = runpy.run_path('/opt/rapthor-source/tests/execution/test_hebog_filter.py')
for name in (
    'test_dual_run_retains_separate_products_and_selects_hebog',
    'test_hebog_defaults_to_continuum_with_zero_background',
    'test_insufficient_memory_falls_back_to_pybdsf',
    'test_reservation_counts_the_image_sources_not_the_sky_model',
):
    with TemporaryDirectory() as directory:
        checks[name](Path(directory))
PYTHON
```

The image archives the Rapthor source, including its tests, and installs it
without dependency re-resolution. The image label records the actual Rapthor
commit. Python 3.12 and Linux x86-64 match the existing LSMTool image; Podman
uses Rosetta on Apple silicon. No Measurement Set or external astronomy
executable is needed for these tests. The real beam branch passes a test
Measurement Set name only as far as the filtering boundary; a production
beam/EveryBeam run remains part of the operational trial.

`requirements.in` combines the three projects' runtime bounds, test tools and
wheel backends. `requirements.txt` freezes their resolution. Regenerate it
intentionally with:

```bash
uv pip compile requirements.in --python-version 3.12 \
  --python-platform x86_64-manylinux_2_39 --generate-hashes --no-header \
  --annotation-style line -o requirements.txt
```

`requirements-build.txt` contains the same locked entries for `setuptools`,
`setuptools-scm`, `vcs-versioning`, `packaging` and `wheel`, installed first so
source-only `progressbar` and `pims` build without an unpinned build environment.
Hebog and Rapthor arrive as explicit artifacts, and LSMTool comes from the
pinned base; none is silently replaced by a package-index version.
