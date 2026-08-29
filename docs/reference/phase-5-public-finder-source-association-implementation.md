# Phase 5 public-finder source-association implementation

**Status:** implemented and validated on analytic fixtures only. Exact
non-executable identity review SHA-256 `c58eec6e...` freezes the candidate.
No replay, viewed-data execution, campaign, qualification, tuning, rescoring,
cutover, or release is authorized.

The implementation is governed by pre-review SHA-256
`9af42348896e0449e007fe2318648f66122313d600137f8f5ec525ebaec1cc3c`
and implementation decision SHA-256
`6a495cfcb54ec01e5a7290b6c28edf7b7fffe89f88318c5b6f3e135e70a15553`.
It did not inspect the terminal cumulative replay, viewed SDC1 or Hydra
products, or reference-finder catalogues.

## Component and source identities

`DetectionComponentRecord` represents an immutable accepted component. Its
persistent identity is a canonical hash of the component's global row-major
owner pixel; the task-local integer label remains diagnostic only. A
`CatalogueSourceMembership` is an exact, non-overlapping partition of those
component identities. The catalogue-source identifier hashes the sorted member
identities, so worker count, task order, retry, and label permutation cannot
change it.

These records represent image-domain catalogue sources. They do not assert
that separated lobes or other components belong to one physical
astrophysical object.

## Conservative association graph

Two components receive an edge only when all frozen requirements pass:

1. exact owner pixels plus undilated significant B3 support put them in the
   same eight-connected parent support;
2. every valid pixel on the straight centroid segment remains at or above the
   existing island threshold;
3. centroid separation is no greater than half the sum of the two directional
   component FWHMs along that segment; and
4. both exact-support component covariance estimates are available.

The reducer considers edges in canonical scientific order and merges groups
only when every cross-group pair has an accepted edge. This complete-link rule
prevents a plausible A--B and B--C chain from implying an unsupported A--C
association. Missing shapes, weak saddles, invalid gaps, disconnected support,
and ambiguous evidence all leave components separate.

Overlapping association-halo tasks retain global component coordinates. Their
edge evidence is array-free, order-independent, and idempotent under exact
retry duplication. The pure reducer therefore produces the same membership
for one tile, multiple halo windows, Serial execution, and the existing Dask
executor.

## Binding source catalogue

The existing component catalogue remains available as stable diagnostic rows.
The binding source catalogue aggregates only existing exclusive component
measurements:

\[
F_s = \sum_{c\in C_s}F_c,
\qquad
P_s = \max_{c\in C_s}P_c.
\]

Source position is the integrated-flux-weighted component centroid in a local
tangent plane. Source shape is the existing moment-equivalent estimator
applied to the union of exact member-owner support. Detection labels and
component pixels are never mutated or reassigned. Background, RMS, thresholds,
minimum area, support recovery, measurement apertures, calibration, astrometry,
and component shape estimation remain unchanged.

## Fixture validation

The analytic matrix covers singleton components, continuous split broad
sources, low-saddle neighbours, high-dynamic-range fragments, directional
filaments, disconnected double lobes, complete-link bridge chains, invalid
barriers, unavailable shapes, label permutation, and malformed evidence.
Catalogue fixtures verify component-pixel preservation, exact flux summation,
maximum peak flux, tangent-plane centroid composition, and union-support shape
provenance.

Executor fixtures verify one-tile versus overlapping many-tile results across
Serial and existing-Dask execution, including partition-origin changes,
completion-order reversal, and duplicate retry evidence. The new association
modules have 90.60% focused branch-aware coverage.

Identity review
`config/contracts/phase-5-public-finder-source-association-identity-review.json`
binds implementation commit `26e639a...`, source tree `34fecf30...`,
configuration `78dbb230...`, all implementation and validation artifacts, the
failed ledger `1ac6deb2...`, reconstructed references `48209eae...`, and closed
baseline `a45303df...`. The existing replay wrapper remains bound to prior
candidate `b1d59e5...` and configuration `65c8876d...`, so it cannot execute
this candidate. A separate replay-composition pre-review, exact executable
identity freeze, and named approval are required before any cumulative replay.

## Measurement-completeness repair composition

The consumed source-association replay stopped after 58 candidate products
because an accepted positive owner could lose its catalogue measurement when
negative surrounding residuals made only the expanded aperture non-positive.
Repair commit `6184a32...` retains ordinary expanded-aperture photometry and
uses the positive exact owner only for that bounded fallback. Truly
unmeasurable owners still fail closed.

Pre-review `7687839f...` authorized a minimal replacement wrapper and a
prospective readiness update, not a replay. The wrapper checksum-binds and
loads the consumed source-association composition, then replaces only the
candidate revision/source tree, measurement-repair program, and new
write-once ledger and scratch namespaces. The scientific configuration,
compact path, reference products, compiler, evaluator, endpoints, gates, and
two-worker population remain unchanged.

The readiness contract now requires candidate `6184a32...`, source tree
`517d56e1...`, configuration `78dbb230...`, the prospective measurement-repair
cumulative ledger, and a future held-out qualification decision. These fields
were fixed before either result was opened. Clean implementation commit
`9cc00fb...` passed complete no-write verification of all 2,400 inputs and
9,600 retained reference runs. It created neither the prospective ledger nor
scratch state and did not start a replay. Non-executable review `119ce0f9...`
now freezes every prospective replay field with all later authorizations false.
A separate named one-replay approval was granted and consumed. The replay
completed all 2,400 candidate products, then stopped before the atomic ledger
because the continuum compiler still interpreted every Hebog catalogue row as
one legacy `hebog-segment-N` support. Binding associated-source rows instead
use stable `source-associated-*` identities and can own several native
component supports.

## Evaluation-only compiler adapter

The repair keeps the three semantic layers separate:

- stable component identities are recomputed only from each native support's
  canonical owner pixel;
- the persisted source digest and component count must identify exactly one
  complete partition of those components; and
- the compiler matches the binding source against the union of its verified
  native supports while retaining each native support independently for split
  and merge topology.

Malformed, mixed, incomplete, ambiguous, or unverifiable memberships fail
closed. Single-segment Hebog and both PyBDSF translations keep their prior
meaning. Every historically checksum-bound producer, matcher, and compiler
remains byte-identical. The new adapter presents a bounded synthetic union-label
view only to catalogue matching while retaining the original component-label
plane for topology. The completion program re-hashes every preserved shard and
replaces candidate execution with a verification-only seam. It cannot submit
candidate work. Clean repair commit `ea3279d...` verified all 2,400 candidate
shards as product set `dbc317fa...`, all 9,600 retained reference runs, and the
absent ledger without opening scientific products. Non-executable review
`6a0e79b4...` freezes that exact composition with compilation and evaluation
still false. A separate approval bound to that review is required before the
preserved products may be compiled and evaluated.

## Terminal evaluation result

The exact approval was recorded in decision `46ddfefa...`. Immutable revision
`2174b0c...` reverified all preserved products and references, then atomically
published ledger `6b2aa4de...` without candidate execution. The ledger is a
terminal failure: compact passes with zero regressions; Continuum has 89
passing, 44 failing, and 10 underpowered endpoints, plus 37 like-semantics
regressions.

The association layer changed 49 Continuum point estimates but no endpoint
status relative to the first corrected ledger. Overall reliability moved from
0.62563 to 0.62375 and duplicate fraction from 0.25179 to 0.25295; split
fraction stayed 0.25295. Integrated-flux and mask results were unchanged, and
the astrometric changes were numerically negligible. This is consistent with
the approved evaluation semantics: catalogue matching uses source unions, but
split and merge topology deliberately retains native components. The terminal
result therefore does not establish that source association solved the
binding fragmentation problem. It cannot be rescored or used to open held-out
qualification.
