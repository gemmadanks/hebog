# Phase 5 astrometry technical pre-review

**Status:** AI-conducted pre-review complete; independent human scientific
review remains open. The recommendation is to revise the astrometry protocol
prospectively before selecting a production representation. Step 3,
optimization, the external Step 2C-P run, and qualification remain blocked.

This review diagnoses the closed Step 2C-A evidence. It does not rerun an
image, change a result, rescore the confirmation, or open qualification. The
closed decision remains `reject-corrective-a`.

The audit used the frozen gate contract
`config/contracts/phase-5-scientific-gates.json`, the Step 2C-A protocol and
decision records, the endpoint compiler and estimator source, and ignored
evidence `benchmark-results/phase-5/corrective-a-review.json` with recorded
SHA-256
`b8eeaf7858b57b07d2c4ab9912e45792d2b5f59658b4f86256fb5ae801aace05`.

## Recommendation

Do not approve the current estimator and endpoint as-is. A successor
pre-results protocol should:

1. measure the catalogue tail directly over eligible truth groups while
   resampling complete images as clusters;
2. restore both frozen position summaries: median error at most 0.10 beam and
   95th-percentile error at most 0.25 beam;
3. treat the observable-domain flux centroid as Hebog's extended-object
   position, but map external finders only where their reported position has
   comparable meaning;
4. compare a direct original-pixel centroid with model-assisted alternatives
   on new development data, with morphology and model-adequacy controls; and
5. replace the scalar uncertainty proxy with a two-dimensional covariance or
   calibrated resampling result and test stated coverage by morphology, S/N,
   edge, and invalid-pixel status.

This is not a recommendation to relax the 0.25-beam ceiling. Correcting the
aggregation would remove four apparent failures in the viewed diagnostics,
but the curved-filament population still has a 0.4315-beam ordinary
group-level 95th percentile and therefore remains a real absolute failure.

## Closed evidence diagnosis

The frozen endpoint first takes the 95th percentile of the eligible groups in
each image, then takes the 95th percentile of those 100 image summaries. It is
therefore a 95th percentile of 95th percentiles. The diagnostic group-level
percentile below was already reported in the stored astrometry diagnostics; it
is not a replacement decision or a rescore.

| Failed stratum | Frozen nested endpoint | Group-level p95 | Gate |
| --- | ---: | ---: | ---: |
| Overall | 0.3597 | 0.2084 | 0.2500 |
| Curved filament | 0.4315 | 0.4315 | 0.2500 |
| Scale 2 | 0.4002 | 0.2429 | 0.2500 |
| Scale 4 | 0.3760 | 0.1954 | 0.2500 |
| Varying noise | 0.3597 | 0.2084 | 0.2500 |

The two statistics agree in a one-group stratum such as curved filament. They
diverge in strata containing several groups per image: three at scale 2, five
at scale 4, and six overall. Consequently the frozen statistic changes meaning
with stratum membership and is not one common catalogue-tail estimand. A
whole-image cluster bootstrap does not require this inner percentile: it can
resample images while retaining all eligible group rows within each selected
image.

The durable scientific gate also freezes a median position error of at most
0.10 beam, but the Step 2B--2C-A review contract and compiler bind only the
95th-percentile position endpoint. The closed Step 2C-A result must not now be
rescored against the missing endpoint. The next protocol should reconcile the
machine-readable contract and implementation before any output is viewed.

### Curved-filament result

The curved-filament mean offset is only 0.0136 beam, while its centred
95th-percentile scatter is 0.4294 beam. The failure is therefore dominated by
variance rather than a stable coordinate bias. Ninety-nine of its 100 results
used the model-assisted path, so the current normalized-cost and
model-to-moment disagreement checks did not identify the problematic cases.

The confirmation varies the noise seed over one fixed three-component curved
truth recipe. It establishes a reproducible failure for that recipe, but it
does not establish behaviour across curvature, orientation, length-to-width
ratio, knot contrast, surface brightness, or component count. A new
development matrix should vary those properties before freezing a fresh
confirmation population.

The likely mechanism is model-selection instability: the estimator chooses up
to six beam-separated peaks above 6 sigma, fits a robust local-RMS-weighted
Gaussian mixture, and shrinks its centroid halfway toward a robust moment.
Noise can change the selected component count and fitted mixture for a curved
object. That explanation is an inference from the algorithm and variance
pattern; the closed evidence did not retain per-seed component-count and fit
diagnostics sufficient to prove it.

## Relation to established source finders

[Condon (1997)](https://doi.org/10.1086/133871) derives position and other
parameter errors for a two-dimensional elliptical Gaussian. This is a sound
compact or Gaussian-component precedent, not a complete uncertainty model for
an irregular segmented source whose support and component count are selected
from the same noisy image.

[PyBDSF's algorithm documentation](https://pybdsf.readthedocs.io/en/stable/algorithms.html)
describes multi-Gaussian island fitting followed by a source centroid from
moment analysis. It reports a maximum position separately. Its default source
errors use the Condon relations; an optional Monte Carlo mode adds uncertainty
from constituent Gaussians for multi-component sources. With `atrous_do`, it
fits residual wavelet-scale emission with further Gaussians before forming
source products. Hebog's mixture-assisted centroid is therefore
standard-adjacent, but Hebog should not claim that its 50/50 shrinkage or
uncertainty proxy reproduces PyBDSF.

[Aegean 2.0](https://doi.org/10.1017/pasa.2018.3) shows that position and peak
uncertainties for Gaussian fits to correlated radio pixels are best estimated
with the data covariance in the Fisher information matrix. Omitting that
covariance underestimates uncertainty in its simulations. Aegean's
[catalogue documentation](https://aegeantools.readthedocs.io/en/dev-aegean/includes/aegean.html)
reports a Gaussian centre for a fitted component but the brightest pixel for
an island. Neither is automatically equivalent to Hebog's observable-domain
flux centroid for a filament or shell.

The [ASKAP/EMU source-finding challenge](https://doi.org/10.1017/pasa.2015.37)
excluded its extended-source challenge from simple positional-accuracy
statistics because genuine structure can contribute to finder-to-truth
offsets. The later [Hydra II comparison](https://doi.org/10.1017/pasa.2023.29)
also records finder-dependent flux-weighted positions and component grouping
for diffuse and blended systems. These findings support explicit position
semantics and morphology-stratified truth comparisons rather than treating
all reported catalogue coordinates as interchangeable.

[ProFound's radio evaluation](https://doi.org/10.1093/mnras/stz1462) provides
the complementary precedent: pixel segmentation can trace complex extended
emission that a Gaussian description may not represent well. This supports
keeping a direct original-pixel centroid as the general extended-source
baseline and requiring evidence before a Gaussian model assists it.

## Estimator assessment

The current estimator is scientifically plausible for compact, blended, or
approximately Gaussian emission, but it is not yet justified as Hebog's
general estimator for irregular extended objects. In particular:

- the fit minimizes local-RMS-standardized residuals with diagonal weights,
  not the full correlated-pixel covariance;
- a hard peak threshold and component cap make the estimator discontinuous as
  noise changes the selected model;
- the reported uncertainty does not propagate the fitted-parameter
  covariance, component selection, robust loss, 50/50 shrinkage, association,
  support selection, background/RMS estimation, or model mismatch; and
- accepting 599 of 600 model fits while retaining the curved-filament failure
  shows that fit convergence and model/moment proximity are not sufficient
  model-adequacy tests.

The next study should compare, without morphology-specific tuning:

- a direct background-subtracted original-pixel flux centroid on reconciled
  support;
- a covariance-aware Gaussian-mixture centroid where a declared morphology or
  adequacy test admits it; and
- a robust or resampling-based alternative for irregular and truncated
  support.

Model assistance should be accepted only when it improves a fresh
morphology-stratified validation suite and its selection is stable. Otherwise
the direct centroid should remain the transparent baseline, with typed
unavailability for cases that cannot support a meaningful position.

## Uncertainty assessment

The stored uncertainty is the square root of summed x/y moment variances,
inflated by one Gaussian beam area and divided by the major-axis FWHM. This is
a useful scale diagnostic, but it is not a complete positional covariance.
The stored 95th percentile of error divided by this scalar is 2.56 overall and
3.50 for curved filaments.

Those ratios are evidence of under-dispersion, but they are not themselves a
coverage test because the scalar's probabilistic meaning was never frozen. For
example, even an isotropic, correctly calibrated two-dimensional Gaussian has
a radial-error distribution that is not a one-dimensional standard normal.

A successor protocol should report a 2-by-2 position covariance in pixel and
sky coordinates, then validate:

- per-axis normalized residual bias and dispersion;
- 68% and 95% error-ellipse coverage using Mahalanobis distance;
- coverage by morphology, S/N, scale, edge, invalid-pixel, and truncation
  stratum; and
- calibration conditional on whether the direct or model-assisted estimator
  was selected.

For nonlinear support and model selection, correlated-noise parametric
resampling or repeated injected realizations should calibrate coverage even if
an analytic covariance is used as the production approximation. The protocol
must state how background/RMS and model-selection uncertainty are included or
why they are negligible.

## Proposed human-review decisions

The independent scientist should explicitly accept, amend, or reject these
recommendations before further implementation:

1. **Position meaning:** observable-valid-domain flux centroid for Hebog
   extended objects, with peak and component coordinates reported separately
   when available.
2. **Tail estimand:** one eligible astronomical truth group per observation,
   direct median and p95 summaries, and whole-image cluster resampling. Any
   per-image worst-object statistic must have a separate name, limit, and
   power analysis.
3. **Estimator family:** direct original-pixel baseline, with model assistance
   admitted only by predeclared morphology-neutral adequacy and stability
   evidence.
4. **Uncertainty:** a two-dimensional covariance and declared coverage
   protocol, not an uncalibrated radial scalar alone.
5. **Fresh evidence:** a new development matrix with diverse irregular
   morphology, then a seed- and geometry-disjoint confirmation. No reuse of
   the Step 2C-A confirmation and no opening of qualification.
6. **External mapping:** PyBDSF source-centroid comparisons where product
   semantics align; Aegean component astrometry only for compact/Gaussian
   scope; no forced Aegean island-position comparison for irregular extended
   centroids.

Only after these decisions are recorded should Hebog freeze the successor
pre-results protocol and Step 2C-P comparison. The new candidate must pass
every absolute truth gate before performance or external non-inferiority can
make it eligible.
