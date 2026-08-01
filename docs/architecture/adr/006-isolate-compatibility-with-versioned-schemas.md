---
tags:
  - architecture
  - compatibility
  - schemas
---

# ADR-006: Isolate compatibility with versioned internal schemas

| | |
| --- | --- |
| **Status** | 🟢 Accepted |
| **Created** | 2026-07-18 |
| **Last Updated** | 2026-08-01 |
| **Deciders** | Gemma Danks |
| **Tags** | compatibility, schemas, Rapthor, PyBDSF, interoperability |

---

## Context

Rapthor currently consumes paths to materialised source-finding products:
source catalogues, true-sky and flat-noise RMS images, an island mask, filtered
sky models, and diagnostics. It reads a small set of PyBDSF catalogue columns
and relies on LSMTool-compatible filtering and empty-result behaviour, but it
does not consume live PyBDSF image, island, Gaussian, or source objects.

ADR-003 limits the initially qualified feature set to this contract while
keeping Hebog reusable in other pipelines. The
[Phase 0 inventory](../../reference/rapthor-source-finding-contract.md)
identifies legacy names and product suffixes that must be preserved at the
Rapthor boundary. Hebog still needs clear internal concepts for sources,
islands, measurements, masks, image planes, partitioned products, and
materialised results. Large images also require chunk and catalogue-shard
records that do not exist in the current PyBDSF product model.

Phase 1 has now defined the initial internal catalogue and materialised-result
fields, null representation, ordering, relationship validation, and migration
tests. They remain provisional until the Phase 0 human scientific sign-off;
the boundary and evolution strategy in this ADR remain unchanged.

## Problem Statement

Should Hebog use versioned domain-oriented internal schemas with an isolated
compatibility adapter, mirror PyBDSF/LSMTool schemas throughout the package, or
translate ad hoc dictionaries only when writing products?

## Options Considered

| Option | Description | Scientific clarity | Rapthor compatibility | Other workflows | Evolution safety | Large-image products | Overall score |
| --- | --- | --- | --- | --- | --- | --- | ---: |
| **Weight** | - | 2 | 2 | 2 | 2 | 1 | - |
| **Versioned internal schemas** | Typed domain records mapped by outer adapters | ✅ | ✅ | ✅ | ✅ | ✅ | 27 |
| **Mirror legacy schemas** | Use PyBDSF columns and LSMTool names internally | ❌ | ✅ | ❌ | ⚠️ | ❌ | 14 |
| **Ad hoc dictionaries** | Translate loosely structured mappings at write time | ❌ | ⚠️ | ⚠️ | ❌ | ⚠️ | 12 |

✅ = 3 (good), ⚠️ = 2 (acceptable), ❌ = 1 (poor)

## Decision Outcome

Hebog will use **versioned, domain-oriented internal schemas with isolated
compatibility and workflow adapters**.

Internal records use the agreed Hebog vocabulary and make coordinate frames,
units, array axis order, identifiers, nullability, and product roles explicit.
They are small, typed, serializable, and free of open files, scheduler clients,
workflow state, and image-sized arrays. Image planes remain behind bounded
I/O boundaries; schemas refer to paths, logical dataset identifiers, chunks,
checksums, windows, or small summaries.

Every materialised or externally exchanged schema has an explicit integer
schema version. Readers validate supported versions and reject unknown or
ambiguous fields rather than guessing. Additive changes remain compatible only
when older readers can safely ignore them under a documented rule. A semantic
or structural breaking change creates a new schema version, migration note,
and contract tests. Before 1.0 these changes are permitted but never silent.
The choice of dataclass, Pydantic model, FITS table representation, or another
implementation mechanism is made per concrete Phase 1 contract; this ADR does
not require one schema library everywhere.

Catalogue schema version 1 uses strict immutable Pydantic records and
canonical JSON. It distinguishes islands, source candidates, and fitted
Gaussian components; uses ICRS degrees, Jy, Jy/beam, hertz, explicit position
epoch, and an explicit spectral convention; represents unavailable values as
`None`; and requires stable unique canonical identities. The first version is
MFS-only and rejects mixed reference frequencies.

`SourceFinderResult` schema version 2 replaces its earlier path-only scaffold.
Each concrete materialised product now records a role, media type, content
schema, byte count, SHA-256, and scientific status. Existing path properties
remain available to consumers. Only RMS may be scientifically unavailable in
a successful core result, preventing copied input pixels from being described
as an estimate. No implemented Hebog source-finding pipeline emitted result
schema version 1.

The Rapthor adapter depends inward on Hebog's public pipeline and schemas. It
owns legacy catalogue names such as `Source_id`, `Isl_Total_flux`, and
`DC_Maj`; required suffixes; PyBDSF/LSMTool unit and null conventions;
true-sky/apparent-sky component matching; mask-based grouping; diagnostics
translation; and reviewed empty/failure compatibility. No scientific kernel
imports those names or external packages.

Other workflows may consume the internal materialised schema directly or
provide their own adapter. They do not pass through a Rapthor-shaped product
unless they genuinely require that compatibility contract. Frozen PyBDSF
products remain validation inputs, not the internal schema definition or a
runtime dependency.

## Consequences

- Good, because scientific code uses precise domain names instead of legacy
  column and workflow terminology.
- Good, because Rapthor compatibility can evolve and be tested without
  coupling every algorithm, executor, and alternate workflow to PyBDSF.
- Good, because schema versions and migrations make pre-1.0 changes explicit
  and give restartable materialised products a reliable interpretation.
- Good, because bounded chunk, shard, and partition records can support
  100,000-by-100,000 images without pretending they are single legacy files
  during intermediate stages.
- Bad, because every compatibility product requires an explicit, tested
  mapping and may require a final materialisation pass.
- Bad, because Hebog must maintain its internal schema and the Rapthor adapter
  until the legacy boundary is retired.
- Bad, because producers constructing the public result must migrate from the
  path-only version 1 scaffold to versioned `MaterializedProduct` records.
- Risk: duplicating large image or catalogue data during translation could
  erase performance gains. Adapters must stream, map columns, and materialise
  from bounded chunks or shards rather than copy complete large products in
  memory.
- Risk: a superficially compatible catalogue can still alter LSMTool or
  Rapthor decisions. Contract and acceptance tests must validate downstream
  behaviour, not field names alone.

## Confirmation

- Architecture tests reject imports of Rapthor, Prefect, LSMTool, PyBDSF, and
  concrete schedulers from algorithms and domain records.
- Phase 1 schema tests cover version validation, physical domains, nulls,
  ordering, referential integrity, empty catalogues, product roles and status,
  unsupported versions, and deterministic serialization.
- Rapthor adapter contract tests cover every consumed catalogue field and
  product, normal and empty paths, filtered-model membership/grouping, and
  diagnostics source counts.
- Frozen released-PyBDSF and pinned-`master` products are converted through the
  same adapter used by the comparison runner; tests never redefine mappings
  locally.
- A non-Rapthor workflow smoke test consumes Hebog-format materialised results
  without importing Rapthor, Prefect, or LSMTool.
- Reviews reject legacy product names in scientific kernels and reject public
  records containing live external objects or image-sized arrays.

## Links

| Type | Links |
| --- | --- |
| **ADRs** | [ADR-003](003-limit-hebog-to-rapthor-source-finding-contract.md), [ADR-004](004-keep-top-level-scheduling-in-rapthor.md), [ADR-005](005-scale-large-images-with-hierarchical-tiles.md) |
| **Documentation** | [Rapthor source-finding contract](../../reference/rapthor-source-finding-contract.md), [Domain glossary](../../reference/domain-glossary.md) |
| **Plan** | [Implementation plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md) |
