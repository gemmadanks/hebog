# Quality attributes and coding principles

Hebog must remain scientifically trustworthy and fast while still being easy
to understand, change, test, and embed. Maintainability, extensibility,
interoperability, and testability are architectural requirements, not later
cleanup tasks.

Rapthor is the first production consumer and defines the initial qualified
feature set. It does not own Hebog's scientific architecture. Other data
pipelines and science workflows should be able to call the public API with
their own inputs, executor, orchestration, and product adapter.

## Dependency direction

Dependencies point towards the scientific core:

```text
data pipeline or science workflow
              |
              v
workflow or compatibility adapter
              |
              v
        public pipeline
          /          \
         v            v
domain records and  narrow ports
scientific algorithms  ^
                       |
                  concrete I/O and
                  executor implementations
```

Scientific algorithms and domain records do not import Rapthor, Prefect,
LSMTool, workflow adapters, or concrete schedulers. They do not read ambient
process configuration or perform import-time I/O. The public pipeline composes
explicit dependencies; compatibility adapters translate external names,
schemas, products, and failure behaviour at the edge.

An executor, image source, product sink, or compatibility protocol is
appropriate when there is a demonstrated alternate implementation. A generic
plugin system, global registry, service locator, or abstraction created only
for a hypothetical future workflow is not.

## Pythonic clean code

Code should make the scientific intent obvious to a Python developer:

- Use descriptive names from the domain glossary and include units,
  coordinates, shapes, or ownership in names and types where ambiguity could
  change a result.
- Prefer cohesive modules, small focused functions, composition, immutable
  dataclasses, context managers, iterators, comprehensions, and structural
  protocols over inheritance hierarchies and generic manager objects.
- Keep one useful level of abstraction in a function. Refactor complex
  branching and unclear parameter lists, but do not fragment a readable
  numerical operation merely to satisfy a metric.
- Make side effects, mutation, resource ownership, and failure behaviour
  explicit. Avoid hidden global state, ambient clients, boolean mode flags,
  and broad exception handling.
- Use comments and docstrings to explain scientific assumptions, units,
  numerical tolerances, array shapes, halos, and non-obvious trade-offs. Do
  not narrate syntax that the code already expresses.
- Remove accidental duplication after the shared concept is understood. A
  few explicit lines are preferable to a clever abstraction that hides the
  science.

Public APIs are deliberately small, typed, documented, and versioned.
Breaking behaviour or schema changes require migration guidance. Public
records remain serializable and must not expose open files, mutable full-image
objects, or scheduler state.

## Performance without opacity

Optimization follows profiles and controlled scale evidence. Prefer clear
vectorized NumPy or SciPy code first. Isolate necessary Numba, low-level,
buffer-reuse, or scheduler-aware complexity behind a small typed interface and
retain the deterministic serial implementation as a readable scientific
oracle.

An optimization is incomplete until focused scientific tests, the relevant
performance tiers, and code review pass. Material architectural complexity
requires a design note or ADR explaining why the simpler implementation was
insufficient.

Do not add a compiled extension pre-emptively. The
[native-code assessment](native-code-assessment.md) keeps NumPy/SciPy and then
Numba as the default path, defines quantitative reconsideration gates, and
compares Rust/PyO3 with C++/pybind11. Any accepted native kernel remains behind
a small typed Python boundary and preserves the readable serial oracle.

## Enforced quality gates

Every code change must satisfy:

- Ruff formatting and linting, including import, Pylint, complexity, Bugbear,
  comprehension, naming, performance-idiom, simplification, and Ruff-specific
  checks;
- zero Pyright diagnostics;
- focused normal, edge, and failure tests written test-first where practical;
- at least 80% branch-aware project coverage, without weakening meaningful
  assertions or excluding difficult production code to preserve the number;
- contract tests for interchangeable executors, storage boundaries, and
  adapters;
- architecture checks that prevent workflow and scheduler dependencies from
  leaking into algorithms and domain records; and
- documentation and migration notes for public behaviour, configuration, or
  schema changes.

Coverage is a floor against erosion, not a completeness claim. Scientific
oracles, property tests, partition invariance, executor conformance, and
controlled qualification remain necessary.

Before `1.0.0`, a documented smoke workflow outside Rapthor must use Hebog's
public API with the serial executor, while its integration code imports or
constructs no Dask, Prefect, LSMTool, or Rapthor objects. This proves reuse
through the supported boundary rather than through internal modules.
