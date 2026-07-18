# Scientific-equivalence tests

Use analytic and generated truth to assess scientific correctness. Frozen
PyBDSF products assess compatibility with the behaviour Rapthor consumes; they
are not scientific ground truth.

Unit-test catalogue matching and RMS/mask comparison against hand-constructed
cases before using them on reference products. Include ambiguous assignments,
unmatched rows, coordinate wraparound, unit conversion, masks, and empty
products.

The independent comparison primitives and their analytic unit tests live in
`hebog.validation.comparison` and `tests/unit/validation/test_comparison.py`.
The one-to-one catalogue assignment maximizes match count, then matched
integrated flux, then angular proximity. Product readers and frozen-reference
tests must call this implementation rather than reproduce matching or report
calculations in an integration test.

Persist each released-PyBDSF, pinned-`master`, and Hebog/reference comparison
as a separate `ScientificComparisonEvidence` document. Candidate/reference
revision identities, dataset and configuration checksums, match gates, and all
catalogue/RMS/mask reports belong in the same validated record.

Reference products are immutable test inputs. A separate documented generation
command must record dataset checksums, PyBDSF and dependency revisions, and the
complete configuration. Review reference metadata and the scientific diff
together whenever an update is proposed.
