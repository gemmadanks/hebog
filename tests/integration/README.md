# Integration tests

Tests exercising small FITS fixtures, a local Dask cluster, or another concrete
component boundary belong here and use the `integration` marker. PyBDSF
comparisons belong in `tests/equivalence/`, while cross-system behavioural
scenarios belong in `tests/acceptance/`.

Keep pull-request integration tests deterministic and redistributable. Add the
`qualification`, `slow`, or `requires_data` marker when a case must run only in
a controlled environment.
