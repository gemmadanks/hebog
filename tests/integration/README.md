# Integration tests

Tests exercising small FITS fixtures, a local Dask cluster, or another concrete
component boundary belong here and use the `integration` marker. PyBDSF
comparisons belong in `tests/equivalence/`, while cross-system behavioural
scenarios belong in `tests/acceptance/`.

Keep pull-request integration tests deterministic and redistributable. Add the
`qualification`, `scalability`, `slow`, or `requires_data` marker when a case
must run only in a controlled environment. Large-image and multi-node cases
belong in `tests/benchmark/` and run only through `just test-scalability`.

A product contract that must hold for every executor takes the
`each_executor` fixture from `conftest.py`, which runs the test under
`SerialExecutor`, `ThreadExecutor` and an in-process Dask client in turn. The
public product-hash tests and the envelope-grid test do; the wide-object grid
test runs Serial only, and the corner-background and noiseless-edge tests
still compare Serial with in-process Dask only. In-process Dask workers share
the test's process; one public run in `test_public_find_sources.py` uses Dask
workers in separate processes, so that task arguments and results are
serialized.
