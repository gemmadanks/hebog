# Phase 5 public-finder source reconstruction

**Status:** historical source-reconstruction campaigns remain terminal
evidence. Candidate `c28343f...` adds source-owned persistent measurement
support and a conservative one-missing-child terminal-parent rule. Its
positive, negative, invalid-pixel, boundary, and Serial/existing-Dask fixtures
pass. Public identity `ca1abba6...` and combined development-lane identity
`4c611f1b...` are frozen non-executable; the exact no-write preflight passed
all 144 candidate, 144 coarse-control, and 12 existing-Dask slots without
creating a namespace. No development-lane run, cumulative replay,
public-data campaign,
qualification run, tuning, rescoring, cutover, or release is authorized by
this work.

This page records the prospective correction approved by source-reconstruction
pre-review `528f18a6...`. It replaces the failed catalogue composition used by
candidate `6184a32...` while preserving its detection components, thresholds,
and all sealed evidence.

## What changed

The corrected path makes four coordinated changes:

1. direct detection components become one catalogue source only through an
   explicit common feature or one adjacent-scale-persistent parent derived
   from the fixed B3 filter footprint;
2. each resulting source is measured once on a unique source-owned aperture;
3. reconstructed mask support must have an eight-connected path to an
   accepted direct seed; and
4. future split and merge gates use catalogue-source unions, while native
   component topology remains a separate diagnostic.

No detection, island, background, RMS, recovery-radius, aperture-radius,
matching, gate, or non-inferiority value changed.

## Deterministic source hierarchy

Each retained significant à trous scale is converted to a bounded
`ScaleDetectionPlane`. Its labels represent exact eight-connected support;
they are not dilated for source reconstruction. A stable feature identity is
derived from the scale order and the globally canonical first support pixel.

Adjacent scales are joined with Hebog's existing exact-overlap association
kernel. A direct component attaches to every finest feature intersected by its
immutable direct-seed support and follows only unique parent links. Components
group at their finest common feature only when that feature persists to a
parent, or when every component directly attaches to that same feature.

When exact sibling features remain disconnected, parent construction now has
two explicit safeguards. First, components in the same eight-connected
component of direct support plus adjacent-scale significant reconstruction
support may corroborate a non-terminal envelope group. Connected support does
not itself form a parent because one connected island can contain multiple
astrophysical sources.

Second, the constructor makes a bounded envelope around each feature using the
cumulative radius of the already frozen B3-spline filter at that scale: 2, 6,
or 14 pixels. Envelopes are clipped to valid pixels and are used only as
hierarchy evidence; they never enter measurement. Exact adjacent-scale
persistent support may enter source-level measurement only after deterministic
ownership by an already accepted catalogue source. A sweep-line graph
identifies spatially interacting siblings. A non-terminal envelope group still
requires connected significant support. At the final retained scale, a graph
two-core with at least three members may form a parent when every terminal
feature has an exact or mutually unique bounded displaced child at the
immediately preceding scale. One directly owned terminal feature may lack a
child without vetoing the whole parent, but only when every feature remains in
one retained significant-support component and no direct component
participates in a competing terminal cycle. A missing feature with multiple
owners, disconnected support, or ambiguous displaced evidence fails closed.

The rule fails closed:

- no feature leaves a component as a singleton;
- multiple intersecting finest features require one unique common lineage;
- missing convergence or more than one parent marks the component ambiguous
  and leaves it as a singleton;
- an uncorroborated terminal bridge cannot create a source;
- a terminal pair or transitive chain remains separate, while a cycle with one
  missing child is eligible only under the exclusive whole-source rule above;
- connected significant support, proximity, a two-feature envelope, or a
  centroid chord cannot create a source without independent hierarchy
  evidence;
- invalid-pixel barriers split envelopes; and
- scales outside the frozen three-stage B3 plan cannot construct envelope
  parents.

Component labels and owner pixels are never rewritten. Catalogue-source IDs
remain a deterministic digest of the sorted immutable component IDs.

## Source-level measurement

Component moment rows remain diagnostic. Binding catalogue rows are produced
from a separate source-label plane created after hierarchy reduction. The
source seed is extended by the union of exact adjacent-scale persistent
support connected to an accepted source. Support connected to multiple
sources is assigned once to the nearest immutable member pixel, with canonical
source identity resolving exact distance ties; disconnected and invalid
support remains unowned. The unchanged 1.5-major-beam outer guard then expands
from that owned seed and applies the same deterministic ownership rule, so
distinct source apertures cannot overlap.

For source \(s\), integrated flux is measured once as

\[
F_s = \frac{1}{A_{\mathrm{beam}}}
      \sum_{p \in A_s}(I_p-B_p),
\qquad A_s \cap A_t = \varnothing \quad (s \ne t).
\]

Position and moment-equivalent shape are likewise computed once from the
source-level support. The pre-existing positive exact-owner fallback remains
explicitly flagged and now runs once per source rather than once per
component.

## Connected reconstructed support

The mask owner first labels eight-connected components in

\[
((L>0) \lor R) \land V,
\]

where \(L\) is the immutable direct-owner plane, \(R\) is significant
reconstructed support, and \(V\) is scientific validity. A reconstructed
pixel is eligible only when its connected component contains an accepted
seed and it remains inside the existing recovery radius. Invalid pixels break
connectivity. Direct seed ownership and the deterministic nearest-seed tie
rule are unchanged.

## Prospective topology evaluation

The new evaluator accepts only current in-memory truth, catalogue, and label
records. It cannot accept a campaign or ledger path and therefore cannot
rescore sealed evidence.

| Layer | Role |
| --- | --- |
| Catalogue-source support union | Binding completeness, reliability, duplicate, split, merge, flux, position, and mask metrics. |
| Native detection components | Non-binding split/merge diagnostic and ownership audit. |

The historical evaluator remains unchanged for every closed ledger.

## Fixture evidence

The fixture suite covers:

- a singleton at scale one and scale four;
- three-lobe, shell, curved-filament, boundary, and corner common parents;
- real scale-filter three-lobe, four-lobe shell, and closed curved-filament
  activation with an exact candidate/accepted/rejected telemetry census;
- nearby sources without significant bridge support;
- persistent two-feature neighbours, terminal-only candidates, and ambiguous
  and unambiguous transitive chains;
- connected persistent-support pairs and curved paths that remain separate,
  terminal cycles with persistent constituents, and uncorroborated terminal
  cycles;
- crowded seeds, invalid gaps, label permutations, bounded tile origins, and
  different plane orders;
- exact source flux and centroid, disjoint apertures, boundary/corner
  equality, and one source-level fallback;
- mixed core/halo source-owned photometry at 4, 8, and 12 beam extents under
  flat and varying backgrounds;
- connected wings, disconnected nearby support, direct-seed preservation,
  invalid-pixel barriers, image-edge support, and deterministic competing-
  source ownership;
- exact, displaced, missing, multiply owned, disconnected, partial-group,
  branched, and competing terminal-parent cases; and
- binding catalogue-source topology alongside native-component diagnostics.

The same source memberships and support owners are tested through the serial
and existing-Dask executors, including reversed task order and a duplicate
retry.

## Post-campaign activation review

Terminal cumulative ledger `84fbb3a1...` showed that the first candidate did
not materially change membership: all endpoint states and the overall 25.29%
split and duplicate fractions were unchanged. Review `c1a92bd2...` traced one
real composition defect: support expansion replaced the direct-seed owner
plane before hierarchy attachment. The approved repair now retains both
planes, measures on recovered ownership, associates on direct ownership, and
records an array-free activation census.

That repair exposed a separate source-parent construction defect. An 81 by 81
analytic four-lobe shell was sent through the real corrective-A scale filter,
support assignment, hierarchy, and product composition. It produced four
direct components and four exact features at each of scales 1, 2, and 3. Exact
adjacent-scale overlap produced four persistent lineages, not one shared
parent, so the correct fail-closed result remained four singleton catalogue
sources. The earlier positive tests manually supplied a connected coarse
parent; they validated hierarchy reduction but not construction of that parent
from real scale products.

Non-executable parent-construction pre-review `b5d89bdc...` records the full
cause and proposes a fixture-first, scale-aware parent construction derived
from the existing B3-spline filter footprint. Exact feature support remains
the measurement evidence; any prospective support envelope may provide parent
evidence only, must persist across adjacent scales, and must fail the nearby
source, terminal-bridge, crowded-field, invalid-gap, and transitive-chain
negative controls. No fitted threshold or campaign-derived radius is allowed.
Gemma Danks approved that exact review. Implementation decision
`config/contracts/phase-5-public-finder-source-hierarchy-parent-construction-implementation-decision.json`
opens only fixture-bound implementation, validation, and non-executable
identity freezing. The implementation now passes the required positive and
overmerge controls, emits parent-candidate, accepted-parent, and rejected
candidate counts, and is invariant under label, plane, task, retry, Serial,
and existing-Dask ordering. Any eventual replay still requires a later exact
approval.

The terminal replay later proved that the adjacent-group recurrence rule was
still impossible for this population: all 1,923 constructed parent candidates
first appeared at scale 3 and none could recur at scale 4. Every one of 18,065
components therefore remained a singleton. The prospective correction is
documented in the
[persistent-support parent correction](phase-5-public-finder-persistent-support-parent-correction.md).
It makes significant reconstruction support explicit as corroboration rather
than source membership, and replaces terminal group recurrence with
constituent-feature persistence plus a cycle requirement. The real three-lobe
terminal fixture now activates, while connected-support-only islands, invalid
support, unseeded support, ambiguous owners, partial exact-group overlap,
pairs, chains, and terminal features without adjacent children fail closed.
This is fixture evidence only; no replay or viewed-data execution is
authorized.

The terminal-parent cumulative replay then showed that exact constituent
persistence was scientifically useful but incomplete: Continuum improved from
89 to 96 passing endpoints and from 37 to 30 regressions, yet 35 endpoints
still failed. Approved pre-review `e416f7d8...` required a red analytic
boundary-drift fixture before another correction. That fixture reproduced the
remaining exact-overlap gap. The bounded amendment now accepts one mutually
unique displaced preceding-scale child only when fixed B3 envelopes overlap
and both exact supports lie in the same retained significant-reconstruction
component. It cannot create a cycle or membership, and it rejects disconnected
support, ambiguity, unseeded terminal features, pairs, paths, invalid gaps, and
partial-group conflicts. Exact/displaced/missing/ambiguous/conflict telemetry
is retained for prospective ledger aggregation. This implementation remains
non-executable pending exact identity freezing and a later review-bound replay
decision.

## Governance boundary

The original implementation decision is
`config/contracts/phase-5-public-finder-source-reconstruction-implementation-decision.json`.
The prospective replay wrapper now consumes the exact previous replay
composition, replaces only the Continuum candidate and catalogue-source
topology seams, and prospectively rebinds readiness. The next permitted
activity is to freeze its clean revision together with the candidate, source
tree, configuration, evaluator, reconstructed reference, and closed baseline,
then run the complete verifier in no-write mode. The output must remain
non-executable. That step is complete in identity review `b4eff062...`: all
2,400 inputs and 9,600 retained reference runs verified, the future output and
scratch namespaces were absent, and no replay started.

Execution decision `0d87caf7...` records the separate named approval of that
exact frozen composition and authorizes one cumulative replay only. Its result
must be summarized in the
[Phase 5 campaign overview](phase-5-campaign-overview.md) without replacing
the existing failed evidence. That authority is consumed and its terminal
ledger failed. Root-cause repair decision `8296c4ce...` authorized only the
prerequisite label/activation work. Parent-construction review `b5d89bdc...`
permitted the validated replacement candidate and replay composition to be
prepared. The new wrapper consumes the exact failed source-reconstruction
wrapper, replaces only its candidate identity and current Continuum builder,
requires output and scratch to be absent during verification, and fails closed
unless a separate future decision binds its eventual identity-review digest.
Identity review `e615da00...` now binds wrapper revision `af7040e...`, candidate
`5f2b098...`, source tree `a7ef1887...`, configuration `88634678...`, retained
reference terminal `48209eae...`, and closed baseline `a45303df...`. It does
not authorize executing the replay; that requires a separate named approval
bound to the complete review digest.

Gemma Danks subsequently approved exactly one two-worker cumulative replay
bound to review `e615da00...`. Execution decision `78c274cc...` binds the
800-compact/1,600-Continuum population and every candidate, wrapper, retained
reference, closed-baseline, output, and scratch identity. It authorizes only
that replay. Viewed-data and campaign execution, qualification, tuning,
rescoring, optimization, cutover, and release remain false.

The first authorized process did not reach candidate execution. An initial
immutable-checkout evidence-visibility error was corrected without changing
any identity. The resumed process then completed retained-reference
verification but failed while resolving executable composition: the
parent-construction wrapper descended through source reconstruction once,
received the measurement-repair overlay, and incorrectly treated it as the
source-association wrapper. It therefore requested `_load_current_wrapper`
from the wrong layer. No scratch directory, candidate product, partial science,
or ledger was created.

The approved repair is orchestration-only. It resolves the exact chain
explicitly—source reconstruction, measurement repair, source association, then
the frozen replay—and reuses that resolver in both the parent process and
spawned workers. Complete no-write verification now resolves and installs the
same executable seams, closing the test gap that allowed identity/reference
verification to pass without exercising authorized delegation. Candidate
`5f2b098...`, configuration `88634678...`, references, gates, population,
workers, scratch, and output remain unchanged.

Replacement repair review `89327ae5...` binds boundary commit `9d15fd0...`,
wrapper `053fc647...`, and canonical execution identity `7a9c19d3...`. Its
complete no-write verification passed all 2,400 inputs and 9,600 retained
reference runs, installed the executable delegation seams, and confirmed the
original output and scratch remained absent. Repair execution decision
`0349fdc2...` consumes Gemma Danks's explicit “fix the error and restart the
run” instruction for that one unchanged replay only. Every later action
remains unauthorized.
