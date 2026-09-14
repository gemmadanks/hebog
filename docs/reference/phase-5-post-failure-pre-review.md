# Phase 5 post-failure scientific pre-review

**Status:** technical scientific pre-review complete; approval recommended
before fresh evidence is frozen. The closed confirmation remains a failure and
is not rescored or reused as confirmation. Step 3, optimization, runtime
interpretation, and qualification remain closed.

This review covers the prospective Continuum and compact corrections made
after decision `70c17ba...` and the design of a new comparison population. It
uses the closed analysis only as independent planning evidence. Its
machine-readable power record is ignored benchmark output with SHA-256
`31ca691e1c5fc7ca905e0ad874906533ed55b7a4746c68543457951264aba07d` and
can be reproduced with:

```console
uv run python scripts/validation/review_phase5_post_failure_power.py
```

## Recommendation

Approve the corrected candidate for one fresh, seed-disjoint external
comparison after the remaining truth and protocol seams are implemented and
reviewed. Do not interpret the existing regression diagnostics as equivalence
to PyBDSF or Aegean.

The candidate is scientifically credible because it restores original-pixel
photometry, retains explicit segmentation, uses a sub-beam morphological
cleanup, and returns compact fitting to the previously reviewed beam-or-free
model selection. These choices are adjacent to established source-finder
practice, but they are not intended to reproduce another finder's internal
algorithm. Adoption still depends on unchanged truth gates and direct paired
comparisons.

Before freezing the fresh identities:

1. extend observable-domain truth from integrated flux to the corresponding
   per-group observable centroid and support metadata;
2. bind a new compiler and runner without changing the closed programs;
3. replace the coarse family power table with the exact 226
   endpoint/reference assumptions in this review;
4. freeze 1,600 Continuum realizations, balanced as 400 fresh seeds over each
   of the four reviewed geometries, and retain 800 fresh compact/blend
   realizations; and
5. preserve every absolute gate, paired non-inferiority margin, external
   mapping, failure denominator, and the one-terminal-look rule.

## Candidate assessment

### Continuum integrated flux

The corrected measurement sums signed background-subtracted original pixels
inside a bounded four-major-beam aperture. Overlapping apertures use nearest
detected-segment ownership, so flux is not counted twice. This repairs the
closed candidate's threshold-truncated flux while retaining the exact detected
support for position.

The approach is transparent and appropriate for irregular extended emission.
It resembles segmentation/aperture photometry more than PyBDSF's fitted
Gaussian source sums. PyBDSF fits Gaussians to islands and, with its wavelet
option, fits additional residual-scale Gaussians before forming source
products. Consequently comparable output is the scientific requirement;
matching PyBDSF's internal estimator is not.

The main risk is variance: a large signed aperture admits more background
noise, and a nearest-support boundary can allocate overlapping wings to the
wrong segment in a close blend. The fresh comparison must therefore retain
the integrated-flux median and p95 gates in every morphology, edge, masked,
scale, and blend stratum. The prospective 600-source diagnostic
`0.04979/0.17304` median/p95 error passes the `0.10/0.25` absolute limits but
is not external evidence.

### Continuum mask cleanup

A three-by-three binary opening is smaller than the sampled restoring beams in
the governed data and removes isolated flood-threshold protrusions without
growing a mask or merging labels. This is a reasonable scale-aware
morphological cleanup. Its risk is removal of genuine beam-thin filamentary
support or fragmentation of one labelled source. The existing curved
filament, diffuse, edge, invalid-pixel, and tile-boundary strata remain
binding. On the 100-image regression population, precision/recall/IoU were
`0.91778/0.90964/0.84104`; those values justify confirmation, not promotion.

### Observable-domain truth

Comparing an edge or masked source with injected flux outside the valid image
domain is scientifically incorrect. The prospective flux helper now integrates
only finite injected signal on valid pixels. The compiler must apply the same
domain to each truth group's centroid and support-derived metadata. Using an
observable flux with the old full-plane centroid would mix two different truth
populations. Truth normalization must remain independent of every finder's
detected mask.

### Compact measurement

The beam-or-free selection restores the previously reviewed choice between a
beam-constrained and a free Gaussian model. Position and position angle come
from the selected model; total association flux uses a 1.5-sigma aperture with
the analytic Gaussian enclosed-flux correction. This is closer to PyBDSF and
Aegean's Gaussian-component practice than the Continuum segmentation path,
while retaining Hebog's explicit model choice.

The 100-image Phase 4R regression result passes the existing compact absolute
limits: position-angle median/p95 `0.71624/8.96084` degrees and association
flux median/p95 `0.03712/0.18053`. Because the closed candidate failed 13
Aegean comparisons, all Aegean-binding compact metrics must be rerun on fresh
seeds. No Aegean comparison is forced onto irregular Continuum masks, where
its Gaussian component coordinates do not have the same meaning.

## Variance diagnosis and revised population

The former audit used one standard deviation and a nominal comparison count
for each metric family. It allocated 70 comparisons to most families and 56
to each mask family, including an allocation for report-only position median.
The sealed compiler actually produced 226 paired binding Continuum
endpoint/reference comparisons. Their observed standard deviations varied
sharply by stratum and reference.

| Metric family | Old bound | Largest closed SD | New largest endpoint bound |
| --- | ---: | ---: | ---: |
| Completeness | 0.0800 | 0.0577 | 0.0800 |
| Reliability | 0.0800 | 0.0809 | 0.1011 |
| Integrated-flux median | 0.2000 | 0.1872 | 0.2340 |
| Integrated-flux p95 | 0.2500 | 0.1776 | 0.2500 |
| Position p95 | 0.2500 | 0.7983 | 0.9978 |
| Duplicate fraction | 0.0300 | 0.4741 | 0.5926 |
| Mask precision/recall/IoU | 0.1500 | 0.0395 | 0.1500 |
| Split fraction | 0.0600 | 0.3473 | 0.4341 |
| Merge fraction | 0.0600 | 0.0000 | 0.0600 |

The new planning unit is one exact endpoint/reference comparison. Its standard
deviation is the larger of the old family bound and 1.25 times that
comparison's closed standard deviation. This retains the prior protection,
adds 25% headroom, and prevents an easy stratum from concealing a variable
one. Only half of a favourable closed paired difference is retained as the
planning alternative; an unfavourable difference is planned at equality.
This shrinkage reduces dependence on the failed candidate while recognizing
that the references contribute much of the binary topology and position-tail
variance.

The confidence calculation retains the existing one-sided 95% cluster-normal
planning approximation and conservative union lower bound. With compact held
at its reviewed 800-realization power:

| Continuum images | Continuum lower bound | Joint lower bound |
| ---: | ---: | ---: |
| 600, former count under revised assumptions | 0.27749 | 0.18728 |
| 1,550, mathematical minimum | 0.99023 | 0.90001 |
| 1,600, recommended balanced design | 0.99227 | 0.90205 |

The selected 1,600 images are the smallest round population that balances four
geometries at 400 images each and exceeds the exact 1,550-image minimum. With
the unchanged 800-image compact lane, the campaign contains 2,400 fresh
inputs. If any observed paired standard deviation exceeds its predeclared
endpoint bound, that comparison remains underpowered; a favourable confidence
interval cannot compensate.

## Relation to established practice

[PyBDSF's algorithm documentation](https://pybdsf.readthedocs.io/en/stable/algorithms.html)
supports thresholded islands, Gaussian decomposition, moment-derived source
centroids, and optional wavelet residual fitting. The corrected Hebog compact
path is standard-adjacent to its Gaussian measurements. Hebog's Continuum path
deliberately uses original-pixel segment photometry so irregular emission is
not forced into a Gaussian total-flux model.

[Aegean 2.0](https://doi.org/10.1017/pasa.2018.3) supports covariance-aware
Gaussian component fitting and is an appropriate compact comparator. Its
component centre is not a semantic reference for an irregular shell or
filament centroid.

[ProFound's radio evaluation](https://doi.org/10.1093/mnras/stz1462) provides
precedent for pixel segmentation and flux measurement of complex radio
emission. The ASKAP/EMU source-finding challenge and later cross-finder studies
also show that component grouping and extended-source positions are
finder-dependent. These precedents support Hebog's explicit compact versus
Continuum measurement semantics and outcome-based comparison with established
finders.

## Approval boundary

Approval of this review would authorize implementation and freezing of the
fresh protocol identities. It would not authorize campaign execution. A later
preflight must bind the exact manifests, runner, compiler, evaluator, runtime
images, core allocation, storage requirement, and one-look execution decision.
Only a passing scientific decision may open Step 3 or permit runtime
interpretation.
