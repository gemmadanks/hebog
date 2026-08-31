# Phase 5 terminal-feature persistence correction

**Status:** terminal cumulative failure. The exact replay completed and the
displaced-child correction did not activate on the governed population. This
result does not authorize another replay, viewed SDC1 or Hydra execution,
qualification, tuning, rescoring, optimization, cutover, or release.

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

Named approval subsequently opened exactly one cumulative replay and its
evaluation. Immutable execution checkout `ed84c216...` repeated the complete
no-write verification and produced all 2,400 candidate products before
publishing the atomic ledger. No process repair or duplicate replay occurred.

## Terminal cumulative result

The write-once ledger is
`benchmark-results/phase-5/cumulative-regression-ledger-public-finder-terminal-feature-persistence.json`,
SHA-256
`a9b4d57ec7384eb1d625b9a030126f4ca5d45f0a83150b309d14b3536eeae8a6`.
It binds candidate `3d080f7...`, source tree `a25d22d8...`, configuration
`2d6ab6bb...`, replay review `45aef047...`, execution decision `ad72924a...`,
reconstructed reference `48209eae...`, and closed baseline `a45303df...`.

Compact passes with no like-semantics regression. Continuum records 93
passes, 39 failures, 11 underpowered endpoints, no indeterminate endpoints,
and 33 like-semantics regressions. Both `all_required_endpoints_pass` and
`cumulative_science_regression_ready` are false.

The bounded terminal census makes the main result unambiguous:

| Diagnostic | Count |
| --- | ---: |
| Continuum images | 1,600 |
| Terminal-cycle candidates | 1,211 |
| Accepted terminal parents | 1,211 |
| Exactly persistent terminal features | 4,414 |
| Displaced-child candidates | 0 |
| Accepted displaced children | 0 |
| Missing or ambiguous children | 0 |
| Rejected cycles or whole-group conflicts | 0 |

The intended displaced-child seam therefore did not activate. Relative to the
preceding terminal-parent result, no endpoint state improved, three passes
became failures, one underpowered endpoint became a failure, and the
like-semantics regression count rose from 30 to 33. Overall reliability fell
from 85.21% to 77.80%, duplicate and split fractions rose from 12.83% to
15.21%, integrated-flux-error p95 rose from 26.94% to 74.62%, and
position-error p95 rose from 0.98 to 3.59 beams. Mask values are unchanged.

## Root cause and next review boundary

Code inspection isolates an eligibility guard introduced alongside the
displaced-child seam. Before persistence is evaluated, it rejects an entire
terminal cycle whenever any geometric feature lacks a direct-component
attachment. The predecessor allowed an unseeded but persistent feature to
corroborate cycle geometry while deriving catalogue membership only from
seeded direct components. The new guard can therefore discard a valid parent
without ever producing a displaced, missing, or ambiguous-child diagnostic.

The aggregate ledger proves non-activation and regression, but the transient
per-image products were removed after atomic publication and the census is
recorded after this guard. Per-realization attribution therefore still
requires a red analytic fixture. Non-executable pre-review
`phase-5-public-finder-terminal-cycle-eligibility-pre-review`, SHA-256
`e70e602f5a7a7c2a703def62ac6e5922c505feb71ae4b6f9def6dfcbf9520cd5`,
freezes that boundary. It proposes only to let an unseeded feature corroborate
cycle geometry when it independently passes the existing exact-or-displaced
persistence rule; it may never add catalogue membership. Thresholds,
measurement, gates, references, and closed evidence remain fixed, and no new
group-wide support rule is introduced.

Implementation requires named approval of that exact pre-review. Another
replay would require separately frozen replacement identities and a new exact
approval.
