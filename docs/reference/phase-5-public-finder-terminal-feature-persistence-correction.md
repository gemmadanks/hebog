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

This remains fixture evidence only. The exact non-executable replacement is
now frozen as candidate `3d080f7...`, source tree `a25d22d8...`, configuration
`2d6ab6bb...`, wrapper `0c66f221...`, evaluator `1cb62c00...`, and readiness
overlay `da135898...`, against retained reference `48209eae...` and closed
baseline `a45303df...`. The complete no-write verification passed all 2,400
inputs and 9,600 reference runs without creating scratch or output. Exact
identity review `45aef047...` records the result and canonical future
execution identity `75534703...`.

The review remains non-executable: every execution, tuning, rescoring,
qualification, cutover, and release authorization is false. A cumulative
replay requires a separate explicit approval bound to review SHA-256
`45aef047b0a8779e785995971eb60ad34384fa25aa443745ad36f2bdb6b652b9`.
