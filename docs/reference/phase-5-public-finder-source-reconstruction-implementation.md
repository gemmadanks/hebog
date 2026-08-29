# Phase 5 public-finder source reconstruction

**Status:** implemented and validated on analytic fixtures only. No cumulative
replay, public-data campaign, qualification run, tuning, rescoring, cutover,
or release is authorized by this work.

This page records the prospective correction approved by source-reconstruction
pre-review `528f18a6...`. It replaces the failed catalogue composition used by
candidate `6184a32...` while preserving its detection components, thresholds,
and all sealed evidence.

## What changed

The corrected path makes four coordinated changes:

1. direct detection components become one catalogue source only through an
   explicit common feature in the exact undilated multiscale hierarchy;
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
kernel. A direct component attaches to the finest feature it intersects and
follows only unique parent links. Components with the same unambiguous root
form one catalogue source.

The rule fails closed:

- no feature or no parent leaves a component as a singleton;
- more than one intersecting finest feature or more than one parent marks the
  component ambiguous and leaves it as a singleton; and
- proximity, a centroid chord, or a transitive chain cannot create a source
  without one explicit common feature.

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
- nearby sources without significant bridge support;
- ambiguous and unambiguous transitive chains;
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

## Governance boundary

The implementation decision is
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
the existing failed evidence.
