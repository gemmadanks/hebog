---
tags:
  - architecture
  - maintainability
---

# ADR-009: Place the reviewed science below the stages

| | |
| --- | --- |
| **Status** | 🟢 Accepted |
| **Created** | 2026-10-06 |
| **Last Updated** | 2026-10-09 |
| **Deciders** | Gemma Danks, through plan task 59, which allowed either direction |
| **Tags** | layering, dependencies, architecture tests |

---

## Context

The documented direction was
`adapters → pipeline/public_api → science → stages → algorithms`: `science/`
was described as composing the stages into the reviewed pipeline. The code
did not work that way. `public_api.py` runs the stages in order, and
`science/` holds what the stages apply: the reviewed profile and
configuration, the composition records (`models.py`, `catalogue_rows.py`)
and the catalogue-row kernels (`catalogues.py`). On 6 October 2026 the
static import graph, counting function-level and `TYPE_CHECKING` imports,
ran both ways between the two packages:

- four imports from `stages/` into `science/`: `stages/catalogue_rows.py`
  takes the rows and the row kernels, and `stages/islands.py` the row
  kernels and the island records; and
- one import from `science/` into `stages/`:
  `science/configuration.py` built the detection stage's
  `DetectionStageConfig`, which was defined in `stages/detection.py`.

Apart from `io/__init__.py` re-exporting one astrometry function, no other
edge contradicted the documented layering. The architecture test had import
rules for `algorithms/`, `data_models/`, `io/`, `config.py` and
`pipeline.py`, and kept `hebog.validation` out of the public composition
only, so it could not see the cycle.

## Problem Statement

The two packages imported each other, so no direction described the code.
Which direction should the layering state, and what has to move for the
code to follow it?

## Options Considered

| Option | Description | One direction | Moves | Modules where readers expect them | Quick-check cost | Overall score |
| --- | --- | --- | --- | --- | --- | ---: |
| **Weight** | - | 3 | 2 | 2 | 1 | - |
| **B: redraw the direction** | `public_api → stages → science → algorithms`; move `DetectionStageConfig` into `config.py` beside the other per-stage configurations | ✅ | ✅ | ✅ | ✅ | 24 |
| **C: keep the direction with exemptions** | Exempt the four stage imports of `science/` | ❌ | ✅ | ✅ | ✅ | 18 |
| **A: move the science below the stages** | Move the rows, the row kernels and the records into `data_models/` and `algorithms/` | ✅ | ❌ | ⚠️ | ❌ | 16 |

✅ = 3 (good), ⚠️ = 2 (acceptable), ❌ = 1 (poor)

Option A moves three modules. `science/models.py` imports two algorithm
modules, and `algorithms/` imports `data_models/`, so the records cannot
join `data_models/` without a cycle; the 1,734 lines of row kernels would
join `algorithms/` under a name that no longer says they are the reviewed
catalogue. Moving `science/catalogue_rows.py` also changes the code that
identifies the quick check's cached PyBDSF references, so every reference
would run again once. After all that, `science/` would hold only the
configuration and profile, and would still not compose the stages.

Option C keeps a cycle between two packages, so the table would describe
no direction at all.

## Decision Outcome

We will use **option B**. The direction is
`adapters → pipeline/public_api → stages → science → algorithms`, with
`public_api → public_science → science`, `executors/` and `io/` used by
`stages/` and `public_api.py`, and `data_models/` and `config.py` shared by
every layer. `science/` is the reviewed science that the stages apply, and
imports no stage, executor or `io` module. `DetectionStageConfig` moved from
`stages/detection.py` to `config.py`, where the other per-stage
configurations already were. No module moved, and the products are
byte-identical.

## Consequences

- Good, because the documented direction describes what the code does, and
  names one place where the stages are composed: `public_api.py` when this
  was decided, and `stages/composition.py` since plan task 70 moved the
  sequence below the public boundary on 9 October 2026, within the same
  layering.
- Good, because one class moved: no module path changed, and the quick
  check's PyBDSF references stay valid.
- Good, because `config.py` now holds every per-stage configuration.
- Bad, because the name `science/` no longer says where it sits: readers
  must learn that it is below the stages, not above them.
- Risk: a catalogue-row or record change that needs a stage would reverse
  the edge again. The table rejects that import; move the stage-facing part
  into `stages/` instead.

## Confirmation

`LAYER_IMPORTS` in `tests/unit/test_architecture.py` states, as one table,
the layers every layer of `hebog` may import, counting every import
statement in any scope. The test requires the table to name every layer,
to form no cycle, and to keep `science` below `stages` and `stages` below
`public_api`. An import outside the table needs a named exemption with its
reason, and each exemption must still match an import the table rejects.
The same test keeps `hebog.validation` out of every production layer,
Rapthor, Prefect and LSMTool out of every module, and Dask inside
`executors/`, and keeps the imports that load `public_api.py` and the Dask
executor deferred.

## Links

| Type | Links |
| --- | --- |
| **ADRs** | [ADR-004](004-keep-top-level-scheduling-in-rapthor.md), [ADR-006](006-isolate-compatibility-with-versioned-schemas.md), [ADR-008](008-make-the-continuum-composition-tile-native.md) |
| **Documentation** | [Architecture overview](../index.md), [Quality attributes](../../explanation/quality-attributes.md) |
| **Plan** | [Implementation plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md) |
