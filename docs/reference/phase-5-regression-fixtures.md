# Phase 5 regression fixtures

## Purpose

Phase 5 qualification must not depend on remembering why an earlier candidate
failed. The machine-readable
[`phase-5-regression-fixtures.json`](https://github.com/gemmadanks/hebog/blob/main/config/contracts/phase-5-regression-fixtures.json)
maps every accepted development defect to its root cause, the invariant that
must now hold, the revision that accepted the correction, and one or more
deterministic pytest fixtures.

The registry is itself checked by
`tests/unit/validation/test_phase_five_regression_fixtures.py`. The check fails
if a defect disappears, an identifier is duplicated, a fixture file is
missing, or a named pytest function no longer exists. The registered tests are
also run directly as a focused lane before qualification.

This is traceability evidence, not qualification evidence. It neither reopens
closed campaigns nor substitutes viewed development cases for untouched data.

## Covered defect families

| Family | Accepted defects | Permanent invariant |
| --- | ---: | --- |
| Numerical science | 8 | Mask and edge normalization, original-pixel photometry, reviewed aperture, residual-B3 refinement and position weighting, component bias, and irregular-source locations remain explicit and tested. |
| Product semantics | 3 | Fitless detections survive, source and Gaussian-component records remain distinct, and valid independent component ellipses are retained. |
| Campaign composition | 3 | The exact candidate composition, fitted-component compiler semantics, and symmetric valid domain fail closed on drift. |
| Runtime provenance | 3 | The frozen source path, reconstructed runtime, and both evaluator accelerator identities remain bound without changing scientific products. |

The 17 entries deliberately describe root causes rather than every failed
endpoint. Several endpoints can share one defect, while one invariant can need
multiple analytic fixtures to cover its normal, boundary, and failure paths.

## Qualification use

Before the final one-look qualification opens:

1. the registry integrity test and every named fixture must pass;
2. the full Phase 4 compact regression must remain green;
3. the untouched Phase 5 population must use the same candidate composition
   and evaluator semantics recorded by the registry; and
4. a terminal failure remains terminal. The registry may diagnose a later
   failure but cannot authorize rescoring or tuning from qualification data.

