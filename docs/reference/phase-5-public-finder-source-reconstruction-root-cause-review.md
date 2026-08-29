# Phase 5 source-reconstruction root-cause review

**Status:** ready for named approval of a fixture-only hierarchy-activation
repair. This review is non-executable. It does not authorize implementation,
a replay, viewed SDC1 or Hydra execution, fresh qualification, tuning,
rescoring, optimization, cutover, or release.

## Conclusion

The source-reconstruction candidate failed because its new hierarchy was
given the wrong semantic label plane when catalogue components were attached
to multiscale features.

The pipeline correctly created immutable labels for direct residual-detection
seeds. It then expanded those labels over connected reconstructed support for
mask ownership and measurement. Only the expanded plane was retained. The
hierarchy therefore attached a recovered aperture—not the original direct
seed—to the finest wavelet features.

An expanded owner can cross more than one fine-scale feature. The hierarchy
currently treats that situation as immediately ambiguous and forces the owner
to remain a singleton. It never asks whether all the intersected fine features
converge on one unambiguous coarse parent. The intended common-parent grouping
therefore remained effectively dormant in the governed population.

This primary defect is **confirmed by code trace and controlled analytic
reproduction**. The exact campaign-wide activation rate cannot be recovered
because no hierarchy telemetry was written and the verified raw candidate
shards were removed after terminal compilation.

The machine-readable review is
`config/contracts/phase-5-public-finder-source-reconstruction-root-cause-pre-review.json`,
SHA-256
`c1a92bd2d03455046db60c6e5b704eb3f7097b4c094d96386f69ae90cdec3993`.

## Bound evidence

The review binds terminal ledger
`benchmark-results/phase-5/cumulative-regression-ledger-public-finder-source-reconstruction.json`,
SHA-256
`84fbb3a18828210543d815d28aa4eab039a2ad7467aa2572a9c5119780f55a0e`,
and predecessor
`benchmark-results/phase-5/cumulative-regression-ledger-public-finder-source-association-measurement-repair.json`,
SHA-256
`6b2aa4deb306e0d7ba8285aae1e18bfb4f4e838b57aecd0497bec990e8a8c842`.

The terminal candidate is:

- revision `42c75f44b71800ae5fa1e0ebe1669caa7da59f85`;
- source tree
  `1b67c7f6f768d6f83becc853a1ebd45b3996164cd2b87fdc0f71b9a3299e6bf1`;
- configuration
  `470e918db1a640d7393edc02de01fc57b50881b908bd6d5dac18a57709117bbb`;
  and
- verified product set
  `0d8c2d0bb783aa812c520667ca71a557bae08d3a4a234ba70d7589c1285aa3c7`.

Compact science passed. Continuum remained at 89 passing, 44 failing, and 10
underpowered endpoints, with 37 like-semantics regressions.
`cumulative_science_regression_ready` is false.

## Why the result indicates dormant behaviour

Compared with the immediately preceding terminal ledger:

| Observation | Result |
| --- | ---: |
| Endpoint status transitions | 0 of 143 |
| Changed point estimates | 48 of 143 |
| Largest absolute point change | \(6.51\times10^{-7}\) |
| Overall duplicate fraction | 0.2529464286, unchanged |
| Overall split fraction | 0.2529464286, unchanged |
| Overall reliability | 0.6237540793, unchanged |
| Compact regressions | 0 |

Source-level measurement and source-union topology can improve the binding
metrics only when more than one native component is assigned to a catalogue
source. The exact topology invariance, unchanged reliability, unchanged flux
metrics, and only floating-point-scale position changes show that meaningful
grouping did not activate. This is not a near miss at a scientific threshold.

## Reconstructed execution path

The failure is reachable through the normal candidate composition:

1. `evaluate_public_finder_correction_candidate_products()` creates
   `direct_detection.component_labels` from direct residual detections.
2. `assign_seeded_multiscale_support()` expands and assigns significant
   reconstructed support to those seed owners.
3. `PostCampaignCandidateProducts` retains only that expanded plane as
   `detection.component_labels`; the direct seed plane is discarded.
4. `build_public_finder_source_reconstruction_continuum_products()` passes
   `products.detection.component_labels` to
   `build_hebog_reconstructed_source_catalogues()`.
5. `_attached_finest_feature()` examines every pixel owned by a component. If
   the expanded owner intersects more than one feature on the first applicable
   scale, it returns ambiguity immediately.
6. `associate_components_by_multiscale_hierarchy()` converts every ambiguous
   component into a singleton without considering whether those features have
   one common parent.

This violates the semantic promise in the hierarchy's own docstring: it says
that *direct component labels* are immutable, but the caller supplies labels
after recovery and measurement ownership have expanded them.

## Controlled analytic reproduction

The review used synthetic arrays only—no governed candidate products, viewed
public data, truth catalogue, or reference-finder catalogue.

The fixture contains two direct owners. The first owner's recovered support
crosses two fine-scale features. The second owner touches a third fine-scale
feature. All three fine features have the same single coarse parent.

| Attachment labels | Ambiguous owners | Membership sizes |
| --- | ---: | --- |
| Expanded measurement ownership | 1 | 1, 1 |
| Original direct-seed ownership | 0 | 2 |
| Expected under the unique common parent | 0 | 2 |

This demonstrates both parts of the activation defect:

- support-expanded ownership is not a stable hierarchy-attachment identity;
  and
- multiple finest-feature intersections are rejected before unique
  convergence can be evaluated.

## Why existing tests passed

The hierarchy unit and integration fixtures use idealized, manually built
scale planes and one-pixel owners. Each owner intersects exactly one finest
feature before the common coarse parent is considered. They exercise the
successful branch but cannot reach the expanded-owner ambiguity branch.

The candidate-composition test mocks both candidate-product construction and
source-catalogue construction. It verifies argument forwarding, but not that
the forwarded label plane has direct-seed semantics.

No current fixture runs an analytic shell, curved filament, or multi-lobe
source through the complete real path:

```text
scale filtering
  -> direct detection
  -> seeded support ownership
  -> hierarchy attachment
  -> source measurement
  -> prospective topology evaluation
```

That missing composition test is the acceptance gap that allowed the defect.

## Causes excluded or downgraded

### Evaluator membership recovery is not the primary cause

The writer stores source membership in the source identifier digest and
component count. The prospective evaluator verifies that digest against the
native label plane and constructs exact union support for catalogue matching.
If the hierarchy had grouped components, the binding topology metrics would
have observed the group.

### Disconnected support was not material here

Connected-support admission changed mask precision by only
\(1.79\times10^{-7}\), recall by \(-6.51\times10^{-7}\), and IoU by
\(3.41\times10^{-7}\), with no gate transition. The earlier hypothesis that
disconnected nearby support materially caused mask imprecision is therefore
refuted for this governed population.

The remaining precision deficit concerns connected retained support. It is a
separate prospective workstream and must be reproduced analytically before any
mask change. It does not justify changing thresholds or the recovery radius.

### Exact-overlap scale shift is plausible, not established

A physical feature can shift between wavelet scales and fail exact
adjacent-scale overlap. That remains a plausible secondary activation problem,
but it has not yet been reproduced. It must not be used to justify dilation or
a new tolerance without a red analytic fixture.

### Terminal-root grouping is a safety risk

Grouping all lineages that reach one very coarse terminal root could merge
nearby independent sources. The terminal candidate reported zero merge
fraction, but that evidence is not reassuring when hierarchy activation was
dormant. A real coarse bridge and a crowded many-seed field are mandatory
negative controls for the repair.

Runtime, statistical power, threshold selection, and an operational failure
are also excluded as explanations for the unchanged source topology.

## Recommended bounded repair

The smallest coherent repair has three parts.

1. Preserve two explicit label planes:

   - `direct_component_labels` for component identity and hierarchy
     attachment; and
   - `measurement_component_labels` for connected recovered-support ownership,
     masks, and measurement.

2. Attach each direct owner to its complete set of finest intersected features.
   Accept a source grouping only when their lineages yield one unique nearest
   common convergence feature. No convergence or multiple convergence
   candidates must fail closed as flagged singletons.
3. Emit compact serializable activation telemetry: component and source
   counts, membership-size histogram, unattached and ambiguous counts by
   reason, unique convergence count, per-scale feature counts, and
   adjacent-scale edge counts.

The repair must not change source measurement or evaluation semantics unless a
focused fixture independently proves a defect after membership activates. It
introduces no threshold, gate, recovery-radius, beam, WCS, background, RMS, or
photometric change.

## Test-first acceptance boundary

Before production implementation, a red fixture must reproduce the exact
expanded-owner failure. The suite must then cover:

- one or several finest features with one unique nearest convergence;
- no convergence and multiple/branched convergence, which remain singletons;
- analytic shell, curved-filament, and multi-lobe examples through the full
  real candidate and evaluator composition;
- a real coarse bridge, crowded many-seed field, masked gap, and invalid
  pixels, which must not overmerge;
- a scale-shift example to determine whether exact overlap is actually a
  second defect before changing that rule; and
- Serial/existing-Dask, tile, worker-count, order, retry, and telemetry
  reduction invariance.

Only fixtures and synthetic analytic evidence may be used. Terminal candidate
shards, viewed SDC1/Hydra products, and PyBDSF/Aegean catalogues are forbidden
inputs.

## Approval boundary

Named approval of this exact review may authorize only test-first
implementation, fixture-only validation, compact activation telemetry,
executor invariance, and freezing non-executable candidate/replay identities.

Any cumulative replay requires a later, separate approval bound to the exact
candidate, source tree, configuration, programs, reconstructed references,
closed baseline, and complete no-write verification. Viewed public execution,
fresh qualification, tuning, rescoring, cutover, and release remain
unauthorized.
