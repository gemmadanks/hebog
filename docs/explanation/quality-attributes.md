# Quality attributes and coding principles

Hebog must stay scientifically trustworthy and fast while remaining easy to
understand, change, test and embed. Maintainability, extensibility,
interoperability and testability are architectural requirements with
enforced gates, not cleanup deferred until after performance work. The rules
themselves are in
[`AGENTS.md`](https://github.com/gemmadanks/hebog/blob/main/AGENTS.md); this
page gives the reasons behind them.

## Why dependencies point inward

Rapthor is the first consumer and defines the qualified feature set, but it
does not own Hebog's architecture: other pipelines and science workflows call
the same public API with their own inputs, executor, orchestration and
product adapter. So scientific algorithms and domain records import no
Rapthor, Prefect, LSMTool, workflow adapter or concrete scheduler, read no
ambient configuration and do no import-time I/O; the public pipeline composes
explicit dependencies, and adapters translate names, schemas and failure
behaviour at the edge. The [architecture overview](../architecture/index.md)
draws the layers and names the test that enforces them.

Library imports are inert so that a worker process, a notebook and a test can
import Hebog without side effects, and so that importing `hebog` never pulls
in Dask; a caller requesting `DaskExecutor` loads it deliberately.

## Why the code looks the way it does

- **Names carry science.** Units, coordinate order, shapes and ownership
  appear in names and types wherever ambiguity could change a result.
- **Small functions, immutable records, composition.** Dataclasses, context
  managers, iterators and structural protocols are preferred to inheritance
  hierarchies and manager objects, because the scientific intent must be
  obvious to a Python developer reading one function.
- **Explicit effects.** Side effects, mutation, resource ownership and failure
  behaviour are visible at the call site; there are no hidden globals,
  ambient clients, boolean mode flags or broad exception handlers.
- **Comments explain assumptions, not syntax:** units, tolerances, shapes,
  halos and trade-offs.
- **Abstractions wait for variation.** An executor, image-source,
  product-sink or compatibility protocol exists because a second
  implementation does; a plugin system, registry or service locator for a
  hypothetical workflow does not.
- **No compatibility shims before 1.0.** `0.x` releases change contracts
  directly and document the break; stale products fail clearly rather than
  being migrated.

## Why performance stays legible

Optimization follows profiles and controlled scale evidence, never
intuition. Clear vectorized NumPy or SciPy comes first; necessary Numba,
buffer-reuse or scheduler-aware complexity sits behind a small typed
interface with the deterministic serial implementation kept as the readable
oracle. An optimization is complete only when the scientific tests, the
affected performance tiers and review pass, and material complexity needs a
design note or ADR saying why the simpler version was insufficient. The
[native-code assessment](native-code-assessment.md) sets the gates for a
compiled extension.

## Enforced gates

| Gate | Mechanism |
| --- | --- |
| Formatting and lint, including import order, complexity, Bugbear and performance idioms | Ruff, in `just check` and pre-commit |
| Zero type diagnostics over `src/` and `tests/` | Pyright strict |
| Normal, boundary and failure tests, written test-first where practical | Review against `CODE_REVIEW.md` |
| At least 80% branch-aware coverage, without weakened assertions or exclusions | `just coverage` and Codecov |
| One contract suite for every executor, store and adapter | `tests/contract/` and the shared executor fixtures |
| Allowed imports stated as one table; Rapthor, Prefect and LSMTool absent; Dask inside `executors/` but for named exemptions; no import-time I/O | `tests/unit/test_architecture.py` |
| Documentation current for public behaviour, configuration and schema changes | Strict MkDocs build |

Coverage is a floor against erosion, not a completeness claim: scientific
oracles, property tests, partition invariance, executor conformance and
controlled qualification remain necessary. Before 1.0.0, a documented
workflow outside Rapthor must use the public API with the serial executor
while constructing no Dask, Prefect, LSMTool or Rapthor object, proving reuse
through the supported boundary.
