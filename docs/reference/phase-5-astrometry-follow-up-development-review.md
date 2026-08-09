# Phase 5 detected-segment position development review

**Status:** the frozen Step 2C-HR development population passed all 60
binding endpoints. Gemma Danks approved the reviewed scientific semantics,
gates, narrow shell risk, unavailable position uncertainty, and one-look
confirmation on 2026-08-09. This authorizes confirmation only; Step 2C-P,
Step 3, optimization, and qualification remain unauthorized.

This Codex technical review covers only the authorized 80-image development
run. It did not execute the sealed confirmation or qualification populations.
The machine-validated decision is
`config/contracts/phase-5-astrometry-follow-up-development-decision.json`.

## Evidence and result

The run evaluated 480 eligible astronomical truth groups across 80 fresh
images and 15 overall or governed astronomical strata. Every group produced a
segment centroid, and every availability, axis-bias, and radial-tail endpoint
passed its prospectively frozen one-sided rule.

| Overall endpoint | Estimate | 95% upper bound | Limit |
| --- | ---: | ---: | ---: |
| Availability | 1.0000 | 1.0000 | at least 1.0000 |
| Absolute mean x offset | 0.0027 beam | 0.0105 beam | at most 0.1000 beam |
| Absolute mean y offset | 0.0070 beam | 0.0147 beam | at most 0.1000 beam |
| Radial p95 | 0.2982 beam | 0.3183 beam | at most 0.5000 beam |

The overall diagnostic radial median was 0.0856 beam. The diagnostic p95
against the former full-observable-domain centroid was 0.3001 beam. That
former target remains non-binding because it includes flux outside the
catalogue segment.

The tightest result was the radial p95 upper bound of 0.4887 beam for the
shell source. The same shell cohort supplies the
`above-compact-deblend-limit`, `morphology-shell`, and `tile-corner` strata,
so these are three labels on one limiting condition rather than three
independent confirmations. Its remaining margin was only 0.0113 beam. The
tile-boundary upper bound was 0.4626 beam; all other radial-tail bounds were
at most 0.3554 beam. The largest axis-bias bound was 0.0652 beam.

| Frozen identity | SHA-256 |
| --- | --- |
| Protocol | `0fec937aeb90dec119993529af04fb5a431aeb070ab483d713abf8c91972037f` |
| Base residual-B3 protocol | `b7bcf5d85cef13fea7a32a4128ab7cb89f1a90bb8f4e066ab3cda618aae2220b` |
| Development manifest | `c96faa8e6bf15bd324a56a5ca37c036f5361f678d1722d6d775c8a2e929587eb` |
| Exploratory evidence | `c0a51dff38f0f7b925e5fbfaf98fabbab737ce20b22f09452826fb16ea426e23` |
| Evidence configuration | `d7429ef8309c090f5daece15eb7cfb693dc6fea26988b3c2681f731bb366acb8` |
| Evidence source tree | `91193c9df23c1a2089001fa6dacf0c8e37e5c2a22d0b73163ef34db9c11b209f` |
| Development decision | `cd6d54cf1c22daf3d68423bc931b58bb81ec192d30ec9c1472bdabcd22969c72` |
| Human confirmation decision | `02124201a45ecc9e88ac9542de1f6ee0fa5a5a0a43759247bc696c68170664ab` |

The generated evidence remains outside Git under
`benchmark-results/phase-5/astrometry-follow-up-development.json`; the
checked-in decision binds its exact checksum and compact conclusions.

## Technical interpretation

The result supports the proposed product semantics. A transparent centroid
of the original pixels in the accepted residual-B3 segment is unbiased and
repeatable enough on this fresh synthetic development population. It also
keeps a separate brightest-pixel location and makes no host-position or
calibrated position-uncertainty claim.

This pass must not be described as an improvement over the rejected
Step 2C-H candidates' astrometry numbers. The scientific target changed from
a threshold-independent full-emission centroid to the matched noiseless
three-sigma segment centroid, so their errors are not interchangeable. The
appropriate conclusion is that the new coordinate is internally consistent
with its declared catalogue meaning.

The residual risks are material:

- the limiting shell/tile-corner cohort passed narrowly and needs the sealed
  larger population rather than tuning on this result;
- the development data are synthetic and do not establish behaviour on real
  survey residuals;
- this study conditions position on an eligible detection and therefore does
  not replace the frozen completeness, reliability, grouping, and photometry
  requirements;
- support-selection uncertainty remains unavailable; and
- PyBDSF and Aegean comparability remains untested under the like-product
  mappings required by Step 2C-P.

## Decision and next review

Retain `original-pixel-detected-segment-centroid` unchanged for the authorized
single one-look confirmation. The confirmation runner must validate the human
decision and every frozen input before opening the population. No development
parameter, estimator, target, or gate may change; a change would invalidate
the approval and require a new pre-results protocol and fresh populations.
