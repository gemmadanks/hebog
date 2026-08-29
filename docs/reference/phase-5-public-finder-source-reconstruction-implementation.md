# Phase 5 public-finder source reconstruction

**Status:** the first source-reconstruction candidate is terminal failed
evidence. The separately approved parent-construction repair is implemented
and passes its synthetic real-scale, overmerge-safety, and executor fixtures.
Exact replacement identities are not yet frozen. No cumulative replay,
public-data campaign, qualification run, tuning, rescoring, cutover, or release
is authorized by this work.

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

When exact sibling features remain disconnected, the parent constructor makes
a bounded envelope around each feature using the cumulative radius of the
already frozen B3-spline filter at that scale: 2, 6, or 14 pixels. Envelopes
are clipped to valid pixels and are used only as hierarchy evidence; exact
feature support remains the sole measurement support. A sweep-line overlap
graph identifies spatially interacting siblings. Only a connected graph
two-core is eligible, so a pair or transitive chain cannot manufacture a
parent. The identical set of immutable direct components must recur as a
candidate at adjacent scales. A shared exact feature at one of those scales
may corroborate the envelope candidate at the other.

The rule fails closed:

- no feature leaves a component as a singleton;
- multiple intersecting finest features require one unique common lineage;
- missing convergence or more than one parent marks the component ambiguous
  and leaves it as a singleton;
- a shared feature appearing only as a terminal coarse bridge cannot group
  otherwise independent components; and
- proximity, a two-feature envelope, a centroid chord, or a transitive chain
  cannot create a source;
- invalid-pixel barriers split envelopes; and
- scales outside the frozen three-stage B3 plan cannot construct envelope
  parents.

Component labels and owner pixels are never rewritten. Catalogue-source IDs
remain a deterministic digest of the sorted immutable component IDs.

## Source-level measurement

Component moment rows remain diagnostic. Binding catalogue rows are produced
from a separate source-label plane created after hierarchy reduction. The
existing nearest-owner aperture expansion then partitions eligible pixels
between sources, so distinct source apertures cannot overlap.

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
- crowded seeds, invalid gaps, label permutations, bounded tile origins, and
  different plane orders;
- exact source flux and centroid, disjoint apertures, boundary/corner
  equality, and one source-level fallback;
- connected wings, disconnected nearby support, direct-seed preservation,
  and invalid-pixel barriers; and
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
now permits freezing a replacement candidate and replay composition after
validation, but it does not authorize executing that replay.
