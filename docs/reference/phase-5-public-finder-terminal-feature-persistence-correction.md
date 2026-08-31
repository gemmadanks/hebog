# Phase 5 terminal-feature persistence correction

**Status:** implemented and fixture-validated; non-executable. This
correction does not authorize a cumulative replay, viewed SDC1 or Hydra
execution, qualification, tuning, rescoring, optimization, cutover, or
release.

## Bound evidence and decision

The terminal-parent replay provided terminal scientific evidence rather than
an operational failure. Compact passed, and the correction materially
improved Continuum reliability, flux and position tails, and split/duplicate
fractions, but 35 endpoints and 30 like-semantics comparisons still failed.
The exact result is recorded in the
[Phase 5 campaign overview](phase-5-campaign-overview.md).

Pre-review
`phase-5-public-finder-terminal-feature-persistence-pre-review`, SHA-256
`e416f7d81ac8345f2ac0ac982980e9e37299886309af2468380a7a463beafc38`,
authorized a fixture-first correction of one remaining fail-closed seam. The
red analytic fixture proved that a one-pixel boundary displacement could leave
every terminal lobe without an exact incoming edge even though:

- the terminal features formed the already-required cycle;
- every preceding and terminal exact support lay in the same retained
  significant-reconstruction component; and
- the fixed B3 envelopes provided one mutually unique child for each lobe.

## Bounded correction

The amended rule treats a terminal feature as persistent when it has either
an exact incoming edge or exactly one mutually unique preceding-scale child
whose fixed B3 envelope overlaps and whose exact support belongs to the same
retained support component. A preceding feature already used by an exact edge
cannot be reused. Displaced persistence only corroborates an existing seeded
terminal cycle; it cannot create a feature cycle, pair, path, direct-component
membership, or transitive merge.

The array-free diagnostics now distinguish exact persistent features,
displaced candidate pairs, mutually accepted displaced features, missing
children, ambiguous children, and whole-group conflicts. Future replay
composition must aggregate these counts into its terminal ledger so the next
scientific outcome can distinguish insufficient activation from ambiguity or
conflict without retaining per-image sidecars.

## Fixture evidence

Positive one-pixel displacement, disconnected support, ambiguous child,
unseeded terminal feature, nearby pair, transitive chain, invalid gap, and
partial-group conflict fixtures pass. Component labels, feature-plane order,
record order, task order, retry, Serial, and existing-Dask execution produce
identical membership and diagnostics.

This remains fixture evidence only. Exact candidate, configuration, wrapper,
evaluator, readiness, retained-reference, baseline, scratch, and output
identities must be frozen prospectively. A later cumulative replay requires a
separate exact review-bound decision.
