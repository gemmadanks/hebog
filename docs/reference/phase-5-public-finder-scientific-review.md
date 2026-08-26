# Phase 5 public-finder scientific review

**Status:** complete post-result review of terminal decision `954077e9...`.
The sealed one-look remains `fail`; public evidence, tuning, rerunning,
rescoring, cutover, and release remain closed.

This review opened only after the write-once campaign, analysis, and decision
were terminal. It did not change the matcher, gates, catalogue, or any terminal
file. Its purpose is to distinguish a Hebog science defect from a protocol
defect before choosing the next development work.

## Executive conclusion

The campaign exposed both kinds of defect.

1. **The public protocol is not an official SDC1 comparison.** Its fixed
   0.5-beam position-only matcher and inherited absolute gates were never
   calibrated against the official SDC1 scorer or submitted teams. The
   official source-finding match uses position, size, and flux together and a
   null catalogue to estimate chance associations. Hebog's public catalogue
   supplies neither fitted nor deconvolved shape, core fraction, nor source
   class, so the official score cannot be computed. The terminal fail is valid
   under its frozen stress-test rules, but it is not a challenge-equivalent
   score and must not be presented as one.

2. **Hebog has a real depth-dependent association defect.** On the Hydra deep
   image, the three-beam multiscale association dilation bridges independently
   seeded sources into very large connected islands. The deepest image then
   produces fewer catalogue entries than the shallow image and only 38
   deep--shallow matches. The RMS maps track the observed noise, so gross RMS
   normalization is not the cause.

3. **SDC1 still reveals a real low-SNR sensitivity gap.** Completeness is only
   6.59% at apparent peak SNR 5--8 and 22.44% at SNR 8--10. The measured RMS is
   slightly *lower* than the constant noise used for truth admission, so RMS
   inflation cannot explain this. The effective catalogue threshold is
   materially higher than the nominal five-sigma seed rule.

4. **Do not optimize photometry first.** Among accepted matches, integrated
   flux meets the frozen limits above SNR 20. The aggregate flux failure is
   concentrated at low SNR and is entangled with selection and association.

The next science change should therefore make multiscale ownership preserve
independent seeded islands, then provide source shapes and a prospectively
reviewed SDC1 scorer adapter. SDC1 and Hydra are now viewed development and
regression data; they cannot become fresh held-out qualification evidence.

## Evidence and review boundary

The exact terminal evidence is:

| Record | SHA-256 |
| --- | --- |
| Campaign | `42abb896b452ee9143156b88ad46ea21033e63dbd8060185242ffa10c30b0c71` |
| Analysis | `975978fbc0351184ac0f80706afbe211a1f7d6fce9f10bb7b49eea242bb5aeee` |
| Decision | `954077e9af7bcd34d42d2a273a08dbd7aa8cdd43427c6aa28ec3de5d74465e3a` |
| Protocol | `f29100bea8396df945672f97e6eeb63f7ec6a4acef3cd8e8eef4a9058788e6df` |

Post-result diagnostics read the sealed truth, catalogue, RMS, background,
mask, and label products. They varied only diagnostic grouping or association
radius in memory. They did not publish an alternative analysis or decision.
All such values below are explicitly non-binding.

The scientific reference points are the official [SDC1 challenge
page](https://www.skao.int/en/464/ska-science-data-challenge-1), the official
[data description](https://www.skao.int/sites/default/files/documents/SKA-TEL-SKO-0001001-SKA_DataChallengesDataDescription-signed.pdf), the
[SDC1 results paper](https://doi.org/10.1093/mnras/staa3023), the official
[scorer documentation](https://developer.skatelescope.org/projects/sdc1-scoring/en/latest/sdc1_scorer.html), and the [Hydra
I](https://doi.org/10.1017/pasa.2023.24) and [Hydra
II](https://doi.org/10.1017/pasa.2023.29) papers.

## What the SDC1 terminal result establishes

The frozen endpoint admits truth sources with analytic apparent peak SNR at
least five, matches within 0.5 synthesized beams, and applies one-to-one
maximum-cardinality assignment. Under those exact rules:

| Metric | Result | Frozen limit |
| --- | ---: | ---: |
| Completeness | 0.32463 | at least 0.90 |
| Reliability | 0.75598 | at least 0.95 |
| Median absolute integrated-flux error | 0.10475 | at most 0.10 |
| P95 absolute integrated-flux error | 0.30592 | at most 0.25 |
| Position p95 | 0.27253 beam | at most 0.50 beam |
| Duplicate fraction | 0.00000 | at most 0.02 |
| Merge fraction | 0.00564 | at most 0.10 |

All eight selected strata fail the same first four metrics. This consistency
rules out a single corrupt tile, but it does not identify the cause.

### SNR dependence

The terminal report-only curve separates threshold behaviour from bright-
source behaviour:

| Apparent peak SNR | Truth | Matches | Completeness | Median flux error | P95 flux error |
| --- | ---: | ---: | ---: | ---: | ---: |
| 5--8 | 7,954 | 524 | 0.06588 | 0.15837 | 0.55610 |
| 8--10 | 3,061 | 687 | 0.22444 | 0.13846 | 0.42206 |
| 10--20 | 7,346 | 3,411 | 0.46433 | 0.12147 | 0.31148 |
| 20--50 | 5,105 | 2,602 | 0.50970 | 0.09972 | 0.20581 |
| at least 50 | 1,735 | 957 | 0.55159 | 0.07171 | 0.12809 |

For an isolated source in Gaussian noise, a five-sigma measured threshold has
idealized detection probability

\[
P(\hat{s} \ge 5 \mid s) = \Phi(s - 5),
\]

where \(s\) is true peak SNR and \(\Phi\) is the standard-normal cumulative
distribution. Averaged over the selected admitted truth SNRs, this simplified
ceiling is 0.94969. It ignores morphology, crowding, correlated noise, and
selection, so it is not an acceptance prediction. It does show that the
observed 0.32463 cannot be explained merely by including sources arbitrarily
close to five sigma.

The candidate RMS maps also exclude gross noise inflation. Across the eight
cores, median RMS is 66.06--66.82 nJy beam\(^{-1}\), versus the 73 nJy
beam\(^{-1}\) constant used by truth admission. Candidate peak SNR has fifth
percentile 7.84 despite the nominal five-sigma seed. The sensitivity loss lies
after, or in addition to, RMS estimation: support construction, minimum area,
association, catalogue admission, or the mapping between simulated sources
and Hebog segments.

### Association sensitivity

Position-only diagnostic radii show that the frozen result is highly sensitive
to source association:

| Radius | Overall matches | Completeness | SNR at least 50 matches | Bright completeness |
| ---: | ---: | ---: | ---: | ---: |
| 0.25 beam | 7,688 | 0.30507 | 825 | 0.47550 |
| 0.5 beam | 8,181 | 0.32463 | 957 | 0.55159 |
| 1 beam | 8,738 | 0.34673 | 1,115 | 0.64265 |
| 2 beams | 9,696 | 0.38475 | 1,283 | 0.73948 |
| 5 beams | 10,709 | 0.42494 | 1,465 | 0.84438 |

Changing the truth location from centroid to core changes overall matches only
from 8,181 to 8,173. Coordinate-column choice is not the explanation.

Larger position-only radii are not a valid correction. The selected truth
density is approximately \(7.51\times10^{-4}\) source pixel\(^{-1}\), and the
beam spans approximately six pixels. Under a deliberately simplified uniform
Poisson model, the probability of at least one chance truth source within
radius \(r\) beams is

\[
P_{\mathrm{chance}}(r) \approx
1 - \exp\left[-\rho\pi(6r)^2\right].
\]

That approximation rises from 0.021 at 0.5 beam to 0.288 at 2 beams and 0.880
at 5 beams. It is not a null-catalogue measurement, but it explains why a
position-only radius cannot safely recover the additional apparent matches.
The official SDC1 scorer instead combines position, source size, and flux and
measures chance matches with a randomized catalogue.

The 2,641 candidates unmatched at 0.5 beam have median measured peak SNR
27.94. Among the 778 unmatched truth sources above SNR 50, the median distance
to the nearest candidate is 2.30 beams. These are strong signs of source-
identity disagreement rather than a catalogue consisting only of weak noise
excursions, but only source-aware matching and a null control can quantify how
many are genuine.

### Morphology and flux

Univariate completeness rises from 0.24580 below one intrinsic major-axis beam
to 0.52594 above five beams. That trend is confounded by SNR. Restricting to
SNR at least 50 makes completeness nearly flat:

| Intrinsic truth major axis | Truth | Matches | Completeness |
| --- | ---: | ---: | ---: |
| below 1 beam | 411 | 223 | 0.54258 |
| 1--2 beams | 625 | 342 | 0.54720 |
| 2--5 beams | 557 | 311 | 0.55835 |
| at least 5 beams | 142 | 81 | 0.57042 |

Apparent size by itself therefore does not explain the bright-source deficit.
Primary-beam response also has no adverse radial signature: completeness is
0.37891 below response 0.5 and 0.28260 above 0.9. That inverse trend is likely
confounded by source density and selection, but it rules against primary-beam
attenuation as the dominant simple cause.

Matched-source flux is already within the frozen limits above SNR 20. The
correct order is therefore to repair detection and source association, then
re-evaluate flux. Tuning the flux aperture against the present matched subset
would optimize on selection bias.

### Missing characterization

All terminal shape diagnostic counts are zero. The public catalogue records
`deconvolution_status=unavailable`, no fitted shape, and no deconvolved shape
for every row. It also does not classify SDC1 populations or estimate core
fraction.

These fields are not required by Rapthor's narrow filtering contract, but they
are required to answer the broader stakeholder question “how does Hebog
perform on SDC1?” using challenge semantics. Until they exist, the official
global score and a faithful source-finding cross-match remain unavailable.

Count-only inspection of the nine published 1.4-GHz, 1000-hour submissions
places Hebog's 10,823 selected-core entries within the very broad submitted
range: examples include 8,301 for ICRAR, 8,833 for `hs`, 15,729 for Shanghai,
18,919 for ARCIt-CACAO, and 21,115 for EngageSKA. These counts use only the
published coordinate columns and are post-result diagnostics; they say
nothing about correctness. They do show that catalogue cardinality alone is
not a defensible team comparison.

## Hydra root-cause review

Hydra is non-binding because the EMU Pilot field has no astronomical truth.
Its deep--shallow comparison is nevertheless a strong invariance test: adding
noise should not radically change the identities of high-SNR sources.

### RMS is plausible

| Image | Sampled image MAD sigma | Median Hebog RMS | Candidate count |
| --- | ---: | ---: | ---: |
| Deep | 32.94 microJy beam\(^{-1}\) | 30.52 microJy beam\(^{-1}\) | 356 |
| Shallow | 175.81 microJy beam\(^{-1}\) | 169.97 microJy beam\(^{-1}\) | 413 |

The RMS ratios track the image-noise ratio closely. A spatial or robust
comparison may still find local defects, but gross RMS normalization cannot
explain why the deeper image yields fewer sources.

### Multiscale ownership merges sources

The qualified candidate creates association support by dilating retained and
reconstructed multiscale support by three beam major axes, labels the connected
union, and assigns retained pixels the union label. That policy was successful
on frozen synthetic Continuum cases, but it has a different meaning in a deep,
crowded field: faint support builds bridges between independently seeded
sources.

| Label diagnostic | Deep | Shallow |
| --- | ---: | ---: |
| Retained-mask fraction | 0.04139 | 0.00867 |
| Positive labels | 357 | 423 |
| Median label area | 322 px | 169 px |
| P95 label area | 6,248 px | 777 px |
| Maximum label area | 55,186 px | 2,737 px |
| Labels above 10,000 px | 9 | 0 |

The catalogue contains one entry per resulting segment, so these bridges
directly collapse catalogue cardinality. Only 38 deep entries match shallow
entries within the frozen half-beam radius. Published deep finders have many
thousands of entries in the same Hydra archive, while Hebog has 356. Finder
catalogues use different semantics and are not truth, but the order-of-
magnitude discrepancy and the label topology point to the same mechanism.

This is a high-confidence cause because it links an explicit algorithmic
operation to the observed intermediate product and terminal catalogue. It is
not merely a correlation with a tuning parameter.

## Causal assessment

| Hypothesis | Assessment | Confidence |
| --- | --- | --- |
| Gross RMS overestimation | Excluded as primary cause by SDC1 and Hydra RMS diagnostics | High |
| Wrong core-versus-centroid column | Excluded; match count is effectively unchanged | High |
| Primary-beam attenuation error | No simple adverse radial signature; retain as a unit/provenance check | Moderate |
| Fixed 0.5-beam matching | Material protocol limitation, especially for dense and complex sources | High |
| Low-SNR catalogue admission | Real capability gap beyond RMS estimation | High |
| Three-beam multiscale association | Direct cause of Hydra deep-image island bridging | High |
| Integrated-flux measurement | Acceptable for matched sources above SNR 20; secondary until association is repaired | High |
| Tile halo or one corrupt stratum | Not supported by the uniform failures and normal SDC1 label sizes | Moderate |
| Missing fitted/deconvolved shapes | Confirmed public-catalogue capability gap | High |

## Prospective recovery plan

No item below is authorized by this review.

1. **Repair ownership before thresholds.** Replace three-beam connected-union
   labelling with seeded ownership that can attach multiscale support to an
   existing island without joining independent seed basins. Add analytic
   tests for two nearby sources joined by diffuse support, deep--shallow
   monotonicity, blends, and genuine single extended sources.

2. **Complete the public source record.** Publish fitted and deconvolved major
   axis, minor axis, and position angle with explicit units and unavailable
   states. Preserve the narrow Rapthor API, but allow the validation adapter to
   construct an SDC1-compatible source-finding record.

3. **Redesign the SDC1 protocol prospectively.** Use the official scorer's
   source-finding match dimensions, run its null-catalogue control, establish
   all nine published catalogue mappings, and compare SNR-dependent curves on
   identical regions. Calibrate any pass limits before opening corrected
   products. Keep official global scoring unavailable unless Hebog genuinely
   supplies the characterization and classification fields it requires.

4. **Prevent regression cycling.** Treat the viewed SDC1/Hydra evidence as
   development and regression data. After a correction, replay every closed
   Phase 5 regression family, including compact, Continuum, boundaries,
   blends, masks, and the Hydra depth-invariance diagnostic, before proposing
   fresh identities.

5. **Use fresh evidence for qualification.** A future passing public
   development result cannot itself close Phase 5. Freeze a new held-out
   qualification population and obtain named scientific and engineering
   approval before any one-look execution.

## Decision

The scientific failure review is complete. Phase 5 remains open, and the
current terminal decision remains `fail`. The next governed task is a
prospective pre-review for the seeded-island ownership and public-catalogue
shape work. No campaign should be rerun and no gate should be changed until
that plan and the corrected public protocol have separate named approval.
