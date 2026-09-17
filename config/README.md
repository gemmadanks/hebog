# Configuration

Checked-in source-finder, scientific-equivalence, and benchmark configurations
belong here. Configuration files must not contain machine-specific paths;
datasets are supplied through command-line arguments or environment variables.

`baselines/` contains machine-readable revision and environment inventories.
Each inventory must state whether it is a candidate or reviewed baseline and
record unresolved reproducibility gaps rather than inferring missing versions.

`datasets/` contains versioned validation-data manifests. Every entry has one
test role, canonical beam/WCS and image-statistics units, provenance,
redistribution status, and a SHA-256 digest of its complete generation recipe.
Changing a recipe requires a new digest and, when the generator algorithm
changes, a new generator version. Loading a manifest validates metadata only;
it never downloads or generates data.

Phase 0 freezes separate development, regression, and held-out qualification
manifests. The qualification seed is recorded for reproducibility but its
results must not be inspected during routine algorithm tuning. Do not add a
role merely to make a dataset available in more than one test lane.

`benchmarks/` contains the complete size/density matrix, crossover rules,
one-tile overhead budgets and the pinned-PyBDSF-`master` deployment gate
(`phase-0-performance.json`), the provisional 100,000-square resource and
scaling gates (`phase-0-scalability.json`), and the quick benchmark's cases
(`quick-benchmark.json`). `checks/` contains the quick science check's cases.
`contracts/` contains the public-behaviour ownership manifest, the Phase 3 and
Phase 4 scientific gates and measurement semantics used by the equivalence
tests, and `phase-5-corrective-a-review.json`, which the installed science
profile must match byte for byte.

Phase 4 and Phase 5 development are closed. Their dataset manifests remain so
that new populations can be checked for seed disjointness. Their paired
non-inferiority protocols, metric registries, reviews, decisions and campaign
contracts were removed with the campaign tooling and remain in
[Git history at `v0.7.0`](https://github.com/gemmadanks/hebog/tree/v0.7.0/config/contracts).

`comparisons/notebook-comparison.json` lists the public SDC1, Hydra and LoTSS
cases, download sources and PyBDSF/Aegean options used by the source-finder
comparison notebook scripts. It is diagnostic configuration and carries no
qualification authority.

These files are gates, not measured evidence; raw measurements use the evidence
schemas and stay under the ignored `benchmark-results/` directory.
