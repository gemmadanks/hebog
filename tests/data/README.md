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
