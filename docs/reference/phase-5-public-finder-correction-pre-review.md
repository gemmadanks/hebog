# Phase 5 public-finder correction pre-review

**Status:** ready for named scientific and engineering approval of
implementation and fixture-only validation. This review is non-executable: it
does not authorize implementation, cumulative replay, execution on the viewed
public data, fresh qualification, campaign execution, tuning, rescoring,
cutover, or release.

## Recommendation

Implement one deliberately narrow candidate correction in two coupled parts:

1. preserve direct residual seed identities while assigning nearby
   multiscale support by deterministic nearest-seed ownership; and
2. publish honest moment-equivalent observed and beam-deconvolved source
   shapes with explicit unavailable states.

In parallel, implement only the adapter and fixture tests needed to use the
official SDC1 *source-finding* scorer later. Do not rerun SDC1 or Hydra, and do
not change a threshold, background/RMS rule, minimum area, aperture, flux
measurement, or pass limit during this implementation stage.

This is the smallest response to scientific review `320f57f5...`. It removes
the directly demonstrated Hydra bridge mechanism and fills the shape record
needed for source-aware SDC1 association, while preventing low-SNR,
photometry, and protocol questions from being tuned simultaneously.

The machine-readable pre-review is
`config/contracts/phase-5-public-finder-correction-pre-review.json`, SHA-256
`3e02aff3c29128d65b0af5c0d9d99720fd03a9fe70730e632815ae4694747bfd`.

## Evidence and immutability boundary

The correction is motivated by terminal public campaign `42abb896...`,
analysis `975978fb...`, decision `954077e9...`, and post-result scientific
review `320f57f5...`. The sealed decision remains `fail` and is not rescored.
Its campaign, analysis, protocol, decision, raw products, and frozen
configuration remain immutable historical evidence.

The qualified base candidate is revision `9062664...`, source tree
`e4307246...`, and configuration `0e5dde51...`, with final-qualification
decision `d4db4d7f...`. A corrected candidate will necessarily have new source
and configuration identities. It must not masquerade as the qualified base.

The exact reusable closed cumulative baseline is
`benchmark-results/phase-5/cumulative-regression-ledger-recovery.json`,
SHA-256 `a45303df...`. It is a comparison oracle, not a file to overwrite.

## Why the current association fails

The current prospective candidate first detects accepted connected components
on original residual pixels. Those components already provide distinct,
physically interpretable seed identities. It then dilates the union of direct
and reconstructed support by three beam major axes and labels the connected
union. In a deep crowded field, faint multiscale support supplies long bridges
between otherwise independent seeds. Connected-component labelling then
turns the entire bridged graph into one catalogue identity.

The Hydra evidence makes the failure causal rather than speculative: the deep
mask occupies 4.139% of the image, has label p95 area 6,248 pixels and maximum
area 55,186 pixels, and publishes only 356 entries. The shallow mask occupies
0.867%, has p95 area 777 and maximum 2,737 pixels, and publishes 413 entries.
The RMS ratio remains consistent with the images. Depth changes association
topology, not merely sensitivity.

## Seeded-island ownership

### Authoritative identities

Let \(L_0(p)\) be the accepted direct-residual label at pixel \(p\) before any
association dilation. Its positive labels are authoritative seed identities.
The correction must preserve two invariants:

\[
L(p) = L_0(p) \quad \text{for every } p \text{ where } L_0(p) > 0,
\]

and multiscale recovery alone must never reduce the number of positive seed
identities.

The existing direct detector already supplies this plane. The historical
three-beam connected-union branch remains available only to reproduce sealed
evidence; it must not be modified in place.

### Recovered support

Let \(S_0\) be accepted direct support and \(S_m\) significant adjacent-scale
multiscale support. Only support within the already reviewed half-major-beam
recovery radius is eligible:

\[
S_r = \{p \in S_m : d(p, S_0) \le 0.5\,b_{\mathrm{maj}}\}.
\]

For an eligible pixel outside direct support, assign the nearest exact seed
support:

\[
L(p) = L_0\!\left(\underset{q\in S_0}{\arg\min}\;\lVert p-q\rVert_2\right).
\]

Equal-distance ties use the canonical global seed identity derived from its
global row-major reference pixel, never a task-local completion order. Invalid
pixels remain unowned. An association or context graph may record that two
sources overlap the same diffuse structure, but graph evidence cannot alter
pixel ownership or merge catalogue rows.

This reuses `refine_multiscale_segment_labels` and the repository's existing
nearest-owner aperture semantics. It does not introduce a new segmentation
framework.

### Expected trade-off

Preventing merges can expose multiple direct peaks belonging to one genuinely
complex radio galaxy. That is an honest source-characterization problem; it
must not be hidden by reconnecting every nearby seed. For this correction,
each direct seed stays a source identity and any physical grouping is recorded
as a separate association relation. A later source-grouping policy would need
truth-bearing evidence and its own review.

## Public shape record

The existing extended-measurement code already accumulates flux-weighted
first and second moments on exact original-residual support. Reuse those
statistics rather than fitting a new model during this correction.

For positive support weights \(w_p\) at pixel coordinates
\(\mathbf{x}_p\), compute

\[
\boldsymbol{\mu} =
\frac{\sum_p w_p\mathbf{x}_p}{\sum_p w_p},
\qquad
\Sigma_{\mathrm{pix}} =
\frac{\sum_p w_p
(\mathbf{x}_p-\boldsymbol{\mu})
(\mathbf{x}_p-\boldsymbol{\mu})^\mathsf{T}}{\sum_p w_p}.
\]

At the measured centroid, use the local WCS Jacobian \(J\) to transform pixel
covariance into east/north sky covariance:

\[
\Sigma_{\mathrm{sky}} = J\Sigma_{\mathrm{pix}}J^\mathsf{T}.
\]

If \(\lambda_{\max}\) and \(\lambda_{\min}\) are its eigenvalues, the
moment-equivalent observed FWHM axes are

\[
\theta_{\mathrm{maj,min}} =
2\sqrt{2\ln 2}\sqrt{\lambda_{\max,\min}}.
\]

Position angle is measured east of north in \([0,180)\) degrees. This handles
rotated WCS and non-square pixels without assuming a diagonal pixel scale.

Beam deconvolution uses covariance subtraction,

\[
\Sigma_{\mathrm{intrinsic}} =
\Sigma_{\mathrm{sky}} - \Sigma_{\mathrm{beam}},
\]

and retains the existing four states: resolved, major-axis-only, unresolved,
or unavailable. Under-determined support, non-positive weight, singular
covariance, invalid WCS, or non-identifiable axes remain explicitly
unavailable. The implementation must never manufacture a circular source.

The public comparison row may continue using its `fitted_shape` transport
field, but it must carry a canonical `segment-moment-equivalent-shape` quality
flag. Documentation and adapters must say that this is an observed
moment-equivalent ellipse, not a nonlinear Gaussian fit. Shape uncertainties
remain unavailable until correlated-noise uncertainty propagation has its own
scientific review.

## SDC1 validation redesign

The corrected public adapter must target only the official SDC1 source-finding
dimensions. It must not claim the global classification score because Hebog
does not estimate source population or core fraction.

The recommended validation boundary is:

- pin the official scorer and its dependency inventory in an isolated
  validation environment; do not copy its implementation or add it to the
  Hebog runtime;
- map Hebog position, moment-equivalent size, and apparent integrated flux to
  its source-finding input schema with explicit units;
- freeze the randomized null-catalogue configuration and seed before opening
  corrected public products;
- run all nine applicable published 1.4-GHz, 1000-hour submissions over the
  same selected output cores and truth admission so that calibration is
  like-for-like;
- report chance-adjusted source-finding components and completeness,
  reliability, flux, and shape curves versus apparent SNR and morphology; and
- retain the old 0.5-beam position-only metrics as historical diagnostics,
  never as an official score or as the sole future public gate.

The already viewed SDC1 and Hydra data are development/regression evidence.
They may calibrate a future protocol only after a corrected candidate and
scorer composition are frozen and separately approved. They cannot qualify
the corrected candidate and cannot become fresh held-out evidence.

## Test-first implementation matrix

### Analytic unit tests

Add failing tests before changing candidate behaviour for:

1. two accepted direct seeds joined by a broad significant bridge: both seed
   identities and their pixels remain distinct;
2. one accepted seed with coherent multiscale wings: eligible wings attach to
   the seed without creating another source;
3. an equidistant ownership tie: global identity, partition, and task order
   produce the same owner;
4. a close blend, a genuine single extended source, edge clipping, and invalid
   pixels;
5. elliptical, circular, unresolved, major-axis-only, and singular covariance
   shapes; and
6. rotated WCS, non-square pixels, and beam covariance subtraction.

### Property and integration tests

Require the following invariants:

- adding eligible recovered support cannot merge or delete a direct seed;
- relabelling task-local integers cannot change stable global ownership;
- every eligible recovered pixel has exactly one owner;
- serial and Dask results agree;
- one tile and many tiles agree across partition origin, tile shape, worker
  count, completion order, and retry;
- catalogue JSON and canonical `SourceCatalogue` round trips preserve units,
  shape states, measurement provenance, and absent uncertainties; and
- the SDC1 adapter validates synthetic scorer fixtures without opening or
  scoring corrected public products.

### Regression sequence

Implementation approval alone must not start a large replay. After focused
validation passes, freeze the exact candidate, runtime, fixture, public
adapter, and absent-output identities. Obtain separate named approval before:

1. replaying every closed compact, Continuum, boundary, blend, mask,
   measurement, and final-qualification regression against exact ledger
   `a45303df...`;
2. requiring `cumulative_science_regression_ready=true` with no like-semantics
   regression;
3. running the frozen corrected candidate and scorer on viewed SDC1/Hydra
   development data; or
4. designing a fresh held-out qualification population.

Hydra improvement is diagnostic, not an absolute truth gate. The replay must
still report deep/shallow counts, overlap, retained-mask fraction, and label
area distribution so that the known bridge failure cannot silently return.

## Risks and controls

| Risk | Control |
| --- | --- |
| True multi-component objects become separate rows | Preserve graph association separately; do not merge without truth-bearing review |
| A half-beam radius becomes another tuned constant | It predates the public result and is already the reviewed bounded support-recovery radius |
| Moment ellipses are mistaken for Gaussian fits | Canonical provenance flag, explicit docs, and adapter metadata |
| Threshold changes hide a remaining SDC1 sensitivity gap | Freeze threshold, RMS, area, aperture, and flux policies during this correction |
| Viewed public data leak into qualification | Classify SDC1/Hydra as development/regression only and require fresh identities |
| New behaviour regresses earlier Continuum or compact science | Exact full cumulative replay and no-like-semantics-regression gate |
| Official scorer becomes a runtime dependency | Isolated pinned validation environment only |

## Authorization boundary

This pre-review authorizes nothing by itself. The next approval may authorize
only implementation and fixture-scale validation of seeded ownership, public
shape records, and the non-executable SDC1 adapter. It must not authorize the
cumulative replay, execution on viewed public data, a new campaign, fresh
qualification, threshold or photometric tuning, rescoring the sealed terminal
decision, cutover, or release.

After that implementation is complete and exact identities are reviewed, a
second named approval is required for the full cumulative replay and any
viewed-development execution. Fresh qualification requires a later, separate
design and approval.
