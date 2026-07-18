# Scientific-equivalence tests

Use analytic and generated truth to assess scientific correctness. Frozen
PyBDSF products assess compatibility with the behaviour Rapthor consumes; they
are not scientific ground truth.

Unit-test catalogue matching and RMS/mask comparison against hand-constructed
cases before using them on reference products. Include ambiguous assignments,
unmatched rows, coordinate wraparound, unit conversion, masks, and empty
products.

Reference products are immutable test inputs. A separate documented generation
command must record dataset checksums, PyBDSF and dependency revisions, and the
complete configuration. Review reference metadata and the scientific diff
together whenever an update is proposed.
