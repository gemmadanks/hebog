# Phase 5 detected-segment position confirmation review

**Status:** the single authorized Step 2C-HR confirmation passed all 60
binding endpoints on 400 images and 2,400 eligible astronomical groups. The
detected-segment centroid is confirmed for the external source-finder
comparison protocol. Step 2C-P execution, Step 3, optimization, and
qualification remain unauthorized.

The confirmation ran once from committed runner `0e37424`, after Gemma Danks's
named scientific approval in committed decision `562f86e`. No candidate,
population, target, gate, resampling rule, or algorithm parameter changed after
development. The confirmation population is now closed and must not be rerun,
rescored, or tuned.

## Result

Every overall and governed astronomical stratum passed availability,
signed-axis bias, and radial-p95 confidence-bound requirements.

| Overall endpoint | Estimate | 95% upper bound | Limit |
| --- | ---: | ---: | ---: |
| Availability | 1.0000 | 1.0000 | at least 1.0000 |
| Absolute mean x offset | 0.0008 beam | 0.0043 beam | at most 0.1000 beam |
| Absolute mean y offset | 0.0003 beam | 0.0041 beam | at most 0.1000 beam |
| Radial p95 | 0.2958 beam | 0.3103 beam | at most 0.5000 beam |

The overall diagnostic radial median was 0.0867 beam. Error against the former
full-observable-domain target had a diagnostic p95 of 0.3299 beam and did not
enter the decision.

The shell cohort again supplied the `above-compact-deblend-limit`,
`morphology-shell`, and `tile-corner` limiting strata. Its radial-p95 upper
bound was 0.4883 beam, leaving 0.0117 beam of margin. This independently
reproduces the narrow development result of 0.4887 beam rather than removing
that risk. The tile-boundary bound improved from 0.4626 to 0.4303 beam; every
other radial-tail bound was at most 0.3247 beam. The largest axis-bias bound
was 0.0372 beam.

| Frozen identity | SHA-256 |
| --- | --- |
| Protocol | `0fec937aeb90dec119993529af04fb5a431aeb070ab483d713abf8c91972037f` |
| Human decision | `02124201a45ecc9e88ac9542de1f6ee0fa5a5a0a43759247bc696c68170664ab` |
| Confirmation manifest | `0e0c360a95044e155b489670d50de6c0ef41ccb3b314354a56388e208d2b87c7` |
| Confirmation evidence | `6a9ca9be593d3f5c04a190869be709f698ff1582c570a55052c3ea4a7238e87a` |
| Evidence configuration | `621c6192445be3b4bf556e9c2291379313daf450f3cac82b7e861ca45c48e48e` |
| Evidence source tree | `f448a0be0a08ce6d62b35a17522ba8d93686d10e21453448070710b580a97ab2` |
| Confirmation decision | `61eff7dd2c3785a82b3048ebdfc88a3f6004f34e1b1183be2e409ceab4094b75` |

The generated evidence remains outside Git at
`benchmark-results/phase-5/astrometry-follow-up-confirmation.json`. The
checked-in decision binds its exact checksum and reviewed conclusion.

## Decision

Confirm `original-pixel-detected-segment-centroid` unchanged as Hebog's
irregular extended-source location descriptor for Step 2C-P. This decision
does not claim host astrometry, calibrated segment-position uncertainty,
scientific superiority over another finder, or production readiness. Compact
sources continue to use fitted Gaussian centres and their stricter existing
astrometry gates.

The next authorized action is to freeze the complete external-comparison
protocol before generating any Hebog, PyBDSF, or Aegean comparison output.
That protocol must preserve like-product position mappings, analytic and
injected truth as scientific authority, exact reference revisions and
environments, a fresh population, and fail-closed non-inferiority rules.
