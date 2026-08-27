# Phase 5 source-association replay-composition pre-review

## Decision

Do not adapt or rerun the consumed public-finder correction replay in place.
Candidate `26e639a...` changes the source tree and complete candidate
configuration, so the previous execution approval cannot transfer to it.

The machine-readable pre-review is
`config/contracts/phase-5-public-finder-source-association-replay-composition-pre-review.json`,
SHA-256
`a2e13e1126ce7733949dca570116c8b9cb73eb8128226bedcd9ee214f44e32a3`.
It authorizes nothing. Wrapper implementation, no-write verification, identity
freezing, cumulative replay, viewed SDC1 or Hydra execution, another campaign,
qualification, tuning, rescoring, cutover, and release are all false.

## Why another composition is required

The existing correction wrapper, SHA-256 `04a3a543...`, is a consumed
write-once evidence producer. It is bound to:

- candidate `b1d59e5...`;
- production source tree `2de6564e...`;
- correction configuration `65c8876d...`; and
- output ledger `1ac6deb2...`.

The source-association candidate is instead commit `26e639a...`, source tree
`34fecf30...`, and complete configuration `78dbb230...`. That configuration is
computed by `public_finder_source_association_candidate_configuration` and
binds the approved scientific pre-review and fixture-only implementation
decision. Treating the old wrapper or its consumed execution decision as
authority for these changed identities would mislabel the candidate and break
the write-once evidence chain.

## Smallest prospective repair

After separate named approval, add one new fail-closed wrapper around the
checksum-bound correction wrapper. The new wrapper may change only five
things:

1. bind candidate revision `26e639a...`, source tree `34fecf30...`, and
   configuration `78dbb230...`;
2. compute that configuration through the source-association configuration
   builder and exact approved contract records;
3. retain `build_public_finder_correction_continuum_products` from the exact
   new source tree, where it now publishes the approved component and source
   records;
4. publish to a new absent write-once ledger and scratch namespace; and
5. freeze a new non-executable identity review.

Everything else remains delegated and checksum-bound: reference provenance,
compact generation, compilation, evaluation, regression comparison, atomic
publication, endpoint registry, evaluation contract, and scientific gates.
The exact population remains 800 compact and 1,600 Continuum images with two
workers. Reconstructed reference terminal `48209eae...`, closed baseline
`a45303df...`, and the exact four-runtime registry `cc22c773...` remain
unchanged.

The inherited Hebog container remains only a compatibility dependency. The
candidate must be recorded as an exact source overlay; the wrapper must not
claim that source association is baked into the historical image.

## Required fail-closed validation

Implementation must be test-first and fixture/no-write only. It must prove
that the real wrapper:

- selects the exact candidate revision, source tree, configuration builder,
  scientific builder, and new output path;
- rejects the old consumed execution decision;
- rejects candidate, contract, implementation-decision, wrapper, delegated
  program, reference, runtime, population, worker, endpoint, or gate drift;
- preserves the exact compact composition and every historical science
  object not named above;
- completes the full reference and identity preflight before creating scratch
  or opening scientific inputs; and
- rejects an existing prospective scratch directory or output ledger.

Fixture validation may not open terminal replay products, viewed SDC1 or Hydra
products, or reference-finder catalogues. It may not change thresholds,
background or RMS, minimum area, support recovery, apertures, flux,
astrometry, shape, source association, runtime dependencies, or gates.

Only after those checks pass may a new non-executable identity review be
frozen. That review will still require a separate named approval before one
complete cumulative replay can start.

## Approval requested

The next decision is intentionally limited to wrapper implementation,
fixture/no-write validation, and non-executable identity freezing:

> I approve the Phase 5 public-finder source-association replay-composition
> pre-review SHA-256
> `a2e13e1126ce7733949dca570116c8b9cb73eb8128226bedcd9ee214f44e32a3`
> and its recommendations. This authorizes test-first implementation and
> fixture/no-write validation of the minimal replay wrapper, followed by
> freezing exact non-executable identities for candidate
> `26e639ace9d39b039eb7c3114427277c91809591`, configuration
> `78dbb230cbb726cbbe02b74f2e7fe96bc42801e2102bf15f0580c0643befe946`,
> reconstructed reference terminal
> `48209eae94b7dfe66c5098feac56ac8be608c76b6b1a1c4f6c1ff35028c69cc2`,
> and closed baseline
> `a45303dfa8f544830a65988fc0b3371678b9cda37cd5f62d2b650163e5dbfbf9`.
> It does not authorize the cumulative replay, viewed SDC1/Hydra execution,
> another campaign, fresh qualification, tuning, rescoring, cutover, or
> release.
