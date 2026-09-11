# Phase 5 v13 replacement replay preparation

## Status — 2026-09-11

**Prepared, not execution-admitted; no replay has started.** The approved
[zero-noise adaptive repair](phase-5-zero-noise-adaptive-repair.md) is tested
and frozen. The independent development cost ladder is complete. Host disk
space is below the revised reserve. The exact launch wrapper is implemented
and fixture-tested; the resource record, immutable execution identity and
exhaustive no-write admission remain separate launch gates.
The completed notebook and all historical results remain untouched.

The new write-once metadata is
`benchmark-results/phase-5/public-catalogue-v13-replay-preparation.json`,
SHA-256
`a1c60497ac6a93b86e37460d24a9956a9eb743139481b048e22c47ca5ae8765c`.
Its status is `prepared-not-execution-admitted`, all authorizations are false,
and `execution_identity` is null. This supersedes only the candidate binding
of the [historical v12 preparation](phase-5-v12-replay-preparation.md), not
its evidence or any consumed execution authority.

## Candidate and unchanged scope

- Candidate repair commit: `eacfa6455c750c3bb8c85250669890cc44bc0dac`.
- Preparation source checkout: `9ca9833d20fe616d5b1b92577d926bd0f7b505e6`.
- Candidate-review SHA-256:
  `e93372b5d2787739f7fd1b03024c1bbfe3df6d5fde73e9f6eaedd3eca74f8c5b`.
- Source SHA-256:
  `d5107cd3dca436f802760c96bb3cd8693d7bc000c57283f5cad0b5a05f216b04`.
- Configuration SHA-256:
  `5eca0efc1995f206900506c87f2ca3cba6aa4a2f1a5155bc3e58863bf3cb75c4`.
- Composition v13 SHA-256:
  `0b6844bfd9d17cff7e297fca8cc550e108878180807b8747b3c71065c833f2f8`.

The proposed two-worker replay retains all 2,400 inputs: 800 compact and
1,600 Continuum. It requires 2,400 new current-Hebog Serial captures and
evaluations, 12 new caller-owned existing-Dask comparisons, and byte-for-byte
reuse of 2,400 incumbent, 4,800 dual-PyBDSF and 800 Aegean records. There are
**zero new incumbent or external finder executions**. All 1,187 binding
comparisons, five safety checks, 50,000 bootstrap resamples and seed
`20260810` remain unchanged; underpowered is not pass. Each finder is tested
against analytic/injected truth before like-semantics comparison.

Preparation revalidates the 8,000-record index
`c3fdb6c3ae0e51bbaae1b4f3f46cfe32b5493b2d054ffca080fee26e4db80d25`.
Against historical continuation `b64228d...`, 335 original package,
validation-script and dataset paths and ten native-reader definitions are
unchanged. The 14 changed paths are candidate repairs. The preparation-time
package and validation-script closure has SHA-256
`f6a76a63be262637e2e8bdb7dfa0426a6d13a73a9ec7d6ef2fb4c50012ae7344`.
The subsequently implemented launch wrapper requires a new committed program
closure in the exact execution plan; it does not change the candidate source.
No old current-candidate measurement, Dask verdict or scientific verdict
transfers. The failed R6 terminal remains failed.

The separate exhaustive historical audit completes at 12:34:45 UTC. It verifies
all 2,400 input bundles, 9,600 reference runs, 4,800 native captures, 12
historical Dask comparisons and 10,400 completed finder records, without
finder execution or evaluation. Its record is
`benchmark-results/phase-5/v13-replay-preparation/post-terminal-verification.json`,
SHA-256
`5b95726b47f81743bae1d5cb36fe4751b3549af9f127d212c60776f61f6c5c6b`.
The old terminal `7146f2e8...` retains 885 passes, 288 failures and 14
underpowered comparisons; all five safety checks pass. This historical audit
does not replace the final new immutable execution preflight.

## Independent development cost evidence

Eight independently seeded fixtures each complete one warm-up and five
measured repetitions, on an exact 1,230-file archive of `9ca9833...` with
two workers and one numerical thread per worker. Five fixtures preserve the
full declared geometry, beam/WCS and truth annotations while using disjoint
development seeds. All 158 Continuum endpoint specifications are exercised.
Two denser 1024-square fixtures and the repaired zero-noise 512-square fixture
are capture-only stress cases, not substitutes for annotated evaluation data.

All **48 captures and 30 current-only evaluations** complete in 1,219.16 s.
The terminal SHA-256 is
`f2d4116c241cf1017dbde2652652706cf356a737077f953ddf16f60ab270e666`;
the verified summary at
`benchmark-results/phase-5/v13-runtime-probe-20260911/summary.json` has SHA-256
`bf6bb1be7e4b0f5fc7b9b8441dd041db1c74c88cede62404d186f8a3617fbbd1`.
It retains every repetition, input/program identity, CPU time, logical size,
worker lifetime RSS, median, range and median absolute deviation.

Capture medians are 16.20 s for the 60-component 512-square fixture,
46.89–49.54 s for the four 17-component 1024-square fixtures, 39.50–42.66 s
for the density stress cases, and 60.80 s for the repaired zero-noise case.
The noisy and zero-noise correctness/Serial-Dask evidence remains in the
separate repair review; successful timing execution is not a parity verdict.

The first v13 cost attempt completed all ten captures but failed while
evaluating generic fixtures without the required truth strata/groups. Its
terminal `e9b332ac...` remains preserved. Two intended test failures identify
the probe setup error; four fixture-contract tests pass after correcting only
the development metadata and capture-only classification. No source-finding
or evaluator code, scientific threshold, campaign input or closed result was
changed. This was a probe-setup failure, not a failed scientific replay.

## Resource estimate and remaining gates

Weighting fixture medians by the unchanged population gives 12.55 hours for
capture and 0.48 hours for current-only evaluation at two workers. Retaining
the conservative historical 1.25-hour evaluation, 3.2-hour statistics and
0.5-hour checks/Dask allowances gives **17.50 hours**, or **20.02 hours** with
20% capture headroom. These are planning estimates, not confidence bounds or
a sub-12-hour guarantee. The earlier sub-12-hour request concerned the final
campaign; this replacement regression was separately scoped. Do not silently
promise a deadline or reduce its population, risk geometries or gates.

The projected new capture volume is 31,911,255,200 logical bytes. Keeping
1.5 times the larger of the historical and measured capture volume, plus
2 GiB for records, 3 GiB working space and 20 GiB untouched headroom, raises
the provisional reserve to **74,710,430,800 bytes (69.58 GiB)**. The cost-summary
snapshot observed 59.73 GiB free, about **9.85 GiB short**. The Podman VM had
about 77 GiB free; host space is the limiting reserve. No agent deletion was
performed. Recheck after any user cleanup and immediately before launch.

The proposed scratch
`/private/tmp/hebog-r6-public-catalogue-v13-products-eacfa64` and execution
checkout `/private/tmp/hebog-r6-public-catalogue-v13-replay` remain absent.
The proposed atomic output is `benchmark-results/phase-5/` followed by
`public-catalogue-v13-cumulative-decision.json` inside that future checkout.
Do not call the staged runner directly. Complete the committed program/runtime
execution freeze, exhaustive immutable no-write preflight and
fresh one-use decision under the standing launch authorization first.
The preserved v12 wrapper draft's 68-GiB constant is not sufficient. The new
wrapper and its tests enforce this preparation's 74,710,430,800-byte minimum.

The host is an 18-GiB Apple M3 Pro desktop running Python 3.14.2. Desktop
background activity, affinity and actual native thread-pool census are not
controlled; RSS is a per-worker lifetime high-water mark. No aggregate-stage,
production-scale, matched PyBDSF or complete Rapthor performance claim follows
from this development probe. The 50% complete-filter speedup remains
unmeasured here; optimization and scalability remain later work.

## Exact launch owner

`scripts/validation/source_catalogue_replacement_admission.py` derives the
new plan from the pinned v13 preparation and a separately hashed resource
record. The latter must have `status=resource-admitted`, the exact
`preparation`, `candidate`, `cost_probe` and `runtime`, integer
`required_free_bytes` at least the preparation's minimum, integer
`observed_free_bytes` at least that reserve, and a byte-bound `evidence` list
including the completed cost summary. A historical disk observation alone
cannot pass: available space is checked again before and after the exhaustive
audit. No resource record has yet admitted the real replay.

The plan retains the full census and binding gates, copies no execution
authority and replaces only the current candidate's software/configuration
identity, including its current dependency inventory. Reference identities
are unchanged. Admission verifies the actual imported package belongs to the
immutable checkout, clean revision, package/program hashes, Python/platform/
dependency identity and all five one-thread environment settings. It hashes
Markdown and Python provenance as bytes, not as JSON. Every input, native
reference, capture and reusable row is reverified without finder execution.

The CLI is `python -m scripts.validation.run_source_catalogue_replacement_replay`
from the immutable checkout, with its package import path and reviewed
thread environment. It requires `--plan`, `--plan-sha256`, `--identity-review`
and `--identity-review-sha256`. `--preflight-only` performs the no-write audit
without execution authorization. Actual launch additionally requires
`--authorization` and `--authorization-sha256`, binding a one-use decision
to that exact plan and review. It rechecks these documents after the long
audit, before claiming the new namespace. Missing or changed identities,
insufficient space, symlink/overlapping paths and consumed outputs fail
before capture. A process error propagates without an automatic retry;
a completed scientific failure remains a terminal failure, not success.

The launcher does not itself prepare a resource record, grant authority,
change the candidate, delete data or choose a smaller population. Complete
the reviewed program commit, immutable plan/review/decision freeze and real
exhaustive preflight under adequate resources before using it for the replay.

There are **114 synthetic admission/CLI tests**, with 100% line and branch
coverage of both new wrapper modules (167 statements and 68 branches).
Test-first failures exposed obsolete resource admission, mixed JSON/text
provenance handling, dependency identity and identity drift during preflight.
Tests cover valid admission, changed/consumed identities, insufficient or
changed disk space, namespace isolation and both process/scientific failures.
The real preparation's census and scientific metadata also verify without
finder or evaluator execution. Neither these checks nor the historical audit
substitutes for the exhaustive preflight in the final immutable checkout.

The portable suite passes 3,899 tests, including actual Serial/existing-Dask
integration, with two existing expected failures. Branch-aware project
coverage remains 95.26468995%; all 27 frozen equivalence tests and normal
checks pass. The post-validation host snapshot is 47.59 GiB free, about
21.99 GiB short of the bound minimum. No cleanup or replay was performed.
