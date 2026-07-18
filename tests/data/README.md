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
