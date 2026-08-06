# Phase 5 scale-filter selection

**Status:** Step 2B completed with `select-neither`. The broader paired review
found that neither the beam-aware matched filter nor the undecimated wavelet
passed every absolute and candidate-to-candidate stratum gate. The initial
matched-filter selection is retained only as historical Step 2 evidence.
Step 3 and candidate-specific optimization remain blocked until a newly
frozen corrective design passes the same review. This is not multiscale
equivalence, complete Rapthor performance, or production-readiness evidence.

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

## Completed paired scientific re-evaluation

The initial rule treated each scientific metric as an absolute pass/fail gate
and compared cost once both candidates passed. That protected the minimum
contract but did not ask whether one passing candidate had a repeatable,
practically material scientific advantage. The matched filter's 8.585%
masked-response error is close to the 10% gate, while the wavelet's error is
0.397%. Conversely, the matched response has lower propagated noise in that
probe, so centre-response bias alone cannot establish which representation
has better detection or measurement behaviour.

Step 2B compared both candidates on the same prepared image, validity,
background, and RMS products over 84 exact analytic cases, ten development
images, and 100 fixed-seed regression images. It used the same 5-sigma seeds,
3-sigma support, connectivity, truth groups, and whole-image bootstrap for
both candidates.

The machine-readable pre-results protocol is
`config/contracts/phase-5-filter-paired-review.json`, SHA-256
`749d2393c485239bea6a897beaeb4a97b0b8ab7d8aff851646e43e857b4c993d`.
It binds the ten-image development and 100-image regression manifests, keeps
qualification closed, and leaves `step_three_authorized=false`.

The result is scientifically mixed rather than a cost tie. On exact analytic
truth, the matched filter had 7.49% median and 12.86% 95th-percentile response
error, versus 5.98% and 19.81% for the wavelet; both missed the 5%/10% gates.
The matched filter retained higher median calibrated response SNR (15.99
versus 11.32). The wavelet was much better on several straight masked
half-planes but worse at corners, irregular holes, and some edge cases.

On the generated regression population, both recovered every governed group.
The wavelet produced substantially better mean mask overlap (0.617 versus
0.239), but neither reached the frozen 0.8 gate. Both exceeded the 0.25-beam
95th-percentile position gate (0.444 wavelet and 0.462 matched). The wavelet's
mean fragmentation fraction was 0.167, above the 0.1 absolute gate and 0.15
worse than the matched filter; the matched result was 0.017. Flux measured
within candidate-retained support had median fractional error 0.145 for the
wavelet versus 0.059 for the matched filter, so the wavelet missed both the
0.1 absolute median gate and its paired margin. These trade-offs, plus
failures in finer scale, morphology, mask, edge, and SNR strata, prevent either
candidate from satisfying the no-compensation rule.

The reviewed machine-readable decision is
`config/contracts/phase-5-filter-paired-decision.json`. It records
`selected_family=null`, `step_three_authorized=false`,
`optimization_authorized=false`, and `qualification_opened=false`.
Independent human scientific review remains required before production
cutover.

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

## Historical provisional matched-filter representation

The machine-readable record captures the superseded initial Step 2 decision.
It is
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

The paired Step 2B evidence is
`benchmark-results/phase-5/filter-paired-review.json`; its exact checksum and
source-tree identity are frozen in the paired decision contract. The runner
is `scripts/benchmark/review_phase5_filters.py`.

Neither evidence record establishes production thresholded scale detections,
connectivity,
extended measurements, cross-scale reconciliation, real-residual behaviour,
PyBDSF equivalence, or complete `filter_skymodel` speedup. Those remain later
Phase 5 and Phase 7 gates. Step 2C must now freeze a corrective design; Step 3
remains blocked.
