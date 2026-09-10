# Phase 5 v12 replacement replay preparation

## Status — 2026-09-10

**Prepared, not execution-admitted and not started.** The user requested
preparation while independently refreshing the notebook. Package science,
the notebook runner, public identity reviews and refresh outputs were not
changed. No finder, replay, qualification, rescoring or cleanup was started
by this preparation. No execution decision or monitor was created.

This supersedes the candidate binding in the
[v11 preparation](phase-5-v11-replay-preparation.md), not its historical
evidence. The [noiseless-filter repair](phase-5-noiseless-filter-repair.md)
remains frozen and unqualified.

## Exact preparation

- Candidate: `ed5136af4b0948ff48e7ebb8311ce192f17c76cf`.
- Source SHA-256:
  `838e28460525259e7a8879ecf97f352a979754b887a5423ff3a59ecb5b3f7f27`.
- Configuration SHA-256:
  `5eca0efc1995f206900506c87f2ca3cba6aa4a2f1a5155bc3e58863bf3cb75c4`.
- Non-executable candidate-review SHA-256:
  `2ab9d43330e7e8af3f7c426aa272180a391f6437a287f91851747106d2db5096`.
- Committed preparation code: `97dc43e969d7ac0a626439c0aeca1d195cc59348`.

The ignored, write-once metadata snapshot is
`benchmark-results/phase-5/public-catalogue-v12-replay-preparation.json`,
SHA-256
`4d70e746cee657061fdb10feff8788bfd367a73832114cb156a55c900a55f149`.
It contains the 2,400 proposed tasks, comparator inventory, code/runtime
bindings and unresolved admission gates. Its status is
`prepared-not-execution-admitted`, all authorizations are false and
`execution_identity` is null. It is **not a launch plan or approval**.

| Planned work | Count |
| --- | ---: |
| New current-Hebog Serial captures and evaluations | 2,400 |
| New caller-owned existing-Dask comparisons | 12 |
| Reused incumbent records | 2,400 |
| Reused released/master PyBDSF records | 4,800 |
| Reused Aegean records | 800 |
| New incumbent/PyBDSF/Aegean executions | 0 |

The two-worker budget, 800 compact and 1,600 Continuum inputs, 1,187 binding
comparisons, five safety checks, 50,000 bootstrap resamples and seed
`20260810` are unchanged. Each finder is independently measured against
analytic/injected truth; PyBDSF is not truth. Every required comparison and
safety check must pass. Neither old current-candidate measurements nor old
Dask verdicts, scientific verdicts or uncertainty acceptance transfer.

The proposed scratch directory
`/private/tmp/hebog-r6-public-catalogue-v12-products-ed5136a` and execution
checkout `/private/tmp/hebog-r6-public-catalogue-v12-replay` remain absent.
The staged runner still has no command-line launch entry point. Its stale
v11 terminal label was made candidate-neutral without changing its exact
candidate binding, control flow or scientific calculations.

## Provenance and validation

The immutable historical verifier finished successfully at 19:44:38 UTC.
It checked all 2,400 input bundles, 9,600 retained reference runs, 2,400
native current/incumbent capture pairs, 12 historical Dask comparisons and
10,400 completed per-finder evaluation records. It ran no finder or
evaluator. The historical R6 terminal remains unchanged: **885 passes,
288 failures and 14 underpowered comparisons**, with all five safety checks
passing. Verification does not convert that scientific failure into a pass.

The 8,000 reusable-record index remains SHA-256
`c3fdb6c3ae0e51bbaae1b4f3f46cfe32b5493b2d054ffca080fee26e4db80d25`.
Against historical continuation commit `b64228d...`, 335 original code/data
paths are byte-identical. The 14 changed paths are candidate repairs,
including the v12 numerical filter repair; historical evaluator scripts and
dataset bytes remain intact. All ten native reference-reader definitions
in `products.py` are unchanged. The snapshot binds the complete current
package/validation program set separately.

Audit output and preparation/verifier scripts are retained under ignored
`benchmark-results/phase-5/v12-replay-preparation/`.
`post-terminal-verification.json` has SHA-256
`93e22734732ac2ba55c041036824dca64f68ed6c0f798ef4708d94de15c03f5a`.

The preparation-only change passes 40 focused tests with all 143 executable
lines and 36 branches covered across the three replacement-tooling modules.
`just check` passes Ruff, Pyright and 3,471 tests, with two expected failures.
Strict documentation and all-file hooks pass before the tooling commit.
Full scientific coverage/equivalence were not rerun for a literal/docstring
change; the candidate's earlier frozen repair evidence remains separate.

## Before any launch

1. Finish the notebook refresh, then measure the remaining representative
   independent cost/size fixtures, including the precision-limited spatial
   filter. Concurrent notebook timings cannot admit replay runtime.
   The quick probe is not a proven 12-hour bound or a PyBDSF speedup result.
2. Recheck host/Podman resources and disk. This snapshot observes **69.42 GiB
   free**, only **1.42 GiB above** the provisional 68 GiB requirement.
   Notebook growth and the unfinished cost/size ladder prevent treating this
   small margin as final resource admission. No deletion was performed.
3. Complete and test the exact execution owner, freeze its committed program
   closure, runtime, immutable checkout and fresh write-once paths, then run
   exhaustive no-write launch validation. Do not call the staged runner
   directly or reuse a historical consumed decision.
4. Resolve exact launch authority separately. The user's instruction remains
   **prepare, do not start**. No candidate run or scientific success follows
   from fixture tests or this preparation record.

Scalability and performance optimization remain later work. Scientific
thresholds, catalogue semantics and risk geometries must not be reduced to
meet a runtime estimate.
