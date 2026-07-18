---
tags:
  - architecture
  - scope
---

# ADR-003: Limit Hebog to Rapthor's source-finding contract

| | |
| --- | --- |
| **Status** | 🟢 Accepted |
| **Created** | 2026-07-18 |
| **Last Updated** | 2026-07-18 |
| **Deciders** | Gemma Danks |
| **Tags** | scope, compatibility, source finding |

---

## Context

Rapthor currently uses PyBDSF through LSMTool to detect emission, filter and
group WSClean sky-model components, and produce catalogue, RMS, mask, and
diagnostic products. PyBDSF has a much broader feature set than Rapthor uses.
Reproducing that complete feature set would increase delivery time and the
scientific validation surface without improving the first production use case.

The Phase 0 [contract inventory](../../reference/rapthor-source-finding-contract.md)
identifies the current consumer boundary. Hebog must demonstrate scientific
equivalence for that behaviour and preserve a PyBDSF fallback during
qualification.

## Problem Statement

Should Hebog reproduce PyBDSF generally, provide a generic source-finder
framework, or implement only the source-finding contract consumed by Rapthor?

## Options Considered

| Option | Description | Delivery focus | Rapthor compatibility | Scientific validation | Evolvability | Overall score |
| --- | --- | --- | --- | --- | --- | ---: |
| **Weight** | - | 2 | 2 | 2 | 1 | - |
| **Rapthor contract** | Implement and qualify the consumed vertical slice | ✅ | ✅ | ✅ | ✅ | 21 |
| **Generic framework** | Start with pluggable source-finder abstractions | ⚠️ | ⚠️ | ⚠️ | ✅ | 15 |
| **Full PyBDSF reproduction** | Recreate all PyBDSF capabilities and outputs | ❌ | ✅ | ❌ | ⚠️ | 12 |

✅ = 3 (good), ⚠️ = 2 (acceptable), ❌ = 1 (poor)

## Decision Outcome

Hebog will implement **the source-finding behaviour and products required by
Rapthor**. The initial compatibility surface includes reviewed configuration,
source catalogue fields, true-sky and flat-noise RMS products, the
source-filtering mask, filtered sky-model behaviour, diagnostics inputs, and
empty/failure semantics.

PyBDSF implementation code will not be copied or mechanically translated.
Hebog will use independently structured implementations of published
algorithms, validated first against analytic truth and then against frozen
compatibility products and Rapthor decisions.

Additional features enter scope only when the Rapthor contract, approved
dataset matrix, or a separately accepted use case demonstrates their need.

## Consequences

- Good, because delivery and validation stay focused on measurable production
  value.
- Good, because Hebog can use clearer internal schemas and algorithms rather
  than inheriting PyBDSF's object model.
- Good, because the compatibility boundary can be tested and versioned
  independently.
- Bad, because Hebog is not a drop-in PyBDSF replacement for unrelated users
  or workflows.
- Bad, because new Rapthor requirements may expand the qualified contract and
  dataset matrix.
- Risk: an incomplete contract inventory could omit behaviour that only appears
  in production. Dual-run qualification and the PyBDSF fallback mitigate this.

## Confirmation

The implementation plan, domain glossary, contract tests, dataset manifest,
and compatibility reports define the supported surface. Reviews reject
features justified only as “PyBDSF supports it” without a Rapthor requirement
or accepted use case.

## Links

| Type | Links |
| --- | --- |
| **ADRs** | [ADR-004](004-keep-top-level-scheduling-in-rapthor.md) |
| **Documentation** | [Rapthor source-finding contract](../../reference/rapthor-source-finding-contract.md) |
| **Plan** | [Implementation plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md) |
