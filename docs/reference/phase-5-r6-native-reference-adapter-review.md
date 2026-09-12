# R6 native-reference adapter review

Review date: 2026-09-08. Terminal follow-up: 2026-09-09.

**Current state:** the separately frozen evaluation-only continuation has
completed. Its process exited zero, but cumulative terminal `7146f2e8...`
failed scientifically (885 passing, 288 failing and 14 underpowered binding
comparisons; all five safety checks pass). See the
[terminal snapshot](https://github.com/gemmadanks/hebog/blob/0ce253cf26a7954a58dc9a211eb01d8502e69025/docs/reference/phase-5-campaign-overview.md#2026-09-09-r6-cumulative-terminal-scientific-failure).
The adapter failure below is historical, not a live retry instruction.

This is a later process review, separate from the
[original source-finding audit](phase-5-source-catalogue-science-audit.md).
R6 completed its captures and Dask comparisons but stopped while
converting a retained PyBDSF catalogue into the validation-only source union.
At the time of this review no terminal science decision existed, and no
metrics were changed or rescored for the review.

## Gaussian identifiers: repaired, not executed

The adapter used `(Isl_id, Source_id, Gaus_id)` as a unique key. Retained
wavelet products reuse Gaussian numbers across `Wave_id`; 153 of the 3,200
Continuum catalogues contain such collisions. One pinned-master catalogue
also repeats `(2, 2, 16, 2)` with different native positions, fluxes and
shapes. These are distinct model rows, not byte-identical duplicates.
[PyBDSF's catalogue documentation](https://pybdsf.readthedocs.io/en/stable/write_catalog.html)
defines separate island, source, Gaussian and wave identifiers; the retained
export demonstrates why Gaussian numbering alone cannot identify its rows.

The adapter-only correction includes the wave and, for a repeated full key,
an exact native-model fingerprint. It neither changes nor drops a Gaussian,
alters native `srl` positions/fluxes, or changes its source membership.
Indistinguishable duplicate models still fail; differing error bars alone
cannot justify duplicate rows. Existing lexical model-summation order is
preserved wherever the shorter keys were unique. Synthetic cross-wave,
same-wave, reversed-order and byte-order cases cover the boundary.

All 16 PyBDSF reference views behind the eight completed Continuum inputs
retain exactly equal source observables, diagnostic catalogue rows, source
union arrays and publication masks. This is projection-equivalence evidence,
not another evaluation against truth. Historical programs and records remain
byte-identical, and the repaired adapter has not been used for a retry.

## Empty exclusive ownership: approved amendment

With the ID repair in place, a full read-only projection audit succeeds for
3,150 reference catalogues and rejects 50 across 28 inputs with
`PyBDSF source owns no native pixels`: 23 released and 27 pinned-master.
These are adapter failures, not failed scientific endpoints. No other
exception class appeared in this bounded adapter audit; this is not proof
that every downstream evaluation path is bug-free.

A synthetic reproduction uses two valid native sources with the same centre
and Gaussian shape but unequal amplitudes. The stronger model wins every
native island pixel, leaving the weaker source in the catalogue but absent
from the exclusive owner plane. The same contradiction can occur for nearby
overlapping models. Neither source count nor file integrity is the defect.

The frozen `phase-5-compact-held-out-sentinel-source-union-adapter-pre-review.json`
explicitly requires each source to own a pixel and includes a fail-closed
zero-owner test. The downstream matcher also rejects an asserted support
label absent from its plane. Deleting the adapter assertion therefore both
weakens the reviewed contract and leaves a later failure. Dropping the source,
allocating an arbitrary pixel or switching it to the whole island would
silently alter catalogue denominators or topology and is not acceptable.

**Recommended prospective remedy:** retain native source/component records
unchanged and represent absent exclusive derived support explicitly, separately
from catalogue measurement availability. Review how that representation
enters the already-defined centroid/overlap matching rules and topology
diagnostics, without changing thresholds, denominators, confidence rules or
comparator identities. Test the representation and all downstream compiler
seams with synthetic dominated, coincident, separated, fitless and unavailable
cases before adopting it. Preserve every formerly valid projection exactly.
The scientific owner approved this amendment on 2026-09-08. It is recorded in
`config/contracts/phase-5-r6-unavailable-source-support-amendment.json`;
the original hash-bound review and v1 adapter remain unchanged.

### Implemented representation and fixture gates

The R6-only v2 projection reuses the original native membership checks,
Gaussian model arithmetic and native catalogue records. It preserves pixel
winners and stable ties, including gaps in source label numbering. A source
with no winning pixels receives `support_label=None`; no pixel is allocated
to make its label exist, and no source or component row is removed.
The coordinate construction also retains the historical array layout: a
synthetic final audit caught layout-dependent rounding in the reused model
kernel. A test-first correction verifies exact model values and pixel winners
for nearly tied anisotropic models, not only visibly separated sources.

The R6 validation catalogue record accepts that explicit optional label;
the historical record and compiler remain unchanged. The amended compiler
reuses the historical matching, strata and metric kernels through a narrow
read-only record boundary. An asserted positive label still has to exist.
Matching uses the
unchanged centroid-in-one-beam-dilation rule when overlap is unavailable;
it does not invent overlap, shrink a denominator or relax a threshold.
Unmatched sources still count against reliability. Topology statistics
describe actual support; an unavailable source is not an additional support
island. The binary mask remains the actual published mask, including fitless
islands, independently of model ownership.

Source diagnostics are schema **2**, with explicit
`unavailable_source_support_ids` and JSON `null` support labels. Source
measurement summaries are schema **5**: source counts retain every native
row, source-union counts count available supports, and
`unavailable_source_support_count` states the difference. These are current
validation schemas, not modifications or migrations of saved campaign
records. Existing completed records must remain byte-identical; any future
reuse is checked by the separately frozen continuation.

Synthetic tests cover dominated and coincident models, stable equal-model
ties, separated sources, unowned/empty islands, non-square planes, row order,
true duplicate or invalid membership, unavailable-support centroid boundary
cases, independent finder-to-truth measurements, reliability denominators,
publication masks, exact record serialization, and Serial/existing-Dask
equivalence. No finder, retained-data scoring or R6 retry is part of this
implementation. This does not assert that downstream campaign evaluation is
bug-free or that R6 has passed.

The review's next step was a new evaluation-only continuation. The original
2,400 paired products and 12 Dask comparisons are preserved, as are all 800
compact and eight Continuum completed evaluations (4,032 finder records with
verified checksums and capture/census bindings). No finder reruns are needed
for this adapter work. Reuse the verified completed records where equivalent,
evaluate only missing inputs, and keep the original R6 candidate isolated
from the later notebook-only repairs. Do not tune or rescore closed results.
That continuation has now reused all 808 completed inputs byte-for-byte and
evaluated only the 1,592 missing inputs, without finder or Dask reruns. The
process repair is complete; scientific acceptance is not. Preserve both the
historical failure and the completed scientific terminal, and obtain a
separate prospective scientific review before any further repair or run.
