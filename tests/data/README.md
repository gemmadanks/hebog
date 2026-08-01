# Test data

Every dataset must have a manifest entry containing its checksum, provenance,
redistribution status, generator version and configuration where applicable,
beam and WCS metadata, image statistics, and exactly one role:

- `development`: analytic and synthetic cases used during TDD;
- `regression`: reviewed cases preserving a defect fix or scientific decision;
- `qualification`: frozen production-like cases held out from routine tuning.

Tests must not download data or regenerate expected products implicitly.
Non-redistributable qualification data stays outside Git and is addressed by
environment-neutral identifiers on approved controlled runners.

The 10,000/30,000/100,000-pixel scalability ladder is generated or retained
outside Git. By default those cases have development, regression, and
qualification roles respectively. Their manifests record the logical recipe
and checksums, generator version, source population, deliberate tile-edge and
tile-corner cases, storage layout, and approved facility identifier; tests
must not check large planes into the repository.

The checked-in manifests live in `config/datasets/`. Synthetic noise is
addressed by global pixel coordinate, so generating a plane through different
window or tile layouts produces identical values. Complete in-memory
generation has a safety limit; large cases must use bounded windows and
external materialised storage.

`pybdsf/pybdsf-compact-reference-256/` contains the seven standardized
Rapthor-facing products from released PyBDSF 1.14.1 and pinned PyBDSF master.
Its `input.fits` is the exact 256-by-256 generated input bound by the dataset
checksum in the same baseline manifest; keeping this small regression input
allows Hebog to recompute and compare RMS products in portable CI.
`config/baselines/phase-0-pybdsf-reference-products.json` binds every file to
its checksum, exact configuration, dependency inventory, container digest,
and reviewed benchmark run. Regenerate them only with
`scripts/validation/freeze_reference_products.py` after rerunning and
reviewing both isolated campaigns. The freezer fails closed when an artifact
already exists; replacing a reviewed reference requires the explicit
`--replace-existing` option and a fresh review of every resulting checksum.
