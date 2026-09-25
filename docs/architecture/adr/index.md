# Architectural Decision Records

An ADR records one architecturally significant decision: its context, the
options considered, the outcome and its consequences. Read them to learn why
Hebog is built the way it is; read the
[architecture overview](../index.md) for what the design is today. New ADRs
start from the [template](template.md). When a decision is replaced, the old
ADR is kept and marked as superseded.

| ADR | Status | Summary |
|-----|---------|----------|
| [ADR-001: Use Architecture Decision Records](001-use-architectural-decision-records.md) | 🟢 Accepted | Use ADRs to explain the rationale behind architecturally significant design choices for future developers and AI assistants |
| [ADR-002: Manage dependencies with uv](002-manage-dependencies-with-uv.md) | 🟢 Accepted | Use uv to manage project dependencies |
| [ADR-003: Limit Hebog to Rapthor's source-finding contract](003-limit-hebog-to-rapthor-source-finding-contract.md) | 🟢 Accepted | Qualify the Rapthor feature slice through a pipeline-neutral scientific core |
| [ADR-004: Keep top-level scheduling in Rapthor](004-keep-top-level-scheduling-in-rapthor.md) | 🟢 Accepted | Keep resource and graph ownership in Rapthor while Hebog exposes explicit executors |
| [ADR-005: Scale large images with hierarchical tiles](005-scale-large-images-with-hierarchical-tiles.md) | 🟢 Accepted | Bound worker memory with haloed tiles, boundary summaries, and hierarchical reconciliation |
| [ADR-006: Isolate compatibility with versioned internal schemas](006-isolate-compatibility-with-versioned-schemas.md) | 🟢 Accepted | Keep domain schemas explicit and map legacy products only at outer adapters |
| [ADR-007: Use Zarr for intermediate image storage](007-use-zarr-for-intermediate-image-storage.md) | 🟢 Accepted | Keep one maintained intermediate backend and optimize Zarr across all execution tiers |
| [ADR-008: Make the continuum composition tile-native](008-make-the-continuum-composition-tile-native.md) | 🟢 Accepted | Define the pass structure, halo, ownership, boundary summary and merge of every public continuum stage |
