# Source-finding domain model

This page maps the stable boundaries around Hebog. It describes ownership and
data flow, not a detailed class design. The terms are defined in the
[domain glossary](../reference/domain-glossary.md), and current compatibility
behaviour is frozen in the
[Rapthor source-finding contract](../reference/rapthor-source-finding-contract.md).

## System context

```mermaid
flowchart LR
    R["Rapthor orchestration<br/>Prefect/Dask graph, retries, resources"]
    W["Other pipelines and science workflows<br/>own orchestration and adapters"]
    F["FITS and WSClean products<br/>images, sky models, sector geometry"]
    H["Hebog scientific boundary<br/>configuration, kernels, materialised results"]
    E["Hebog executor policy<br/>serial, local, existing Dask client"]
    A["Compatibility adapter<br/>product names and schemas"]
    L["LSMTool / sky-model filtering<br/>membership, grouping, beam conversion"]
    P["Restartable Rapthor products<br/>catalogue, RMS, mask, filtered models"]
    B["Frozen PyBDSF references<br/>compatibility oracle only"]
    Q["Equivalence harness<br/>science and downstream decisions"]

    R -->|"paths, config, resource budget"| H
    W -->|"inputs, config, executor"| H
    F --> H
    H --> E
    H --> A
    A --> L
    L --> P
    H --> P
    P --> R
    H -->|"versioned domain results"| W
    B --> Q
    H --> Q
    Q --> R
```

Rapthor owns operation ordering, top-level Dask scheduling, retries, restart
state, and resource admission. Hebog owns scheduler-independent scientific
configuration and source-finding behaviour. It may use an executor for coarse
work, but it does not create a hidden cluster or send live scheduler state in
results.

Other pipelines and science workflows enter through the same public
scientific boundary and provide their own orchestration, executor, and product
adapter. Their integration code does not need Rapthor, Prefect, LSMTool, or
Dask objects when serial execution and Hebog's native products satisfy the
workflow.

The compatibility adapter is a boundary rather than a settled package. ADR-006
will decide its schema after frozen products and contract tests expose the
required mapping. PyBDSF remains a test oracle and feature-flagged fallback,
not a runtime dependency of Hebog's scientific kernels.

## Processing and data flow

```mermaid
flowchart LR
    TI["True-sky image"]
    FI["Flat-noise image"]
    SM["WSClean true/apparent<br/>sky-model components"]
    BG["Background and true-sky<br/>RMS estimation"]
    DN["Normalize and threshold"]
    IS["Islands, deblending,<br/>measurement and fitting"]
    FR["Flat-noise RMS estimation"]
    TR["True-sky RMS product"]
    CA["Source catalogue"]
    MA["Source-filtering mask"]
    AD["Compatibility adapter<br/>filter and group components"]
    FM["Filtered true/apparent<br/>sky models"]
    DG["Diagnostics join<br/>RMS, source count, flux, astrometry"]
    OUT["Materialised result records"]

    TI --> BG --> DN --> IS
    BG --> TR
    IS --> CA
    IS --> MA
    FI --> FR
    SM --> AD
    MA --> AD --> FM
    TR --> DG
    FR --> DG
    CA --> DG
    FM --> OUT
    MA --> OUT
    CA --> OUT
    TR --> OUT
    FR --> OUT
    DG --> OUT
```

The true-sky and flat-noise branches may execute concurrently only when
Rapthor admits their combined CPU and memory demand. Both produce files before
the diagnostics join, allowing retries and restarts without serializing image
objects through Dask.

## Large-image decomposition

```mermaid
flowchart LR
    IN["Logical image planes<br/>up to 100,000 × 100,000"]
    PM["Partition manifest<br/>cores, halos, ownership, chunks"]
    TM["Bounded tile maps<br/>local scientific kernels"]
    BS["Boundary summaries<br/>statistics, labels, source state"]
    HR["Hierarchical reconciliation<br/>tree reductions and stable IDs"]
    CP["Retryable chunk products<br/>RMS, masks, catalogue shards"]
    CM["Compatibility materialisation<br/>Rapthor products"]
    DC["Existing Dask cluster<br/>1 to 200+ worker nodes"]

    IN --> PM --> TM --> BS --> HR --> CP --> CM
    DC --> TM
    DC --> HR
    DC --> CP
```

ADR-005 makes the partition manifest part of the stable scientific boundary.
Every tile has a non-overlapping output core and a stage-specific read-only
halo. Local maps emit bounded boundary summaries; tree reductions reconcile
global statistics, connected labels, cross-scale sources, and stable
identifiers without gathering a full plane on the scheduler or one worker.
The one-tile path uses the same ownership and reconciliation rules as the
multi-node path.

The physical chunk store and final large-product materialisation format remain
Phase 0 and Phase 1 evidence-driven decisions. FITS compatibility at the
Rapthor boundary does not require every internal stage to rewrite a complete
FITS plane.

Production nodes are expected to have hundreds of GB of RAM. Executor policy
may use the admitted fraction for larger tile batches and bounded caches, while
retaining headroom for concurrent Rapthor work. Resource sizing changes
execution topology, not tile ownership or scientific results.

## Boundary invariants

- Scientific kernels accept arrays, immutable configuration, and explicit
  metadata; they do not import Rapthor or a global Dask client.
- Domain records, algorithms, and the public pipeline do not import Rapthor,
  Prefect, LSMTool, workflow adapters, or concrete scheduler implementations;
  adapters depend inward on the public scientific API.
- Image-sized kernels accept bounded tile cores, explicit halos, and global
  coordinates; no worker or public record requires a complete large plane.
- Source membership, stable identifiers, and materialised values are invariant
  to valid tile geometry, partition origin, worker count, task order, and
  retries within reviewed numerical tolerances.
- Production graph size is proportional to tiles and stages, never pixels,
  RMS windows, or small islands.
- Public task inputs and results contain paths and small serializable records.
- Apparent-sky, true-sky, flat-noise, RMS, residual, mask, catalogue, and
  filtered-model products remain distinguishable.
- Serial execution defines deterministic Hebog behaviour. Other executors
  match it before comparison with PyBDSF.
- Compatibility names remain at the adapter. They do not determine Hebog's
  internal algorithm or domain model.
- A product is not considered compatible until schema, units, empty behaviour,
  and downstream Rapthor decisions pass contract tests.

A detailed executor diagram is intentionally deferred until the asynchronous
executor contract stabilizes in Phase 6. The large-image decomposition above
records the stable data and ownership boundaries without fixing executor
classes or a physical chunk-store technology.
