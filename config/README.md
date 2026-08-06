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

`benchmarks/` contains the complete size/density matrices, crossover rules,
one-tile overhead budgets, the Phase 4 incremental compact-catalogue component
budgets, and the provisional 100,000-square resource and scaling gates.
`contracts/` contains the public-behaviour ownership manifest
and versioned phase-specific scientific meanings and margins. Phase 4 keeps
its measurement semantics separate from its numerical gates so review can
amend thresholds without silently changing the meaning of a catalogue field.
The Phase 4 paired non-inferiority contract separately records comparison
directions, practical margins, clustered design assumptions, failure handling,
and the one-look stopping rule. Its `reviewed` status records named approval;
the final unseen population may be frozen only through a separate governed
manifest and must not be opened before that freeze is complete.
`datasets/phase-4-final-qualification.json` is that frozen, ungenerated,
600-image one-look population. Its complete dataset-record digest, not only
its recipe digest, is the identity carried into each campaign shard.

The Phase 5 multiscale and scientific-gate contracts freeze the Rapthor-used
three-scale meaning, failure and association semantics, absolute truth gates,
paired PyBDSF non-inferiority margins, and one-look statistical design before
filter selection. Phase 5 dataset schema version 3 adds analytic morphology
groups and scale-, edge-, tile-, invalid-pixel-, and artefact-aware strata.
The 400-image qualification manifest is frozen and must remain unopened until
the independent pre-opening power audit passes; development and regression
seeds are disjoint from it.

`contracts/phase-5-filter-selection.json` records the provisional
development-only Step 2 decision to use the float64 beam-aware matched-filter
bank, including its
normalization, four-sigma support, halo formula, correlated-noise model,
bounded structural costs, and typed evidence identity. Analytic edge evidence
amended the minimum valid support from 0.8 to 0.5 before qualification was
opened. A paired Step 2B scientific comparison must amend or confirm this
record before Step 3; the undecimated-wavelet candidate remains active
development evidence until then.

These files are gates, not measured evidence; raw measurements use the evidence
schemas and stay under the ignored `benchmark-results/` directory.
