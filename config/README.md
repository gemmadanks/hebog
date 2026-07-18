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

The initial Phase 0 manifest contains small development cases. Frozen PyBDSF
products and the reviewed regression and qualification manifests remain
separate deliverables; do not add a role merely to make a dataset available in
more than one test lane.
