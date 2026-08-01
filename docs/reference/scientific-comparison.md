# Scientific comparison reports

The Phase 0 comparison oracle is independent of PyBDSF product readers and
Hebog's future scientific algorithms. Its purpose is to make catalogue, RMS,
and mask equivalence calculations testable before any frozen external product
is treated as evidence.

## Catalogue matching

`CatalogueSource` stores canonical ICRS-like sky values in degrees, peak flux
density in Jy/beam, and integrated flux density in Jy. `from_units` accepts
degrees or arcseconds and Jy or mJy variants at ingestion. A compatibility
adapter must decide whether it is comparing PyBDSF sources, Gaussian
components, or another row type before constructing these records; those
concepts are not interchangeable.

`compare_catalogues` forms all pairs inside the caller's beam-normalized
angular-separation gate and uses a global one-to-one assignment. The assignment
objectives are lexicographic:

1. maximize the number of valid pairs;
2. maximize the sum of the smaller reference/candidate integrated flux in each
   pair, resolving blend ambiguities without rewarding flux duplication;
3. minimize great-circle angular separation.

Right ascension wraps at 360 degrees. Reported positions are separations in
beam FWHM; flux differences are signed fractions of the reference value, with
median and linear 95th-percentile absolute differences in the summary.
Completeness is matched/reference and reliability is matched/candidate. An
empty denominator has value `1.0`, so two empty catalogues agree while a
candidate-only catalogue has zero reliability. Match-only numerical metrics
are `None` when there are no pairs.

The current oracle deliberately performs one-to-one row matching. Grouped
source/component or island-aware comparisons require a separately tested
adapter or future schema; they must not be approximated by duplicating rows.

## RMS maps

`compare_rms_maps` requires equal-shaped, non-negative RMS arrays in Jy/beam.
An optional boolean valid mask selects the scientific comparison region.
Non-finite values are excluded, as are all values outside that region. A
negative finite RMS inside the selected region is invalid input.

Absolute differences use every comparable pixel. Fractional differences use
only pixels whose reference RMS is positive; zero-reference pixels are counted
explicitly rather than divided by an arbitrary epsilon. Empty comparisons
return counts and `None` numerical metrics.

## Masks

`compare_masks` accepts boolean arrays only and never broadcasts different
shapes. Its report contains true-positive, true-negative, false-positive, and
false-negative pixel counts plus agreement, precision, recall, and intersection
over union. Two empty or all-false masks have value `1.0` for all four
fractions. A missing
candidate-positive class has precision `0.0` when the reference contains
positive pixels, and `1.0` otherwise.

`compare_island_labels` compares two-dimensional non-negative integer label
planes independently of their numeric label identities. Label zero is
background. It builds the sparse positive-overlap graph, separates independent
graph components, and assigns objects by maximizing the number of overlapping
pairs before their total intersecting pixels. The report retains per-match
intersection over union, completeness, reliability, unmatched labels, and
every reference split or candidate merge visible in the overlap graph. An
optional valid mask excludes pixels before objects and overlaps are counted.
This object report prevents high background agreement from concealing a
topologically wrong source-filtering mask.

The compact released/master products now exercise the same oracle through the
equivalence lane. Their immutable manifest and persisted scientific record are
summarized in the [Phase 0 baseline results](phase-0-baseline-results.md).
Future Hebog/reference documents use the same typed reports. Per-source-class
stratification begins with later algorithm/regression slices; it must not
change these core calculations.

The corrected representative `5.0/3.0` campaigns produce 12 released-PyBDSF
source rows and 14 pinned-master rows. They are not yet frozen as a row-level
comparison because the controlled 3,000-square input is restricted. That
count difference is an explicit reference divergence to resolve against
governed truth, not by selecting either PyBDSF version as authoritative.

::: hebog.validation.comparison
    options:
      show_symbol_type_toc: true
