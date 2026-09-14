# Phase 5 public-finder source-association pre-review

**Status:** ready for named scientific and engineering approval of fixture-only
implementation. This review is non-executable. It does not authorize
implementation, a cumulative replay, viewed SDC1 or Hydra execution, fresh
qualification, a campaign, tuning, rescoring, cutover, or release.

## Recommendation

Introduce an explicit image-domain catalogue-source layer above Hebog's
existing detection components. Preserve every accepted component and its
exclusive pixel ownership exactly, then group components only when undilated
multiscale support, existing-threshold intensity continuity, and
directional-size proximity all support the same association.

The grouping rule is deliberately conservative. It uses deterministic
complete-link agglomeration, so every pair in a proposed group must satisfy
the association rule. A chain of individually plausible neighbours cannot
silently merge its endpoints. Ambiguous cases remain separate.

The machine-readable review is
`config/contracts/phase-5-public-finder-source-association-pre-review.json`,
SHA-256
`9af42348896e0449e007fe2318648f66122313d600137f8f5ec525ebaec1cc3c`.

## Evidence boundary

The proposal is bound to terminal cumulative ledger
`benchmark-results/phase-5/cumulative-regression-ledger-public-finder-correction.json`,
SHA-256
`1ac6deb24e4bfc1928318c95437d45acac6ac1f94621b53d45175e0f41bd9797`.
That immutable result binds candidate `b1d59e5...`, source tree `2de6564e...`,
configuration `65c8876d...`, reconstructed references `48209eae...`, and
closed baseline `a45303df...`.

Compact science passes with no like-semantics regression. Continuum science
has 89 passing, 44 failing, and 10 underpowered endpoints, including 37
like-semantics regressions. All completeness and merge-fraction endpoints
pass, while reliability, duplicate, split, flux, and position endpoints fail.
The code and evidence therefore identify source composition as the next
prospective repair seam: the corrected owner plane publishes every accepted
connected owner as a terminal catalogue source, fragmenting multi-component
extended sources.

The 10 underpowered endpoints cannot compensate for the absolute failures or
regressions. The terminal evidence remains failed and must not be tuned,
rescored, or overwritten.

## Three distinct identities

The review freezes three different concepts:

| Layer | Meaning | Phase 5 treatment |
| --- | --- | --- |
| Detection component | One accepted connected seed and its exclusively assigned multiscale support. | Preserve its pixels and stable identity exactly. |
| Catalogue source | One image-domain emission source represented by one or more associated detection components. | Proposed binding public row. |
| Astrophysical object | A physical object whose association may require host, morphology, spectral, or multi-wavelength context. | Out of scope; make no such claim. |

This distinction follows the established island/component/source hierarchy in
[Hancock et al. (2012)](https://doi.org/10.1111/j.1365-2966.2012.20768.x).
The proposed image-domain evidence also follows the documented scientific
shape of [PyBDSF component grouping](https://pybdsf.readthedocs.io/en/latest/process_image.html#grouping-of-gaussians-into-sources):
intensity continuity above the existing island threshold and separation
relative to directional component widths. It does not copy PyBDSF code or
adopt PyBDSF output as truth.

## Frozen association rule

Each graph node is a canonical detection-component identity. Two nodes may
have an edge only when all of the following hold:

1. They belong to the same eight-connected parent support formed from their
   exact owner pixels and undilated significant B3 support.
2. Every valid pixel on the connecting segment remains at or above the
   existing three-sigma island threshold.
3. Their centroid separation is no greater than half the sum of their
   directional component FWHMs along that segment.
4. Both component shapes are available.

Edges are ordered deterministically by descending saddle margin, ascending
normalized separation, and canonical component identity. Complete-link
agglomeration accepts a group only if every component pair has a valid edge.
This prevents a transitive bridge such as (A\!\leftrightarrow\!B) and
(B\!\leftrightarrow\!C) from merging (A) with (C) when that pair does
not satisfy the rule.

The implementation may not use truth identities, reference-finder products,
viewed public outcomes, morphological dilation, or distance alone. An invalid
pixel or mask gap cannot create continuity. If an edge is ambiguous, the
components remain separate.

## Ownership and source measurements

Association must not create, delete, relabel, or reassign a detection
component. Let (C_s) be the set of components assigned to catalogue source
(s). The source partition must satisfy

\[
C_s \cap C_t = \varnothing \quad (s \ne t),
\qquad
\bigcup_s C_s = C,
\]

where (C) is the complete component set. Component ownership before and
after grouping must be bitwise identical.

Source records aggregate already measured component quantities:

\[
F_s = \sum_{c\in C_s} F_c,
\qquad
P_s = \max_{c\in C_s} P_c,
\qquad
\boldsymbol{x}_s =
\frac{\sum_{c\in C_s}F_c\boldsymbol{x}_c}
     {\sum_{c\in C_s}F_c}.
\]

Here (F_c) is existing exclusive integrated flux, (P_c) is peak flux, and
\(\boldsymbol{x}_c\) is the component centroid in a local tangent plane.
Source shape is the moment-equivalent ellipse measured on the union of exact
member-owner support. The change may not alter background, RMS, thresholds,
minimum area, recovery radius, apertures, flux calibration, astrometry, or the
component shape estimator. Shape uncertainty remains unavailable until its
covariance treatment receives separate review.

Binding catalogue-source rows use a canonical hash of sorted stable component
identities. Detection-component rows remain available as diagnostic records.

## Test-first matrix

Implementation may begin only after approval of this exact review. Tests must
precede production behaviour and cover at least:

- a single compact component;
- a split broad Gaussian with continuous B3 support;
- two nearby compact sources separated by a low saddle;
- high-dynamic-range neighbours;
- a three-component transitive bridge chain;
- a disconnected double-lobe physical object;
- shell and filament components; and
- masked gaps and invalid-pixel barriers.

The disconnected double-lobe case must remain separate unless the image-domain
rule itself supplies continuity; the implementation must not infer a physical
radio object. Negative controls permit zero false associations. Every fixture
passes independently, with no compensation between cases.

Property and execution tests must prove that:

- each component belongs to exactly one source;
- source and component flux totals are equal;
- component pixels are bitwise unchanged;
- association is invariant to label permutation, tile shape, partition origin,
  worker count, task order, and retry; and
- one-tile and many-tile execution agree.

Terminal replay products, viewed SDC1/Hydra products, and PyBDSF or Aegean
catalogues are forbidden implementation inputs.

## Approval and later gates

Named approval of this exact pre-review would authorize only:

1. test-first pure source-association records and graph logic;
2. fixture-only component and source catalogue construction;
3. serial and existing-Dask invariance validation; and
4. freezing a non-executable candidate identity.

After implementation, the complete change must pass focused unit,
integration, serial/Dask, coverage, typing, and documentation checks without
opening terminal replay or viewed public products. A complete cumulative
replay requires a newly frozen exact composition and a separate named
approval. Campaign execution, qualification, tuning, rescoring, cutover, and
release remain outside this review.
