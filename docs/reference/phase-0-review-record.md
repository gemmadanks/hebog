# Phase 0 review record

This record distinguishes frozen technical decisions from reviews that require
scientific or facility authority.

## Accepted project decisions

Gemma Danks is the named decider on accepted ADRs 003, 004, 005, and 006.
Together they freeze the Rapthor-focused scope, external ownership of the
top-level scheduler, hierarchical haloed tiling, and versioned compatibility
boundary. Their confirmation criteria remain active gates rather than one-time
documentation approval.

The performance curve, public behaviour list, regression and qualification
manifests, and provisional large-image resource envelope are frozen for Phase
0. A later measured crossover or facility constraint may amend them only
through reviewed evidence, the implementation plan, and `LOG.md`.

The technical Phase 0 evidence was completed on 2026-07-18. It includes exact
released/master revisions and dependency inventories, an immutable reference
container digest, one warm-up and five measured compact and representative
runs per reference, per-stage timing/CPU/RSS records, frozen reference
products, an independent reference-divergence report, and warm one-tile
overhead measurements. The technical completion does not confer the external
approvals below.

## Scientific review still required

An SKA imaging/domain reviewer must confirm or amend, with their name and date:

- the definitions and legacy mappings in the domain glossary;
- the public/internal naming conventions;
- the catalogue, RMS, mask, empty-result, and failure semantics in the Rapthor
  source-finding contract;
- the scientific thresholds in Section 5 of the implementation plan; and
- the classification and coverage of the frozen regression and held-out
  qualification cases.

Until that sign-off is appended here, thresholds remain engineering gates and
must not be described as domain-approved. This does not block reproducibility,
I/O scaffolding, or red-green-refactor Phase 1 work that cannot prejudge a
scientific choice; it does block a domain-approved scientific-equivalence or
production-readiness claim.

## Facility review still required

The controlled runner owner must map the representative 512 GiB profile and
storage capability onto an actual facility, then record node RAM, CPUs,
workers, threads, reserved headroom, concurrent demand, local spill medium,
shared-storage identifier, and permitted cache policy in the evidence record.
The 100,000-square gates cannot be marked demonstrated before the complete
1/10/50/100/200-node curve is retained and reviewed.
