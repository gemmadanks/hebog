# Phase 5 external source-finder comparison protocol

**Status:** the Step 2C-P protocol, reference runtimes, fresh populations,
like-product mappings, matcher rules, metrics, margins, and power audit are
frozen before external output. Execution is not yet authorized. Step 3,
optimization, and qualification remain closed.

This is the first Phase 5 comparison that will place Hebog beside external
source finders. Earlier `paired` Phase 5 results compared only Hebog
representations. The machine-readable protocol is
`config/contracts/phase-5-external-comparison.json`.

## References

| Reference | Exact software | Immutable runtime | Binding scope |
| --- | --- | --- | --- |
| Rapthor release | PyBDSF 1.14.1, commit `1b6e0a0`, published sdist `8d5113f...` | `sha256:dce9399...` | Full continuum |
| Performance reference | PyBDSF `master` `c70103b`, version `1.14.2.dev40+gc70103be3`, wheel `2f1fdfb...` | `sha256:f045820...` | Full continuum |
| Community catalogue reference | AegeanTools 2.3.5, publication commit `bb04f50`, wheel `dda95cb...` | `sha256:ca5fd09...` | Compact, blended, Gaussian-like, and mixed catalogue products |

The two PyBDSF identities are unchanged from Phase 0. They run Rapthor's
5-sigma pixel, 3-sigma island, three-scale residual B3-spline à trous profile.
The controlled diagnostic supplies the same frozen mean and RMS maps through
PyBDSF's documented `rmsmean_map_filename` boundary. PyBDSF's own operational
background/RMS path remains primary. The
[PyBDSF processing reference](https://pybdsf.readthedocs.io/en/stable/process_image.html)
describes the residual à trous module and its scale controls.

AegeanTools 2.3.5 is the maintained published release as of the freeze. Its
[published wheel](https://pypi.org/project/aegeantools/2.3.5/) requires NumPy
2.x, whereas the governed Rapthor/PyBDSF runtime retains NumPy 1.26. Aegean
therefore runs in a separate image derived from the same immutable base. The
build verified the published wheel hash and captured dependency-inventory
hash `74f3787...`; its scientific stack includes NumPy 2.5.2, SciPy 1.17.1,
Astropy 7.2.2, and LMFit 1.3.4. This prevents an Aegean dependency upgrade from
changing either PyBDSF reference.

Aegean's primary blind run uses its documented standard 5-sigma seed,
4-sigma flood, covariance-enabled fit, internal background/noise estimation,
and island catalogue. A separately labelled 5/3-sigma diagnostic receives
the same frozen background and RMS products. The
[Aegean command reference](https://aegeantools.readthedocs.io/en/v2.3.4/includes/aegean.html)
documents these controls and the distinction between component and island
catalogues.

## Fresh populations and power

No prior source-finder output or scientific result is reused. Only reviewed
analytic generator geometries, truth definitions, beams, and WCS designs are
carried forward.

| Lane | Images | Purpose | Manifest SHA-256 |
| --- | ---: | --- | --- |
| Continuum | 600 across four beams and geometries | Extended, mixed, edge, invalid-pixel, artifact, scale, and tile strata | `9f88b8904b264e61c5a7445fd8a0cc966cf928d072d010dce3c6d47b6e8e6193` |
| Compact/blend | 800 | Compact, resolved, edge, equal-flux, and 2:1 blend catalogue behaviour | `55c6ecef09711219e45f3e6192cea130b17a02bded6b10e72e1a839743ce2e32` |

All 1,400 noise-seed images are disjoint from every checked-in historical
manifest and from one another. Both lanes have the `regression` role; the
Phase 5 qualification manifest remains unopened and unchanged.

The prospective power audit uses whole-image clustering and conservative
union lower bounds. The continuum lower bound is `0.998392`; the reviewed
Phase 4U compact design supplies `0.969928` for one reference and `0.909784`
after conservatively allowing three references. Their combined lower bound
is `0.908176`, above the frozen `0.90` minimum but intentionally close enough
that its assumptions matter. If an observed per-image paired standard
deviation exceeds a planning bound, the affected comparison is underpowered
and Step 2C-P fails closed. Sample size cannot be adapted after results are
opened.

## Finder-neutral association

Analytic and injected truth is authoritative; the finders are never matched
to one another or treated as votes. Every output is first mapped into the same
pixel-centred coordinate system and associated independently with truth.

- Compact candidates are eligible within half a restoring-beam FWHM.
- Extended candidates are eligible when support overlap relative to the
  smaller support is at least 0.10, or when the candidate centre lies within
  a one-beam dilation of truth support.
- Primary associations maximize cardinality, then overlap, then minimize
  normalized distance, with stable identifiers as the last tie-breaker.
- All eligible secondary edges are retained for duplicate, split, and merge
  metrics; a one-to-one assignment cannot hide topology errors.

Hebog contributes fitted Gaussian centres for compact components and the
confirmed detected-segment centroid for irregular emission. PyBDSF contributes
Gaussian centres for compact components, island masks, and a source moment for
extended position only when its grouping and source-model semantics align.
Aegean contributes component centres and an island-grouped union of fitted
three-sigma ellipses as an association proxy. That proxy is not promoted to a
segmentation mask: Aegean mask precision, recall, and IoU are unavailable,
not passes or failures.

## Binding decisions

Hebog must first pass every unchanged absolute truth gate. It must then be
non-inferior to both PyBDSF references on every applicable continuum metric
and stratum, and to Aegean on compact, blended, Gaussian-like, and mixed
catalogue metrics. Continuum metrics cover completeness, reliability,
integrated-flux median and p95 error, position median and p95 error,
duplicates, mask precision/recall/IoU, and split/merge fractions. Compact
metrics reuse the reviewed Phase 4R registry, including peak and integrated
flux, astrometry, association, and shape products where each finder provides
them.

There is no cross-metric, cross-morphology, or cross-reference compensation.
A reference failure cannot excuse a Hebog absolute failure. Missing binding
output makes that comparison unavailable and fails Step 2C-P. Scientific
outcomes are reviewed before runtime information.

A public challenge cut-out is deferred to Step 6 because this controlled host
does not currently hold a redistributable, checksum-bound input with curated
or injected truth. Real-data majority agreement will remain diagnostic, not
ground truth.

## Required implementation boundary

The next change must implement and test the finder-neutral matcher, FITS
materializer, and three isolated runners, then bind their committed hashes in
a separate execution decision. No finder output may be generated before that
review. Passing Step 2C-P will still require a reviewed scientific decision
before Step 3 opens.
