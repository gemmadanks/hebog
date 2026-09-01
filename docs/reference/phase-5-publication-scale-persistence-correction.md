# Phase 5 publication-scale persistence correction

## Decision summary

The 128-case persistent-feature-influence smoke closed all remaining
duplicate and split-source failures. One binding comparison remained: overall
Continuum mask precision was `0.05231` worse than pinned PyBDSF `master`
against a frozen `0.05` practical non-inferiority margin.

This is a publication-mask problem, not a source-association problem. The
catalogue, component measurements, source grouping, scientific thresholds,
comparators, and acceptance margins remain unchanged.

## Corrected root cause

The prior working hypothesis was that publication refinement started from an
expanded measurement plane rather than direct original-image detections. The
activated smoke falsified that explanation:

- direct and measurement component-label planes are identical on all 64
  Continuum smoke inputs;
- all 64 published segment masks are byte-identical to the preceding
  publication-S/N candidate;
- every published boundary pixel already satisfies the existing 3-sigma
  original-image island floor; and
- the new source-association sidecars changed and closed all six topology
  failures, proving that the intended candidate was active.

Pixel attribution localizes the remaining precision loss:

| Publication branch | True pixels | False pixels | Precision |
| --- | ---: | ---: | ---: |
| Dense opened core | 146,496 | 12,620 | 0.92069 |
| Original-image boundary at or above 6 sigma | 111 | 0 | 1.00000 |
| Other recovered support | 1,103 | 906 | 0.54903 |

The poor branch consists primarily of sparse boundary support seen in only one
wavelet scale. Adjacent-scale recurrence is independent evidence that a feature
is astronomical structure rather than a scale-local fluctuation.

## Prospective rule

The candidate applies the following deterministic rule:

1. Keep the existing dense opened core.
2. Keep original-image boundary pixels at the existing 6-sigma rule.
3. Keep or restore an owned pixel when its exact scale feature participates in
   an adjacent-scale association.
4. Remove a previously published one-scale region unless that complete region
   is needed to connect two retained parts of the same immutable owner.
5. Drop a detached newly restored scale fragment rather than publishing one
   disconnected detection component.

The rule introduces no numerical threshold, radius, fitted parameter, or
truth-assisted selection. It uses the exact adjacent-scale association graph
that Hebog already constructs, and every output pixel retains its existing
measurement owner.

## Reduced-data evidence

A read-only in-memory diagnostic used the already viewed 64 Continuum smoke
inputs. It did not publish a product or rescore a closed result. The new fresh
smoke remains authoritative.

| Metric | Current mean | Prospective mean | Change |
| --- | ---: | ---: | ---: |
| Mask precision | 0.91269 | 0.91567 | +0.00298 |
| Mask recall | 0.90315 | 0.90465 | +0.00150 |
| Mask IoU | 0.83134 | 0.83507 | +0.00372 |

The simple strict-persistence mask had better precision but fragmented 56
owners. Restoring every owner wholesale preserved topology but recovered too
much noisy boundary. The selected owner-bridge rule improves all three mean
mask metrics and preserves connected ownership. Detached restorations are
removed by the production implementation.

## Trade-off policy

Phase 5 still requires every applicable metric to match or outperform both
PyBDSF references under its frozen practical non-inferiority margin. Absolute
scientific targets remain visible longer-term goals, while validity and
Rapthor-facing requirements remain binding.

A small movement relative to the frozen Hebog incumbent may be acceptable only
when it stays inside the endpoint's predeclared practical margin, every
applicable absolute and PyBDSF acceptance gate passes, a scientifically related
metric improves substantially, and the trade-off is reported. Results cannot
be used to change a threshold, margin, comparator, confidence rule, or gate.

For this correction, the reduced-data diagnostic predicts a Pareto improvement
rather than a trade-off: precision, recall, and IoU all improve. The frozen
128-case smoke and then the cumulative replay determine whether that prediction
generalizes.

## Required evidence before the cumulative replay

- analytic tests for one-scale rejection, adjacent-scale restoration,
  connected owner bridges, detached support, malformed evidence, and
  non-contiguous owner labels;
- exact feature-support and scale-order invariance tests;
- Serial and existing-Dask product invariance plus compact byte identity;
- an actual-final-writer activation test through the nested `runpy` overlays;
- complete no-write verification of all current and incumbent smoke inputs;
- one fresh atomic 128-case smoke with zero confirmed failures; and
- exact immutable candidate, source-tree, configuration, producer, compiler,
  evaluator, reference, baseline, and output identities before the one full
  replay.

The machine-readable pre-review is
`config/contracts/phase-5-prospective-publication-scale-persistence-pre-review.json`.
