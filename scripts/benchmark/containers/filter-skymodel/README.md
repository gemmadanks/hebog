# Matched filter_skymodel benchmark image

Plan task 23 times Rapthor's complete `filter_skymodel` step with Hebog's
native task against Rapthor's PyBDSF subprocess, both in one Linux container
on the same cores. This image is the [Rapthor integration
image](../../../validation/containers/rapthor/README.md) with pinned PyBDSF
`master` (`c70103b`, the deployment gate's reference) in place of released
1.14.1; nothing else in it changes, and `pip check` passes.

PyBDSF publishes no wheel for `master`, and its own wheels build Boost.Python
against the NumPy they run with. Ubuntu's Boost.Python is built against
NumPy 1 and the image runs NumPy 2, so the builder stage builds Boost 1.91.0's
Python libraries against the image's NumPy, as PyBDSF's `cibuildwheel` setup
does, then PyBDSF with the helpers the Phase 0 `master` wheel was built with
(`requirements-pybdsf-master-build.in`, locked with hashes). The final stage
copies the two Boost libraries and installs the wheel. The image is
`linux/amd64`, like the integration image, and runs under Rosetta on Apple
silicon, so its timings are emulated: the ratio of the two finders is
matched, while absolute times and the gate's final figures come from the
cluster benchmark (plan task 30).

## Build

Build the integration image first, then from the Hebog checkout:

```bash
context=$(mktemp -d)
cp scripts/benchmark/containers/filter-skymodel/Containerfile \
  scripts/benchmark/containers/filter-skymodel/requirements-pybdsf-master-build.txt \
  "$context"
curl -L -o "$context/boost_1_91_0.tar.bz2" \
  https://archives.boost.io/release/1.91.0/source/boost_1_91_0.tar.bz2
git -C <PyBDSF checkout> archive --output="$context/pybdsf.tar" \
  c70103be3ae9ae9908286f144e6ce956acc0ce5c
podman build --platform linux/amd64 \
  --build-arg BASE_IMAGE=localhost/hebog-rapthor:<tag> \
  --tag localhost/hebog-filter-benchmark:<tag> \
  --file "$context/Containerfile" "$context"
```

The build checks Boost's published SHA-256
(`de5e6b0e4913395c6bdfa90537febd9028ea4c0735d2cdb0cd9b45d5f51264f5`), records
the installed wheel's SHA-256 in `/opt/bdsf-master-wheel.sha256` and checks
that `import bdsf` reports `1.14.2.dev40+gc70103be3`. Regenerate the lock with
`uv pip compile requirements-pybdsf-master-build.in --python-version 3.12
--python-platform x86_64-manylinux_2_39 --generate-hashes --no-header
--annotation-style line -o requirements-pybdsf-master-build.txt`.

## Run

`scripts/benchmark/measure_filter_skymodel.py` writes the sector's inputs
from a real image and runs each repetition of each finder in a fresh
container of this image; see its docstring and
[the benchmark guide](../../README.md).
