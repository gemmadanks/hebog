# Scientific comparison reports

The comparison oracle in `hebog.validation.comparison` is independent of
PyBDSF product readers and of Hebog's scientific algorithms. Its purpose is to
make catalogue, RMS,
and mask equivalence calculations testable before any frozen external product
is treated as evidence.

## Catalogue matching

`CatalogueSource` stores canonical ICRS-like sky values in degrees, peak flux
density in Jy/beam, and integrated flux density in Jy. It can also carry
candidate-reported one-standard-deviation errors, fitted/deconvolved
`CatalogueEllipse` records, an explicit resolved/unresolved/unavailable
deconvolution state, parent-island identity, component count, and canonical
quality flags. `from_units` accepts
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

For matched rows, the report additionally contains signed fitted and
deconvolved major/minor-axis fractional differences, shortest position-angle
differences modulo 180 degrees, resolved/unresolved classification accuracy,
component-count agreement, exact and Jaccard quality-flag agreement, and
summary medians and 95th percentiles. Axis summaries use the worse of the
major/minor fractional errors for each matched row, and fitted and deconvolved
position angles remain separate so one population cannot conceal another.
The caller supplies the reviewed minimum reference major/minor-axis ratio for
position-angle evidence; the compact contract uses `1.1`, below which orientation is not a
meaningful scientific quantity. Axis evidence remains eligible. Reference or
injected truth alone selects every governed population. A missing candidate
shape, classification, or parent identity therefore counts as unavailable
rather than silently removing a difficult row. The report carries explicit
eligible, available, and availability-fraction fields for each gate; absent
shapes are never converted to zero.

Candidate-reported uncertainties are normalized against the reference value.
Each reference-eligible metric reports its eligible and candidate-available
sample counts, availability fraction, one-sigma coverage, mean normalized
residual, and sample standard deviation when at least two observations exist.
A missing candidate uncertainty produces an availability failure and an
explicit empty calibration result, rather than disappearing. The reference
must therefore be governed truth when the report is used to claim calibration;
a PyBDSF comparison alone measures compatibility, not error-coverage truth.

Parent-island association is compared after row assignment. Linear-size
contingency summaries produce pairwise true-positive, false-positive, and
false-negative co-association counts plus precision, recall, intersection over
union, and overall agreement without constructing an all-pairs matrix.
Precision and recall prevent the much larger set of unrelated source pairs
from concealing a split or merge. A missing candidate parent identity remains
in the reference-selected population as a unique unavailable identity, so it
cannot conceal a split; identity availability is also reported directly.
Component counts are compared separately.
`CatalogueOutlierThresholds` has no hidden
defaults: callers must supply their frozen position, flux, and shape limits to
obtain a catastrophic-outlier fraction and identifiers. The report retains
those thresholds so persisted evidence remains self-describing.

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

The frozen released and `master` PyBDSF products under `config/baselines/`
exercise the same oracle through the equivalence lane, and Hebog/reference
comparisons use the same typed reports. Per-source-class stratification is
layered on top and must not change these core calculations. Released and
pinned-`master` PyBDSF do not produce identical catalogues on the same image;
that divergence is resolved against injected truth, not by treating either
version as authoritative.

::: hebog.validation.comparison
    options:
      show_symbol_type_toc: true
