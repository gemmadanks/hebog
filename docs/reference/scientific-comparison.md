# Scientific comparison reports

The comparison oracle in `hebog.validation.comparison` is independent of the
PyBDSF product readers and of Hebog's algorithms, so catalogue, RMS and mask
equivalence are testable before any frozen external product counts as
evidence. The frozen PyBDSF products under `config/baselines/` and every
Hebog comparison use the same typed reports; stratification by source class
is layered on top and never changes these calculations.

## Catalogue matching

`CatalogueSource` stores ICRS positions in degrees, peak flux density in
Jy/beam and integrated flux density in Jy, and can carry candidate-reported
one-sigma errors, fitted and deconvolved `CatalogueEllipse` records, an
explicit resolved/unresolved/unavailable state, parent-island identity,
component count and canonical quality flags; `from_units` accepts degrees or
arcseconds and Jy or mJy. The caller decides whether it is comparing
sources, Gaussian components or another row type first; the concepts are not
interchangeable.

`compare_catalogues` forms all pairs inside the caller's beam-normalized
separation gate, boundary included, and solves one global one-to-one
assignment with lexicographic objectives: most pairs inside the gate, then
the smallest sum of great-circle separations, then the smallest sum of the
symmetric flux difference `|candidate - reference| / (candidate + reference)`.
Position decides before flux: two objects sharing a gate are paired by
separation even when the crossed pairing agrees better in flux, and the flux
errors then show the disagreement. Flux enters each pair's cost with a weight
of 10⁻⁹ beam, so it decides only between pairings whose separations differ by
less than that, which covers coincident rows and rounding. Ties are resolved
deterministically for a given input order, and right ascension wraps at 360°.

The report gives separations in beam FWHM and flux differences as signed
fractions of the reference, with median and 95th-percentile summaries.
Completeness is matched/reference and reliability matched/candidate; an empty
denominator counts as `1.0`, so two empty catalogues agree and a
candidate-only catalogue has zero reliability. Match-only metrics are `None`
without pairs. For matched rows it adds signed fitted and deconvolved axis
differences (the worse of major and minor per row), shortest position-angle
differences modulo 180°, classification accuracy, component-count agreement
and exact and Jaccard quality-flag agreement, keeping fitted and deconvolved
angles separate. The caller supplies the minimum reference axis ratio for
position-angle evidence (the compact contract uses `1.1`). Reference or
injected truth alone selects every population, so a missing candidate shape,
classification or parent identity counts as unavailable rather than removing
a difficult row; each gate reports eligible, available and
availability-fraction fields.

Candidate uncertainties are normalized against the reference value, with
eligible and available counts, one-sigma coverage, mean normalized residual
and sample standard deviation per metric; a missing uncertainty is an
availability failure, not a silent omission. Calibration claims therefore
need governed truth as the reference; a PyBDSF comparison measures
compatibility only.

Parent-island association is compared after assignment through linear-size
contingency summaries: pairwise true-positive, false-positive and
false-negative co-association counts with precision, recall, intersection
over union and agreement, so the far larger set of unrelated pairs cannot
hide a split or merge. A missing candidate parent identity stays in the
population as a unique unavailable identity. `CatalogueOutlierThresholds`
has no defaults: callers supply their frozen position, flux and shape limits
to obtain a catastrophic-outlier fraction, and the report retains them.

## RMS maps

`compare_rms_maps` takes equal-shaped non-negative RMS arrays in Jy/beam and
an optional boolean valid mask. Non-finite values and pixels outside the mask
are excluded, and a negative finite RMS inside it is invalid input. Absolute
differences use every comparable pixel; fractional differences use only
pixels with positive reference RMS, with zero-reference pixels counted
explicitly. Empty comparisons return counts and `None` metrics.

## Masks and island labels

`compare_masks` takes boolean arrays of equal shape and reports
true-positive, true-negative, false-positive and false-negative counts with
agreement, precision, recall and intersection over union. Two empty masks
score `1.0` on all four; a missing candidate-positive class has precision
`0.0` when the reference has positive pixels and `1.0` otherwise.

`compare_island_labels` compares non-negative integer label planes
independently of their label values, with zero as background. It builds the
sparse positive-overlap graph, separates its components and assigns objects
by the number of overlapping pairs and then their intersecting pixels,
retaining per-match intersection over union, completeness, reliability,
unmatched labels and every split or merge visible in the graph. An optional
valid mask excludes pixels first. This object report stops high background
agreement from concealing a topologically wrong mask.

Released and pinned-`master` PyBDSF do not produce identical catalogues on
the same image; that divergence is resolved against injected truth, not by
treating either as authoritative.

::: hebog.validation.comparison
    options:
      show_symbol_type_toc: true
