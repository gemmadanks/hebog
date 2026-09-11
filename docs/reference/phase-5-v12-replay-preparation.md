# Phase 5 v12 replacement replay preparation

## Status — 2026-09-11

**Historical preparation; launch held pending new v13 execution admission.**
The [v13 preparation](phase-5-v13-replay-preparation.md) and independent cost
ladder are now complete. Disk headroom and exact-owner/final preflight gates
remain open; this historical record is not current launch authority.
The independent candidate fixture failure is repaired and a separate v13
candidate is frozen. No replay has started. The user initially
requested preparation while independently refreshing the notebook. Package science,
the notebook runner, public identity reviews and refresh outputs were not
changed. No finder, replay, qualification, rescoring or cleanup was started
by that preparation, and it issued no execution decision.

The later 2026-09-10 instruction authorizes hourly monitoring of the active
refresh, followed by the isolated replay, evaluation and investigation of
failures, including process/evaluator repairs and retries. Active hourly
monitor `monitor-notebook-then-v12-replay` requires the exact refresh's
successful sealed publication before completing admission and launching.
That refresh completed at **22:59:52 UTC on 2026-09-10**. All 13 successful
result hashes, 104 unique artifact hashes/sizes, 13 input records, exact
source/configuration/composition/runner bindings and published history verify.
Terminal `76e4a31-838e28460525-5f17c3d7/campaign.json` under
`benchmark-results/phase-5/hebog-notebook-refreshes/` has SHA-256
`905475f76782be1ae9285d27ec8e08fac021e6b15ec8fa28852daf976393b929`.
The first post-refresh check observed **66.747 GiB free**, **1.253 GiB below**
the provisional 68 GiB requirement. The user's subsequent cleanup raised
available space to approximately **89.9 GiB**; the disk hold is cleared.
Admission then exposed the development failure described below. The same
hourly monitor now holds launch for the new preparation and execution admission.
No agent cleanup or replay has started. Diagnostic completion is not a parity
result.
The immutable preparation metadata below is not amended into an executable
record. A fresh exact execution decision is still required under this
authorization; historical consumed decisions remain unusable.

This supersedes the candidate binding in the
[v11 preparation](phase-5-v11-replay-preparation.md), not its historical
evidence. The [noiseless-filter repair](phase-5-noiseless-filter-repair.md)
remains frozen and unqualified.

## New admission failure — 2026-09-11

The remaining independent cost ladder added two 26-component 1024-square
fields and a zero-noise, two-component 512-square field, with disjoint
development seeds `2026981101`--`2026981103`. The precision fixture failed
during its first capture with
`ValueError: adaptive candidate is absent from source-protection support`.
A bounded diagnostic reproduction fails identically in the frozen source
`838e2846...`; neither attempt is a replay or a scientific parity verdict.
No complete timing ladder or new runtime bound was obtained.

The failing image has 262,144 finite pixels. In contrast, the adaptive
source-protection window `y=[0,191), x=[0,191)` has **zero scientifically
valid normalized pixels**; its old candidate anchor `(y=47, x=45)` is invalid
with normalized value `NaN`. `_connected_source_protection` nevertheless
requires that anchor to belong to a thresholded connected component and
raises. This confirms an availability/anchor mismatch on the public capture
path. A subsequent approved diagnostic trace confirms that all six-by-six
protected coarse samples have exactly zero RMS and background: source
protection leaves a defined zero-variance statistic, not missing image
data. See the separate [zero-noise adaptive repair](phase-5-zero-noise-adaptive-repair.md).
This diagnosis does not justify an RMS floor or weakening the anchor guard.

The recipe, FITS input, failed products and diagnostic record remain under
`/private/tmp/hebog-v12-runtime-probe.WYsfaC/` in
`admission-cost-products-20260911-b/precision-512/`.
`failure-diagnosis.json` SHA-256 is
`3c873ad982026276bb959464d8df888155132868e9294343516ae82d2c25567f`.
The agent's incomplete launch-owner prototype is preserved as text under
ignored `benchmark-results/phase-5/v12-replay-preparation/launch-owner-draft/`;
24 focused prototype tests passed, but its full admission/CLI tests and
validation are unfinished. It is not executable supported tooling.

**Repair/freeze complete:** the approved v13 repair passes the exact
regression, ordinary-noise non-regression and Serial/existing-Dask checks.
The new non-executable review `e93372b5...` binds candidate `eacfa64...`,
source `d5107cd3...` and composition `0b6844bf...`; configuration is unchanged.
No RMS floor, threshold change or weakened anchor guard is introduced.
Unavailable RMS remains explicit, not a claim of scientific non-detection.
**Next:** create new preparation for v13 and complete cost, resource and exact
execution-owner admission, including exhaustive retained-record verification.
Process/evaluator retry authority alone does not authorize further candidate
science changes. The historical v12 identity and every closed result remain
immutable; do not launch this old preparation.

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

1. Resolve the candidate admission failure above through an approved
   test-first repair and a new candidate/preparation freeze. The notebook
   completion gate is satisfied. Then measure the remaining
   representative independent cost/size fixtures, including the
   precision-limited spatial filter. Concurrent notebook timings cannot
   admit replay runtime.
   The quick probe is not a proven 12-hour bound or a PyBDSF speedup result.
2. Recheck host/Podman resources and disk. The latest check after user cleanup
   finds approximately **89.9 GiB**, above the provisional **68 GiB**
   requirement. Crossing that number alone does not replace the unfinished
   cost/size ladder or final admission. No agent deletion was performed.
3. Complete and test the exact execution owner, freeze its committed program
   closure, runtime, immutable checkout and fresh write-once paths, then run
   exhaustive no-write launch validation. Do not call the staged runner
   directly or reuse a historical consumed decision.
4. Record the fresh exact one-use execution decision under the user's later
   launch authorization, then launch and bind the actual session and hashes
   into the same hourly monitor. Preserve failed attempts; process/evaluator
   repairs and retries require tests and newly frozen identities/namespaces.
   Investigate completed scientific failures without tuning or rescoring.
   No candidate run or scientific success follows from fixture tests or this
   preparation record alone. Fresh qualification is not part of this monitor.

Scalability and performance optimization remain later work. Scientific
thresholds, catalogue semantics and risk geometries must not be reduced to
meet a runtime estimate.
