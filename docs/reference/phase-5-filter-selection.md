# Phase 5 scale-filter selection

**Status:** provisional development decision pending Phase 5 Step 2B. The
initial screen selected the beam-aware matched-filter bank because both
predeclared candidates passed its analytic response gates and the matched
filter had the smaller bounded structural cost. The substantially lower
wavelet error in the masked and edge probes means that screen is not
sufficient to authorize candidate-specific Step 3 work. A broader paired
scientific comparison must now select the representation before performance
optimization. This is not multiscale equivalence, complete Rapthor
performance, or production-readiness evidence.

The comparison used only the ten frozen development realizations. The
qualification manifest and all qualification results remained unopened.

## Scientific response

The serial oracle consumes the existing image, validity, background, and RMS
planes. It does not estimate a background, regenerate an RMS product, rerun
compact detection, or persist an image-sized response. Each candidate was
tested against:

- beam-aligned unit-integrated-flux Gaussians at 1, 2, and 4 restoring-beam
  FWHM;
- constant and affine prepared backgrounds;
- invalid and NaN support;
- a source clipped by the image edge; and
- two separated compact sources at the smallest scale.

Both candidates passed the predeclared 2% unit-response, 10% masked-response,
10% edge-response, exact prepared-background, and complete finite development
truth-window gates.

| Candidate | Unit response error | Masked error | Edge error | Finite governed truth windows |
| --- | ---: | ---: | ---: | ---: |
| Beam-aware matched filter | `4.44e-16` | `0.08585` | `0.07588` | `1.000` |
| Undecimated wavelet | `8.88e-16` | `0.00397` | `0.00076` | `1.000` |

The Step 1 minimum support fraction of 0.8 was inconsistent with the required
image-edge stratum: the governed clipped source has between 0.5 and 0.8 of its
filter support visible. Step 2 therefore amends the minimum to 0.5. At or
above that boundary, normalized convolution recovered the analytic flux
within the 10% edge gate; below it the response remains typed unavailable.
This amendment was made from analytic and development evidence before any
qualification result was generated.

## Required paired scientific re-evaluation

The initial rule treated each scientific metric as an absolute pass/fail gate
and compared cost once both candidates passed. That protected the minimum
contract but did not ask whether one passing candidate had a repeatable,
practically material scientific advantage. The matched filter's 8.585%
masked-response error is close to the 10% gate, while the wavelet's error is
0.397%. Conversely, the matched response has lower propagated noise in that
probe, so centre-response bias alone cannot establish which representation
has better detection or measurement behaviour.

Step 2B therefore blocks Step 3 until both candidates have been compared on a
frozen non-qualification matrix of mask geometry, support fraction, image
edge, morphology, scale, nearby-source, varying-RMS, correlated-noise, and SNR
cases. The comparison must record paired flux bias, tail error, calibrated
response SNR, noise calibration, completeness, reliability, astrometry,
support availability, fragmentation or negative-lobe behaviour, and mask
topology by governed stratum. Practical margins and confidence rules must be
frozen before the new results are inspected.

The final decision is science-first: every absolute and paired stratum gate
must pass, with no compensation by aggregate results. Cost distinguishes the
candidates only when neither has a practically material scientific advantage.
If the wavelet is materially better, it will be selected at its current
bounded cost and optimized afterward. Qualification remains unopened.

## Bounded cost comparison

The controlled runner performed one warm-up followed by five complete
measurements of all ten 1,024-square development images for each candidate.
Logical workspace includes retained response, effective-RMS, support, and
validity planes plus maximum simultaneous temporaries and filter kernels; it
is not a process-RSS claim.

| Candidate | Median per ten images | Convolutions per image | Temporaries | Maximum halo | Logical workspace |
| --- | ---: | ---: | ---: | ---: | ---: |
| Beam-aware matched filter | `2.05222 s` | 9 | 7 | 34 px | 159,485,104 B |
| Undecimated wavelet | `2.57138 s` | 11 | 9 | 49 px | 176,399,304 B |

The undecimated candidate reuses its four distinct Gaussian smoothings across
the three dyadic differences. Even with that reuse, it needs two more
convolutions, two more simultaneous temporary planes, and a 15-pixel wider
halo. The matched bank also has a direct positive-kernel masked-support and
local-noise interpretation. Its measured median was lower on this environment,
but timing was only the last tie-breaker after science and structural cost.

## Provisional matched-filter representation

The machine-readable record captures the initial Step 2 decision and must be
amended after Step 2B. It is
`config/contracts/phase-5-filter-selection.json`.

- Each scale uses an elliptical Gaussian aligned with the restoring beam and
  calibrated so a nominal unit-integrated-flux Gaussian has response 1
  Jy/beam.
- Kernels truncate at four major-axis sigma. The relative Gaussian tail at
  the support boundary is at most `exp(-8)`, approximately `3.3546e-4`.
- Development halos are 9, 17, and 34 pixels for the 1, 2, and 4 beam scales.
  The general halo is the ceiling of four times the nominal-scale restoring-
  beam major sigma in pixels.
- SciPy `fftconvolve` supplies constant-boundary convolution. Valid support is
  normalized explicitly; a support fraction below 0.5 is unavailable.
- Local independent-noise propagation uses the squared response kernel and
  the reused Phase 2 RMS. A restoring-beam Gaussian covariance supplies the
  recorded correlated-to-independent gain for each scale.
- Inputs, kernels, response, support, and effective RMS remain float64.
  Lower precision and native code are not authorized.
- Prepared inputs are shared across scales. Response planes are transient and
  are not added to Zarr or another storage backend.

No ADR was needed for the initial screen: it retained the existing
NumPy/SciPy dependency, serial-oracle boundary, float64 policy, and Zarr
architecture. It neither adds a dependency nor changes scheduler or storage
ownership.

## Evidence and limitations

The ignored typed evidence is
`benchmark-results/phase-5/filter-selection.json`, SHA-256
`f250f4b6e938db91eb4811d68ba048e72ed3ba4595caba36e2334a926338917f`.
It binds source-tree SHA-256
`6150aa39661e63bca5c9d6303d34169ca3a97e155fbe28e16d0bf67bb179c9cc`,
the complete development dataset identity, dependency inventory, environment,
every measured repetition, analytic errors, and structural costs.

The evidence does not establish thresholded scale detections, connectivity,
extended measurements, cross-scale reconciliation, real-residual behaviour,
PyBDSF equivalence, or complete `filter_skymodel` speedup. Those remain later
Phase 5 and Phase 7 gates. Phase 5 Step 2B is next; Step 3 remains blocked.
