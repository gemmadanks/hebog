# Phase 5 v11 replacement replay preparation

## Follow-up — numerical repair supersedes the candidate binding

The user subsequently authorized fixing the exposed noiseless-fixture bug.
The [v12 numerical repair](phase-5-noiseless-filter-repair.md) makes the exact
reproducer pass without an xfail. The notebook refresh has finished. The
record below describes the earlier v11 preparation and observed disk state;
its metadata snapshot remains unchanged and is not executable authority.
Rebind the repaired candidate, measure its cost/space requirements and repeat
final no-write admission before any separately authorized launch. No replay
or cleanup was performed by the repair.

The subsequent [v12 preparation](phase-5-v12-replay-preparation.md) completes
the metadata rebinding and historical audit while a new notebook refresh
runs. It remains non-executable; use that page for the current admission
status and disk observation. The v11 record and observations below are
historical, not current launch instructions.

## Status — 2026-09-10

Prepared, **not execution-admitted and not started**. The user explicitly
requested preparation only. No execution decision, monitor, candidate or
reference campaign run, rescoring, qualification or deletion was performed.
Package science and both notebook runner scripts remain unchanged.

The current candidate is `ee8303519feab359e11f70ee1debfafd00d34177`, bound by
the non-executable catalogue-correctness review SHA-256
`dc811fb8b2d1ad51969579de0dcae7956a760a56a527eb6fcda8ea6acc2f4d2a`.
Source SHA-256 is
`f708bd54b8abc9de07cb5335271aba5528f4627e58a31f81d97a4b9808a48bc4`;
composition is v11, diagnostics schema 8, and configuration remains
`5eca0efc1995f206900506c87f2ca3cba6aa4a2f1a5155bc3e58863bf3cb75c4`.

### Prepared work

The new `source_catalogue_replacement_execution.py`,
`source_catalogue_replacement_inventory.py` and
`source_catalogue_replacement_runner.py` modules under `scripts/validation/`
reuse existing capture, truth-measurement, process-pool, Dask and aggregate
functions. They do not introduce a second scientific evaluator. The staged
runner has **no command-line launch entry point**; an exact admitted owner
wrapper remains necessary before execution.

| Work | Count |
| --- | ---: |
| New current-Hebog Serial captures and evaluations | 2,400 |
| New caller-owned existing-Dask comparisons | 12 |
| Reused incumbent records | 2,400 |
| Reused released/master PyBDSF records | 4,800 |
| Reused Aegean records | 800 |
| New incumbent/PyBDSF/Aegean executions | 0 |
| Final combined per-finder records | 10,400 |

Two spawned workers remain the process budget. All 800 compact and 1,600
Continuum inputs, 1,187 binding comparisons, five safety checks, 50,000
bootstrap resamples and seed `20260810` remain unchanged. Each finder is
measured independently against analytic/injected truth. Old current-Hebog
records, old Dask comparisons, old verdicts and the earlier uncertainty
acceptance do not transfer.

Current captures, current evaluations and the combined evaluation inventory
have separate write-once seals. Reuse requires exact input/finder census,
record hashes, schema, lane and capture links. Missing, duplicated, foreign
or changed records fail closed. Late process failures preserve completed
stages; a completed scientific failure is still a terminal result.

The ignored metadata record
`benchmark-results/phase-5/public-catalogue-v11-replay-preparation.json`
(SHA-256
`4c3b8d0ce85b42c39993f9da63528e938ad585164fd4b5c952eda1a04601cbb6`)
contains all proposed tasks, comparator bindings, runtime and code snapshot.
It is a preparation record, **not an exact executable identity**. Its proposed
scratch and immutable execution directories have not been created. A later
science repair requires a new candidate binding and execution freeze.

### Evidence verification

The historical immutable post-terminal verifier completed again at
08:31:34 UTC on 2026-09-10, with exit status zero. It verified all 2,400 input
bundles, 9,600 reference runs, 2,400 native current/incumbent capture pairs,
12 historical Dask comparisons and 10,400 completed evaluation records. It
did not run an evaluator or finder. The old terminal remains SHA-256
`7146f2e857c9473117c16d29f5bd8d55a2790c66d1c1643cd79b96aa8cc51d72`,
with 885 passes, 288 failures and 14 underpowered comparisons; it has not
become a scientific pass.

The 8,000 reusable records were read and verified again. The canonical
`input_id,finder_id,path,sha256` index remains
`c3fdb6c3ae0e51bbaae1b4f3f46cfe32b5493b2d054ffca080fee26e4db80d25`.
Across the original package, validation scripts and dataset files, 336 paths
are byte-identical to continuation commit `b64228d...`. The 13 changed package
paths are the already-reviewed candidate repairs; no old evaluator script or
dataset changed. The ten native reference-reader definitions in the mixed
`products.py` module are unchanged. These checks support comparator reuse;
they do not establish new-candidate parity or replace execution admission.

### Admission blockers

1. **New noiseless-image edge case.** A synthetic exact public capture of the
   first adaptive development geometry, with its analytic signal but no
   added noise, raises
   `ValueError: significant scale features require finite positive response`.
   The path is source-protected adaptive background estimation through
   `persistent_seeded_scale_support` into `build_scale_detection_plane`.
   A bounded diagnostic confirms finite SNR/response arrays but spurious
   significant-scale features with zero or negative original-residual maxima;
   reported local scale SNRs reach approximately `1e56`. The upstream
   near-zero-noise calibration and filtered-support admission still need a
   unit-invariant repair design, not an arbitrary tuned RMS floor. The noisy
   version passes. This is not a campaign observation or a reason
   to alter campaign thresholds. Preserve the strict expected-failure test
   `test_noiseless_public_capture_has_finite_scale_response` until a reviewed
   repair makes it pass normally. Do not treat that xfail as a passed gate.
2. **Controlled cost/size probe.** The user's notebook refresh is active.
   Fixture timings collected concurrently cannot admit runtime or establish
   a sub-12-hour campaign bound. Run the representative independent ladder
   after the workload is quiet and the correctness repair is validated.
3. **Disk.** About 49 GiB is currently free against the provisional 68 GiB
   requirement. Re-measure after cleanup and the notebook refresh; the cost
   probe may revise the requirement. The earlier 9–14-hour estimate is not
   a guarantee.
4. **Exact execution freeze and exhaustive no-write admission.** Bind the
   repaired candidate, final committed owner/worker closure, runtime, reusable
   inventory, immutable checkout and fresh write-once paths. Validate before
   issuing a new exact one-use decision. Do not call the staged runner
   directly or reuse any consumed historical decision.

The new orchestration passes 40 focused tests with all 143 executable lines
and all 36 coverage branches covered. Two noisy end-to-end fixture tests
exercise actual public capture with two spawned workers, current-only truth
evaluation, immutable record recombination and exact Serial/existing-Dask
agreement. Those small fixtures use applicable overall endpoints; the full
campaign retains all 158 Continuum specifications. The new noiseless test
is a strict xfail and an explicit unresolved admission blocker, not evidence
that all scientific fixtures pass.

Final validation on Python 3.14.2: `just coverage` passes 3,743 tests with
three expected failures (including the new blocker), with 95.2547% project
coverage, up from 95.2378%. `just check` passes 3,449 tests plus Ruff and
Pyright; all 27 frozen equivalence tests and strict documentation builds
pass. No controlled timing or Python 3.12/3.13 validation was performed.

## Disk cleanup recommendations

No files were deleted. Sizes below are allocated disk space observed on
2026-09-10, expressed in GiB. Prefer an external, checksum-verified archive for
historical scientific outputs; moving them elsewhere on the same disk does
not free space. Git does not contain these ignored results.

### First candidates

- **Abandoned notebook staging: about 1.85 GiB.** Under
  `benchmark-results/phase-5/hebog-notebook-refreshes/`, the old directories
  `.16aef34-3fc5d4c72e54-440f1c70.staging`,
  `.966d6b8-bb061e9cc5f5-a0c1776e.staging`,
  `.4957025-c1fb96c4cfce-6091aef8.staging` and
  `.11d70cf-d0625e195412-8fa23453.staging` are not the active refresh.
  They are candidates to remove if their failed partial outputs are no longer
  wanted; otherwise archive their request/failure records and products first.
  Do not remove all `.staging` directories with a wildcard.
- **Older completed notebook snapshots: about 6.0 GiB in four directories.**
  In the same parent, consider externally archiving
  `cb02de5-9a5191bc8426`, `cb02de5-517d56e19a5d-c8443bfb`,
  `707478c-11307db00597-440f1c70` and
  `e265c5b-9f8e4a67f0c7-440f1c70`. Preserve manifests and hashes. These are
  registered in `index.json`: removing them leaves unavailable history
  selections unless the index is deliberately maintained. Do not edit that
  index while the refresh may be publishing. Keep the newest refresh and
  the catalogue-repair witnesses locally until the repair review is closed.
- **Downloaded archives: about 9.66 GiB.** Under
  `benchmark-results/phase-5/public-comparison-acquisition/raw/`,
  `emu_pilot_sample_2x2deg.hydra.tar.gz` is about 9.29 GiB and
  `SDC1_submissions.tgz` about 0.37 GiB. These archives are not inputs to the
  replacement replay, which uses retained bundles. Archive them externally
  rather than removing the whole `raw/` directory. Keep `acquisition.json`
  and all raw FITS inputs. Future acquisition/schema/population checks verify
  all seven downloaded artifacts and will require these archives restored
  byte-for-byte.
- **Small reproducible outputs:** `site/` is about 18 MiB, caches
  `.pytest_cache/`, `.ruff_cache/`, `.hypothesis/` total about 6 MiB, and
  `/private/tmp/hebog-r5-public-background-fixtures/` is about 225 MiB of
  generated development fixtures. These are lower-value cleanup targets and
  will not solve the disk shortfall alone. Do not remove test caches during
  active validation.

The first three groups total about 17.5 GiB, slightly less than the current
19 GiB shortfall. Aim for at least 20 GiB of extra space, preferably 25 GiB
while the notebook refresh is still growing and the replay budget is
provisional. These candidates alone therefore do not establish disk
admission. Choose only snapshots/partials whose local loss is acceptable.

### Keep in place

- `benchmark-results/phase-5/viewed-reference-reconstruction-public-finder-correction/`
  — about **97.8 GiB**, containing the replay input and retained reference
  bundles.
- `/private/tmp/hebog-r6-cumulative-products-db8936b/` — about **36.9 GiB**,
  containing the saved captures and reusable observations.
- `/private/tmp/hebog-r6-evaluation-continuation-products-b64228d/` — about
  **0.46 GiB**, containing the completed continuation records.
- Immutable execution/incumbent checkouts, seals, terminals and reconstruction
  records. They are small compared with the data and bind its provenance.
- The active notebook directory
  `.ee83035-f708bd54b8ab-c9b0fec5.staging`, the `latest` target (currently
  `390efa7-cc1db52e4e30-4f8f357a`), and the still-needed repair witnesses
  `766f896-c2398c10709a-3a5dd0cb` and `a91825a-8da21e86afc5-8aca6683`.
- Raw FITS images, notebook input/reference campaigns, `.venv/`, `.git/` and
  tracked source/configuration/documentation. Removing `.venv/` before replay
  admission would also discard the runtime being verified.

Do not recursively remove `benchmark-results/`, `/private/tmp/`, or the
whole notebook history. Broad historical-tooling cleanup remains Phase 5.5.
