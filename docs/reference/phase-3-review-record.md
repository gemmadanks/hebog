# Phase 3 scientific review record

This record closes the named human review required by the Phase 3 compact
detection exit gate. It approves the scientific contract for an experimental
`0.x` vertical slice; it does not claim complete PyBDSF equivalence, catalogue
equivalence, Rapthor readiness, multiscale completeness, or production
readiness.

## Reviewer and decision

- **Reviewer:** Gemma Danks
- **Role or scientific authority:** Data Processing Software Engineer
- **Review capacity:** Project owner and named ADR decider reviewing the
  Hebog/Rapthor source-finding contract
- **Review date:** 2026-08-02
- **Decision:** Approved
- **Required amendments:** No threshold or algorithm amendments. Documentation
  was updated to make the community literature and cross-pipeline-consensus
  principle explicit alongside the scientific pre-review amendments already
  reflected in the glossary, contracts, gates, and phase boundaries.
- **Qualification-data confirmation:** The held-out Phase 3 qualification
  recipe and margins were frozen before its result was inspected. Its result
  was not used to tune the reviewed thresholds or algorithms.

## Approved scientific principles

Hebog remains within the community best-practice envelope documented by
peer-reviewed radio-source-finding literature and source-finder challenges
summarized in the [scientific pre-review](scientific-pre-review.md). Consensus
across established observatory pipelines is a strong guide to expected
practice, but neither a majority convention, one pipeline, nor PyBDSF is
scientific ground truth. Analytic or injected governed truth remains the
primary scientific oracle. A deliberate departure from literature or
cross-pipeline consensus requires an explicit rationale, governed comparison
evidence, and renewed human scientific review before promotion.

## Approved Phase 0 foundations

The reviewer approves the domain glossary and the distinction between
islands, deblended regions, Gaussian components, source candidates, catalogue
rows, and sky-model components. Primary-beam-corrected and
primary-beam-uncorrected are the canonical scientific terms; `true_sky` and
`flat_noise` remain documented compatibility aliases.

The normal Rapthor compatibility profile is explicit `5.0/3.0` detection and
island thresholds. The early-cycle profile is separately explicit `5.0/4.0`;
the `7.5/5.0` helper fallback is not the representative production profile.
These are compatibility operating points, not universal pipeline-neutral
defaults.

Scientifically empty results contain zero detections. Dummy sky-model rows and
copied pseudo-RMS images are legacy serialization behaviours confined to an
explicit compatibility adapter, never relabelled as scientific detections or
RMS estimates. Initial qualification may be MFS-only; unsupported cubes or
channel-image sets must fail clearly until frequency association, per-plane
beams, reference-frequency flux, spectral fitting, and non-detection semantics
are reviewed.

Low-SNR behaviour is reported as completeness and reliability curves with
two-sided 95% confidence intervals rather than one fixed recovery fraction at
the detection boundary. PyBDSF remains a compatibility oracle rather than
truth.

## Approved Phase 3 decisions

1. **Scope and claims.** Phase 3 establishes compact detection topology only:
   normalized threshold masks, accepted connected islands, deterministic
   deblended regions, and restartable background, RMS, and mask products.
   Measurement, fitting, catalogue compatibility, multiscale recovery, and
   the final Rapthor filter decision remain later work.
2. **Threshold semantics.** Island membership is inclusive at `3.0` sigma;
   detection seeds are strictly above `5.0` sigma. Every accepted island must
   contain a seed. The `75.0`-sigma adaptive-RMS candidate threshold is an
   explicit provisional Rapthor profile, not a universal default.
3. **Connectivity and size.** Eight-neighbour connectivity is the fixed
   compact topology. The current beam-aware compatibility policy uses a
   six-pixel minimum floor supplied explicitly to the scientific kernel.
4. **Compact deblending.** Eligible marker peaks are strictly above `5.0`
   sigma, the governed minimum-separation radius is two pixels, and the
   weaker peak remains separate when it is at least `1.0` sigma above the
   shared saddle. Equality at that saddle-depth boundary survives. The
   resulting region is an input to Phase 4 measurement, not yet a source.
5. **Scientific margins.** The foreground-sensitive mask and object gates in
   `config/contracts/phase-3-scientific-gates.json` are approved as
   reviewed-provisional Phase 3 `0.x` margins. Low-SNR threshold crossings
   remain report-only. Viewed held-out results must not be used to tighten the
   margins without replacing the held-out qualification evidence.
6. **Deferral boundaries.** The five unmatched multiscale PyBDSF objects on
   the representative image are explicit Phase 5 work. The compact match is
   not presented as complete-mask equivalence. MFS-only initial scope is
   approved under the failure behaviour above.
7. **Partition invariance.** Tile shape, partition origin, worker count, task
   order, retry, and serial or Dask execution must not change scientific mask
   membership, island identity, or deblended-region results.
8. **Performance accounting.** The inclusive 3.5-second Phase 3 component
   budget is approved. Moving durable background, RMS, and mask publication
   into this component reduces the later output budget by the same amount and
   does not enlarge the complete-path budget.

## Remaining independent reviews

This approval closes the Phase 0 domain-review item and the Phase 3 named
scientific-review item. Independent domain confirmation remains advisable
before production cutover. Facility qualification, complete Phase 4/5
scientific equivalence, full Rapthor acceptance, the dual-PyBDSF end-to-end
performance gate, and 100-to-200-plus-node scalability remain open.
