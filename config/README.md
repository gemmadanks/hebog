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

`benchmarks/` contains the complete size/density matrix, crossover rule,
one-tile overhead budgets, and the provisional 100,000-square resource and
scaling gates. `contracts/` contains the public-behaviour ownership manifest
and versioned phase-specific scientific meanings and margins. Phase 4 keeps
its measurement semantics separate from its numerical gates so review can
amend thresholds without silently changing the meaning of a catalogue field.
The Phase 4 paired non-inferiority contract separately records comparison
directions, practical margins, clustered design assumptions, failure handling,
and the one-look stopping rule. Its `reviewed` status records named approval;
the final unseen population may be frozen only through a separate governed
manifest and must not be opened before that freeze is complete.
These files are gates, not measured evidence; raw measurements use the evidence
schemas and stay under the ignored `benchmark-results/` directory.
