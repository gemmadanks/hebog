# Phase 5 persistent-support parent correction

**Status:** implemented and fixture-validated; non-executable. This
correction does not authorize a cumulative replay, viewed SDC1 or Hydra
execution, qualification, tuning, rescoring, optimization, cutover, or
release.

## Decision

Replace the impossible terminal-persistence rule with two explicit,
complementary safeguards around parent evidence.

The first safeguard is connected, adjacent-scale significant emission. Two or
more immutable direct components may corroborate an independently constructed
non-terminal parent only when they occupy the same eight-connected component
of

\[
P = (D \lor R) \land V,
\]

where \(D\) is direct component support, \(R\) is the significant atrous
reconstruction support, and \(V\) is scientific validity. Connected support
does not itself define a catalogue source: one connected island can contain
several astrophysical sources. It therefore cannot admit a pair, chain, or
path without separate hierarchy evidence. The reconstruction support is
already formed only from detections present at adjacent retained scales, so
this safeguard requires no new threshold, radius, or scale.

The second path handles emission whose common parent first becomes resolvable
at the final retained scale. It admits only a cycle-supported terminal feature
group with at least three members, and only when every terminal feature has an
exact overlapping child at the immediately preceding scale. Persistence is
therefore proved for every constituent feature; only recurrence of the newly
resolved group is waived. A terminal pair, chain, feature without an incoming
adjacent-scale edge, or group with conflicting ownership remains separate.

Exact multiscale hierarchy groups remain valid. A terminal-cycle parent may
merge existing groups only when it contains each intersected group completely.
A partial overlap is a conflict and fails closed. Connected support by itself,
pure proximity, overlapping filter-footprint dilation, invalid pixels, and
unseeded support cannot create membership.

## Bound failure evidence

The correction follows terminal ledger
`cumulative-regression-ledger-public-finder-source-hierarchy-parent-construction.json`,
SHA-256
`2ece9928eec152cf17f06e9e869d0db9c6a8f0acc2b18ea482aced5e133e6bce`.
Its candidate was `5f2b09880dc10feb6ffaec50ffcf3c807a093416`, with
source tree
`a7ef1887bcaeb15abf48722d45de33f81d8be65d58fde19861bf0ece90b4dba8`
and configuration
`88634678d7b24c9d9d47a5ba714c66fcc627c8a201b9639b133e326cd1c72484`.

Compact science passed. Continuum produced 89 passing, 44 failing, and 10
underpowered endpoints, including 37 like-semantics regressions. Every one of
the 143 Continuum values, statuses, and reasons was unchanged from the
preceding source-reconstruction ledger.

The 1,600 retained Continuum association sidecars explain the lack of effect:

| Activation evidence | Count |
| --- | ---: |
| Direct components | 18,065 |
| Catalogue sources | 18,065 |
| Multi-component memberships | 0 |
| Images with a constructed-parent candidate | 1,565 |
| Candidate occurrences | 1,923 |
| Candidates first present at scale 3 | 1,923 |
| Candidates accepted at adjacent scales | 0 |
| Components with no common exact convergence | 4,021 |

All constructed candidates first appeared at the last retained scale. The old
rule required the identical component set to recur at the next scale, which
does not exist, so it rejected every candidate.

## Root cause

The previous parent constructor inferred possible continuity by dilating each
scale feature through every valid pixel within the fixed B3 footprint. It then
accepted only cycle-supported groups whose identical component set recurred at
an adjacent scale.

That composition has two independent defects:

1. **Impossible terminal persistence.** The governed population created all
   parent candidates at scale 3, but the rule demanded recurrence at scale 4.
2. **Geometry was mistaken for emission.** Dilation was masked by validity,
   not by significant signal. Relaxing the terminal rule would therefore have
   allowed unrelated nearby sources to merge through valid background.

The two-core requirement also excluded genuine two-lobe sources and curved or
linear multi-component emission because a pair or path need not contain a
graph cycle.

The candidate already computes both safeguards: significant atrous
reconstruction retains connected pixels supported by adjacent scale pairs,
while exact adjacent-scale feature edges prove constituent persistence. The
wide three-lobe fixture also disproved the initial hypothesis that connected
support could be used as source membership: it contains three disconnected
significant-support components. More importantly, even a connected island is
not necessarily one source. The implementation therefore uses support only to
corroborate non-terminal geometry, while the narrowly bounded terminal-cycle
exception addresses the observed impossible-scale failure.

## Implementation boundary

The implementation must:

- make significant multiscale support an explicit required input to source
  reconstruction;
- validate its shape, boolean type, and containment within valid pixels;
- derive deterministic eight-connected support corroboration groups from
  direct support and significant reconstruction support;
- never turn connected support alone into catalogue-source membership;
- admit a terminal cycle only when every constituent terminal feature has an
  exact child at the immediately preceding scale;
- preserve direct component labels, measurement ownership, source-level
  measurement, thresholds, gates, and all photometric definitions;
- reject a terminal-cycle parent that partially overlaps an already
  established exact source group;
- retain compact array-free telemetry for candidates, accepted parents, and
  conflicts; and
- remain invariant to component labels, input ordering, Serial/existing-Dask
  execution, completion order, and retry.

The envelope graph cannot authorize a non-terminal group unless the same
component group is contained in connected significant support. At the terminal
scale it may authorize only the constituent-persistent cycle described above.
Validity-masked dilation, terminal pairs, and transitive chains remain
insufficient.

## Test-first acceptance matrix

The correction is accepted only if tests cover all of the following.

| Class | Required evidence |
| --- | --- |
| Activation | A wide terminal shell joins through a cycle whose constituent features persist from the preceding scale. |
| Overmerge safety | A connected-support pair or path remains separate without independent hierarchy evidence; nearby pairs and chains remain separate; a terminal cycle with any non-persistent constituent remains separate. |
| Validity | An invalid-pixel gap splits support; significant support on an invalid pixel is rejected. |
| Ownership | Unseeded support is ignored; every direct component remains in exactly one catalogue source. |
| Conflict safety | Partial overlap with an exact hierarchy group is rejected rather than splitting or transitively merging it. |
| Determinism | Component-label permutation, plane order, record order, task order, retry, Serial, and existing-Dask execution produce identical memberships and telemetry. |
| Composition | The real candidate path forwards the exact reconstruction support and activates the formerly terminal-only analytic morphology. |
| Failure behaviour | Missing, non-boolean, misaligned, or invalid support fails before catalogue measurement. |

Passing fixtures show that the implementation matches this prospective
contract. They do not establish governed scientific improvement. Any future
cumulative replay must be separately frozen, fully preflighted, and explicitly
approved.

## Residual scientific risk

The terminal-cycle exception is deliberately narrower than the failed rule,
but it is not proof that all cycle members are one astrophysical source. A
crowded arrangement of three or more individually persistent nearby sources
could form the same envelope topology. Positive analytic morphology fixtures,
crowded-field negative controls, exact ownership checks, and the unchanged
scientific gates reduce that risk; they cannot eliminate it. A future governed
cumulative replay must therefore treat split and duplicate-source endpoints as
binding overmerge checks. Failure is terminal evidence and must not trigger
threshold tuning or a rerun.
