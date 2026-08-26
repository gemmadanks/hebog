# Phase 5 public-finder correction replay-repair pre-review

## Decision

Do not run the approved cumulative replay with the frozen historical replay
program. Its no-write preflight selects the pre-correction candidate even
though the identity review names the new public-finder correction.

The machine-readable pre-review is
`config/contracts/phase-5-public-finder-correction-cumulative-replay-repair-pre-review.json`,
SHA-256
`e198df128900bf991c979764fc67dbda8a9b0a682be30f92bf70703122c1f162`.
It authorizes nothing. Implementation, cumulative replay, viewed public-data
execution, a new campaign, fresh qualification, tuning, rescoring, cutover,
and release are all false.

## What the preflight found

The user approved identity review `e2121fb8...`, candidate `b1d59e5...`, and
closed baseline `a45303df...`. Before creating a scratch directory or reading
scientific products, the preflight inspected the exact program bound by that
review, `review_phase5_cumulative_regressions.py` SHA-256 `5d41d31e...`.

That program still:

- hardcodes candidate revision `c184acf7...`;
- computes configuration with `post_correction_candidate_configuration`;
- writes Continuum results with `build_post_correction_continuum_products`;
  and
- reconstructs a runtime only when its older decision also names
  `c184acf7...`.

The approved correction instead requires revision `b1d59e5...`, production
source tree `2de6564e...`,
`public_finder_correction_candidate_configuration`, and
`build_public_finder_correction_continuum_products`. Its complete configuration
identity is `65c8876d...`, not the base-only `0e5dde51...` recorded as the
candidate configuration in the rejected identity review.

Running the frozen program would therefore produce a scientifically valid
ledger for the wrong candidate and label it as the correction. The preflight
failed closed. No process, candidate shard, scratch directory, or ledger was
created, and no scientific product was opened. The original approval is
recorded by decision `bf955638...`; it cannot transfer to a changed program or
replacement identity.

## Recommended repair

Add one minimal wrapper around the byte-exact historical replay. The wrapper
must delegate unchanged reference verification, compact generation,
compilation, evaluation, regression comparison, and atomic publication. It may
replace only these prospective seams:

1. candidate revision `b1d59e5...`;
2. candidate configuration `65c8876d...` computed from the approved correction
   contract;
3. the corrected Continuum product builder; and
4. provenance that distinguishes the exact source overlay from the inherited
   dependency container.

The wrapper must fail before input access if the source tree, correction
contract, configuration, baseline, population, runtime dependency identity,
authorization, or output state changes. The historical replay remains
unchanged and checksum-bound.

Fixture and no-write tests must exercise the actual wrapper composition. They
must prove that the corrected builder is selected, the compact builder and all
science gates remain the frozen objects, the old revision/configuration/builder
are rejected, and existing output or identity drift fails closed.

After implementation, a replacement identity review must bind the wrapper,
candidate, correction configuration, source-overlay provenance, closed
baseline, and absent output. A further named execution approval will still be
required before the replay starts.

## Approval requested

The current request is limited to implementing and fixture/no-write validating
the wrapper and freezing replacement exact identities:

> I approve the Phase 5 public-finder correction cumulative-replay repair
> pre-review SHA-256
> `e198df128900bf991c979764fc67dbda8a9b0a682be30f92bf70703122c1f162`
> and its recommendations. This authorizes implementation and fixture/no-write
> validation of the minimal replay wrapper and freezing replacement exact
> identities for candidate
> `b1d59e5aaf778a5fed4ea662afeba2ee100424ff`, correction configuration
> `65c8876dcdb484bd5a82b3520e065ea6bf33cf24cfdd33b592c6c859231c62f0`,
> and closed baseline
> `a45303dfa8f544830a65988fc0b3371678b9cda37cd5f62d2b650163e5dbfbf9`.
> It does not authorize the replay, execution on viewed SDC1/Hydra data, a new
> campaign, fresh qualification, tuning, rescoring, cutover, or release.
