# Hebog implementation plan

Authoritative remaining-work plan. Updated **13 September 2026**.
Current user-facing capability and release policy are in
[release status](../docs/reference/release-status.md); exact campaign
identities, execution history and completed validation belong in
[`LOG.md`](../LOG.md) and the existing evidence records.

## Current state

| Item | Current position |
| --- | --- |
| Candidate | Public composition v18 repairs the custom-threshold/background interaction on top of v17's Gaussian/background repairs. Bounded validation passes; exact commit/freeze is next. The [v17 freeze](../config/contracts/phase-5-background-boundary-repair-identity-review.json) is preserved. Development-unqualified; latest completed campaign remains v15. |
| Implemented | FITS/WCS ingress, background/RMS, compact and multiscale detection, source/component measurement, catalogue/mask/RMS/diagnostics publication, Serial and caller-owned Dask execution, Zarr intermediates. |
| Public envelope | ICRS `Jy/beam` FITS, at most 1,024 pixels on either spatial axis. `continuum` is the default; explicit `compact` is extended-emission-incomplete. Custom thresholds remain unqualified; their private refinement-trigger interaction is repaired in v18. |
| Strongest applicable checks | V18 threshold-boundary controls, 12 new exact Serial/Dask comparisons, six unchanged standard-profile controls, five installed-wheel workflows and 27 frozen equivalence tests pass. Portable coverage passes 4,127 tests at 95.3201%; exact results are in `LOG.md`. No v17/v18 campaign or powered parity verdict. |
| Campaign | Verified v15 terminal: scientific **fail**, 1,115 pass / 32 fail / 40 underpowered comparisons. All five safety checks pass; 2,400 captures/evaluations, 12 exact Dask agreements and 8,000 retained records verified. No definite binding external-reference failure, but parity and incumbent retention are not established. |
| Blockers | The custom-threshold defect is repaired and checked; finish its exact freeze before handoff. Accumulated-branch review, platform CI, separate cleanup and fresh notebook inspection remain before release. Earlier human acceptance of unchanged residual limitations is preserved; scientific qualification, Rapthor acceptance and complete-path performance remain unproven. |
| Next authorized action | Complete the authorized test-first custom-threshold repair below and freeze its exact composition, preserving the standard profile. Resolve supported-platform CI before merge. Then complete a separate bounded cleanup PR and fresh comparison-notebook inspection before the human-controlled release workflow. No automatic replay, closed-data rescoring, publishing or parity claim. |
| Deferred | The human accepted uncertainty-calibration, measurement-tail and faint-association limitations for the v17 experimental standalone release on 13 September. Broader F2 repair, optional improvement, full qualification and facility-scale work remain later tasks. Reopen a deferred issue if it becomes a confirmed incorrect supported output or serious correctness impact. |

The [campaign overview](../docs/reference/phase-5-campaign-overview.md)
explains the current evidence and risks. Earlier compact or continuum passes
qualify their exact candidates only; they do not qualify v17.

## Delivery policy: merge and release small increments

The 12 September user decision replaces large phase-sized release batches
with frequent, useful experimental `0.x` increments. Phase numbers remain
identifiers in frozen evidence and existing tools; they no longer determine
PR or release size.

- **Merge:** a coherent reviewed change with passing applicable tests and
  accurate documentation. A documentation or tooling PR need not wait for
  scientific qualification. The accumulated finder branch needs the terminal
  review below before its development closeout and merge recommendation.
- **Experimental release:** a tested package with explicit unqualified
  science, current limitations and no unresolved confirmed incorrect
  supported output. It need not establish general PyBDSF parity, the complete
  Rapthor speed target or maximum facility scale. Those remain gates for the
  corresponding later claims and supported deployment.
- **Scientific qualification:** candidate-bound parity, quality retention,
  fresh held-out evidence and independent scientific/engineering acceptance.
  An experimental label does not turn a failed or underpowered check into a
  pass or waive a known correctness defect.
- **Rapthor deployment/default cutover:** separately qualified workflow
  behaviour, complete-path performance and operational acceptance, with
  feature-flagged PyBDSF fallback retained until the acceptance matrix passes.

This changes prospective release sequencing, not frozen scientific contracts,
closed decisions or campaign execution authority. No release is being executed
by this planning task. Release Please owns versioning, changelogs and tags;
all task commits stay local for human review and push.

## Before merging the accumulated finder work to main

Each task has an observable completion condition. Agent-owned preparation
continues within existing authority; scientific disposition and final merge
remain human decisions.

- [x] **M1 — Finish and verify the existing v15 campaign.** Normal process exit,
      failed scientific terminal, full provenance/census and exact Dask
      agreement verified. Preserve the terminal byte-for-byte and the original
      failed v14 artifacts. Current summaries and `LOG.md` record the result;
      the completed-run monitor is retired.
- [x] **M2 — Make the bounded severity decision.** Review compact science then
      Continuum, including every failed/underpowered endpoint and known public
      witnesses. Use the existing
      [severity policy](../docs/reference/phase-5-v13-followup-review.md#later-decision-final-campaign-then-development-closeout).
      List each remaining issue, evidence, severity, effect on public outputs,
      release disposition and next task. Close development if no serious issue
      remains; uncertain serious impact needs bounded triage and human
      disposition, not automatic deferral or another full campaign.
      **Accepted 13 September:** the campaign overview accounts for all 72
      non-passing comparisons. The human accepted deferral of the documented
      uncertainty-calibration, measurement-tail and faint-association
      limitations for the v17 experimental standalone release, not as passing
      scientific endpoints. The identified fallback/background
      defects are repaired and the specific position witness resolved at the
      fitting boundary. This closes the bounded severity decision only:
      known correctness defects remain blockers and the acceptance does not
      authorize qualification, publishing or cutover.
- [x] **M3 — Fix the serious defects identified by the bounded M2 review.** For each
      repair, state the cause hypothesis, independent test, expected change
      and stopping condition before implementation. Add a failing regression,
      preserve thresholds/semantics, run affected scientific and Serial/Dask
      checks, and freeze a new candidate where science changes. Carry forward
      only evidence whose identities remain applicable. No full replay follows
      automatically; after two ineffective repairs reassess the diagnosis.
      Mark this task not needed if M2 finds no serious defects.
      **Approved 13 September:** an invalid free Gaussian can
      fall back to a numerically valid but scientifically inadequate unresolved
      beam model. Independently test point versus resolved edge/corner sources,
      require correct or explicitly unavailable Gaussian outputs, preserve
      valid point fits and run public Serial/Dask non-regression. Review any
      new admission rule before promotion; never choose it from closed seeds.
      Diagnose the ten missing high-SNR corner rows separately and retain the
      earlier position witness. Stop at a bounded repaired-candidate handoff;
      another full replay is not automatic. Details and stopping conditions
      are in the campaign overview's correctness inventory.

      **Repair decision:** optimizer convergence/conditioning does not prove
      that an unresolved fallback describes the observed emission. Reuse the
      existing original-pixel, multiscale residual-adequacy rule and nearest
      parent attribution before admitting a beam fallback from an invalid
      free fit, over its actual likelihood support; do not introduce a
      chi-squared cutoff from closed witnesses.
      Independent analytic point/resolved, interior/edge/corner and invalid-
      pixel controls must show that inadequate fallback Gaussians become
      explicitly unavailable while valid fits, detected support and independent
      source photometry remain intact. Keep retained neighbours' parameters
      and covariance from the same joint solution, not interchangeable refits.
      The initial whole-parent rejection failed the open-arc controls: two bad
      fallbacks must not erase three valid resolved neighbours or demand that
      a component explain emission outside its fit domain. Admission is thus
      attributed per component on the unchanged joint model. Stop and reassess
      if those controls fail; do not spend another campaign on an unverified
      hypothesis.

      **Completed Gaussian slice:** v16 is independently tested and frozen
      non-executable at `a716eb3...`; valid point models and independent source
      photometry remain, inadequate fallback Gaussians are explicitly absent.
      Exact public Serial/Dask and notebook workflows pass. Test counts and
      identities are in `LOG.md`. Before any future campaign,
      review the omission/completeness effects in the existing bounded paired
      screen; fixture success is not parity or a guarantee of campaign success.

      **Separate corner-background diagnosis:** saved planes show substantial
      over/under-subtraction, including complete loss of direct support in four
      high-SNR cases. A six-pixel final mesh spacing amplifies small background
      sample errors by extrapolation at the corner. Independently isolate
      coarse/adaptive interpolation and protection; require constant and real
      gradient backgrounds, both noise signs, sources, invalid pixels and
      partition invariance. Preserve real gradients when selecting a stable
      boundary policy. The Gaussian guard does not close this release blocker.

      **Release-clearance repair decision (13 September):** isolate the
      interpolation defect using synthetic coarse samples before involving
      source protection. Keep the existing mesh, statistics and in-grid
      bilinear interpolation. Extend background and extrapolated coarse RMS
      at physical image edges
      using a secant spanning at least the extrapolation distance (or the
      whole available axis if shorter), rather than a nearly duplicate pair
      of edge windows. Reuse NumPy/SciPy; no new interpolator dependency or
      threshold. Expect bounded amplification of independent last-cell errors
      while preserving affine backgrounds exactly on adequately sampled grids.
      Test both signs, coarse/fine meshes, non-square and singleton axes,
      invalid pixels, bounded subsets, actual noisy corner sources and
      Serial/existing-Dask equivalence. Stop and reassess if the public
      background/source controls or existing broad-emission controls regress.
      This is a numerical correctness repair, not evidence of campaign parity.

      **Completed boundary/position slice:** v17 passes both-sign/four-corner
      coarse/fine conditioning tests, real-gradient and bounded-subset
      invariance, short/singleton axes, and four noisy corner scenes with
      exact public Serial/existing-Dask results. Read-only saved-plane analysis
      subsequently isolates the actual twelve excursions to the fine mesh's
      final one-pixel centre spacing; the six-pixel coarse example was a
      related instability, not the exact initiating stage. The specific
      historical displaced Gaussian is now 0.257 rather than 11.970 pixels
      from the peak in one unchanged-pixel diagnostic refit; no detection,
      matching or closed score was repeated. Scope and evidence limits are
      explicit in the campaign overview. No known defect in these bounded
      mechanisms remains open; this is not general scientific qualification.

      **Evidence priority:** assess each finder against analytic/injected
      truth, then compare like semantics with released and pinned-master
      PyBDSF for the functionality Rapthor needs. Previous Hebog is a
      non-regression diagnostic, not the scientific target. This prioritization
      does not erase the v15 incumbent failures, relax frozen comparisons or
      permit known incorrect supported outputs to ship.
- [ ] **M4 — Review the actual merge diff.** Compare the branch to main using
      `CODE_REVIEW.md`; preserve unrelated changes, check public/schema breaks,
      dependencies, packaging and provenance. Keep production changes with
      their tests/docs. Exclude generated evidence and private data. Prefer
      reviewable PRs for independent work; do not split a coherent contract
      change merely to reduce diff size.
      **Local review:** the earlier repair/test/documentation slice had no
      actionable finding. The expanded review at `87b2edc` covers public
      ingress/publication, background refinement, fitting and component/source
      ownership, schema/materialization changes, notebook setup tooling,
      package boundaries and CI. It confirms one **P2 custom-threshold crash**
      below. The accumulated branch has 1,035 changed files; this is not an
      independent line-by-line review of all historical campaign tooling and
      frozen records. Human whole-diff review remains open; the user will also
      obtain Copilot review when opening the PR.

      **Authorized bounded correctness repair, implemented and validated:**
      valid caller thresholds replace the public detection config, but its
      private adaptive bright-work trigger remains 75 sigma. Refinement
      rejects an island threshold at or above that trigger. Independent public
      noise-only reproductions and exact inputs are in `LOG.md`; this is an
      operational public-contract defect, not a failed parity endpoint.
      When the private trigger is not above the caller's island threshold,
      use the caller's already-valid detection threshold for private candidate
      discovery and protection; removing only the guard is insufficient.
      Otherwise retain the private trigger unchanged. Preserve caller
      thresholds and the standard 5/3 profile. Add failing tests around the
      75-sigma boundary and 150-pixel background-policy transition, with empty
      and bright-source controls and exact public Serial/existing-Dask
      agreement. Expect valid custom requests to complete without changing
      standard-profile products. Stop after bounded repair, coverage and
      non-regression checks and any required new candidate record. No full
      replay is needed to diagnose this defect, and no closed result or frozen
      identity is to be rewritten.
      The new public regressions fail at the intended guard before repair and
      pass afterward. Six standard-profile controls retain identical science;
      12 new Serial/existing-Dask comparisons agree byte-for-byte. Coverage,
      frozen equivalence, installed-wheel and normal checks pass; details are
      in `LOG.md`. Finish the non-executable v18 freeze before handoff. This
      closes the identified defect, not the outstanding whole-branch review.
- [ ] **M5 — Validate the exact merge candidate.** Run applicable focused
      tests and `just check`, `just coverage`, `just test-equivalence`,
      `just test-acceptance`, `just marimo-check`, `just docs-build` and
      `just package-smoke-test` (or `just ci`). Inspect changed-line/branch
      coverage and retain the 80% project floor without a coverage regression.
      Require CI's Linux/macOS/Windows × Python 3.12/3.13/3.14 matrix, rather
      than treating local Python 3.14 evidence as the whole platform result.
      Run clean `just pre-commit` immediately before each local commit.
      **Local portion complete:** exact results and patch coverage are in
      `LOG.md`. The acceptance lane has seven expected-failure Rapthor
      scaffolds, not passing deployment scenarios. Local macOS/Python 3.14
      cannot clear the full CI matrix; no push or CI-triggering release action
      is performed by this task.
      **13 September CI repair:** the pre-commit job in
      [run 34765428571](https://github.com/gemmadanks/hebog/actions/runs/34765428571)
      failed on `3806794`; local passing hooks do not override that result.
      The test-only portability repair in `bc0df4c` passes a read-only Linux
      reproduction, independent roundoff/identity controls and local all-file
      hooks. It preserves exact historical bytes and recipes; only regenerated
      truth coordinates allow up to four ULPs. See `LOG.md` for the diagnosis
      and checks. Push and rerun platform CI before clearing M5; no remote
      success is inferred from local validation.
      **Additional CI portability repair:** a full quick run in an output-free
      checkout reproduced 76 failures: 74 retained-evidence dependencies and
      two historical-invocation checks coupled to the current checkout path.
      Separate portable tracked-review contracts from explicit `requires_data`
      artifact checks, retain all historical assertions, and use synthetic
      records for ordinary error/publication tests. Verify historical command
      strings independently of the host path syntax. The repaired clean quick
      lane passes 3,759 tests; four new portable freezer/CLI checks and an
      80-test final affected-file run also pass without campaign outputs.
      Local `just check` passes 3,763 quick tests, lint, formatting and typing;
      full coverage passes 4,069 tests with unchanged 95.3193% branch-aware
      coverage. Exact results and final hook validation are in `LOG.md`.
      No frozen artifact, production source or gate is changed, and no evidence
      is downloaded or regenerated. Supported-platform CI remains outstanding.
- [ ] **M6 — Complete the merge handoff.** Update this plan's current state,
      user-facing release status, API/tutorial limitations and `LOG.md` from
      M1–M5. Give the human the exact revision, checks, unresolved risks and
      recommended merge scope. The human reviews, pushes and merges; a merge
      is not a scientific-readiness assertion or default-backend change.
      **Local handoff prepared:** v17 science is `e39f6c9...`; the separate
      freeze binds its exact source and unchanged configuration. The live
      notebook guard and 35 historical-identity/refresh/notebook tests pass.
      M2 human disposition is now accepted. Final merge clearance waits for
      M4 whole-branch review and M5 platform CI, not another automatic campaign.

M1–M3 are specific to the accumulated finder candidate. Future small changes
use only the applicable checks and evidence; do not rerun this entire campaign
for every documentation edit or release.

Notebook usability is maintained through the
[notebook guide](../docs/how-to/notebooks.md), public-input downloader and CI
execution smoke. Individual exploratory runs do not require reproducibility
locks. Saved comparison refreshes retain their existing evidence-integrity
checks and require separately retained reference products.

The fresh notebook setup preserves all 13 Hydra, LoTSS and SKA SDC1 cases
from the existing comparison and produces
PyBDSF/Aegean reference products using existing adapters and container recipes;
Hebog refresh remains separate. Its dry run is read-only. This increment is
validated with synthetic inputs and mocked network/container execution because
the user reserves disk space for the existing replay. A live build/reference
smoke remains unverified. ProFound or a dedicated SoFiA experiment is optional
follow-up work, not a merge or release gate; see the notebook guide.

## Before the next experimental package release

Target the first useful bounded standalone finder release after the merge
checklist, rather than waiting for Rapthor integration or 100,000-square data.

- [ ] **E0 — Review a separate bounded cleanup PR before release.** Inventory
      candidate dead code and superseded scripts against imports, dynamic
      entry points, notebooks, CI, behavioural tests and retained-evidence
      verification. Delete only demonstrably unused paths; low coverage or
      a historical filename is not sufficient. Keep scientific regressions,
      frozen contracts/decisions and current evidence-verification workflows.
      Record removed paths, replacements and the last containing Git revision;
      Git history supplies recovery without keeping duplicate archived code
      in the live tree. An optional annotated non-release archive tag is a
      human-controlled convenience, not a backup of ignored benchmark data.
      Preserve those products separately. Keep scientific changes, substantial
      refactoring and performance work outside this cleanup PR. Validate with
      applicable coverage, public workflows, Serial/Dask, equivalence,
      installed-wheel, documentation and platform checks. If package or runner
      identity changes, prepare a new candidate record without modifying old
      freezes or transferring qualification automatically.
- [ ] **E1 — Close the bounded release correctness inventory.** Confirm from M2/M3 that
      no known incorrect supported catalogue, position, flux, ownership or
      processing-status output remains. Check Gaussian-validity and
      filtered-response repairs against their independent witnesses. Faint
      association, uncertainty and tail warnings may remain only with a
      reviewed explanation of their statistical/ambiguous nature and current
      limitations; calling a confirmed defect “experimental” is insufficient.
      **Earlier v17 disposition on 13 September:** the
      identified correctness mechanisms are repaired and the human accepts the
      stated residual limitations. Reopen for newly confirmed incorrect
      supported outputs; do not transfer this disposition automatically to
      changed science or a broader deployment claim. **Reopened by M4:** the
      independently reproduced custom-threshold crash is repaired and checked
      in v18. Its exact freeze remains before handoff; the earlier accepted
      statistical limitations and historical science evidence are unchanged.
- [x] **E2 — Confirm the local installed user workflow.** From the release wheel,
      run the documented `find_sources` example and read its four products.
      Cover valid empty/all-NaN inputs, corrupt/unsupported input, custom
      thresholds, compact/continuum selection, unavailable measurements,
      failed publication/retry and caller-owned Dask agreement. Reuse exact
      candidate-bound tests where applicable. Keep the 1,024-pixel guard until
      the larger-image work below qualifies an expanded envelope.
      The isolated wheel now exercises blank/all-NaN, continuum, compact and
      custom-threshold inputs and reads/checks all four products, including
      hashes, run identity, shapes and source/Gaussian availability. Existing
      exact-candidate public tests cover unsupported/corrupt inputs,
      unavailable outputs, publication failure/retry and caller-owned Dask.
      Final release-tag installation and the platform matrix remain E4/M5.
- [ ] **E2a — Refresh and inspect the cleaned release candidate.** After E0,
      commit the candidate, run the existing notebook refresh preflight, then
      refresh the 13 saved public inputs while reusing the retained 26
      PyBDSF/Aegean products. Keep code and runner identity unchanged throughout
      execution; preserve earlier refreshes and verify the completed seal.
      Inspect Gaussian/source positions, unavailable measurements, empty and
      difficult extended regions with the user. Reopen E1 for a newly confirmed
      incorrect supported output; apply the agreed severity policy to existing
      statistical limitations. This is a diagnostic user workflow, not a new
      campaign, rescoring of closed decisions or proof of parity. Larger saved
      notebook images do not expand the public 1,024-pixel release envelope.
      A subsequent science change invalidates the affected inspection.
- [ ] **E3 — Review the release description and generated PR.** State
      “experimental, scientifically unqualified”, the tested input/resource
      envelope, known limitations and all public/schema breaking changes.
      Keep diagnostics' qualification labels accurate. Verify the Release
      Please-generated version, changelog, citation and lockfile changes;
      do not manually prepare them or finalize the old Phase 5 readiness
      packet to manufacture an experimental-release pass.
- [ ] **E4 — Release through the existing workflow.** After main and the
      release PR checks pass, the human reviews and merges the Release Please
      PR and verifies its tag/release plus a clean install of that tag. The
      checked-in workflow manages GitHub releases; it does not define a PyPI
      upload job. Add registry publishing only as a separately scoped task if
      required. Update current release status without copying campaign history
      into the release notes.

No version number is preassigned here. A later fix, measured optimization or
coherent API improvement can repeat E1–E4 and ship its own `0.x` release.

## Subsequent manageable increments

Take one row as a bounded work item; split it further when a measured result
reveals independent changes. Each implementation can merge and release with
its own checks. Qualification and deployment rows authorize only their stated
claim and still need their existing scientific/resource decisions.

| Order | Concrete task | Done when / release opportunity |
| --- | --- | --- |
| Next | Freeze a known-issues runtime baseline and profile complete FITS-to-products execution. | Inputs, candidate, resources and every warm-up/measured run are recorded; CPU/RSS/I/O and task costs identify the first material bottleneck. No speedup or qualification claim from this baseline alone. |
| Next | Remove one measured I/O/copy/materialisation or fit-batching bottleneck. | Paired before/after evidence covers affected and adjacent anchors/crossovers; scientific non-regression and Serial/Dask invariance pass. Ship each useful optimization independently. |
| Next | Complete the shared Serial/local/Dask executor contract and add persistent local threads. | Ordering, serialization, errors, cancellation, retry and resource budgets pass the same contract suite; no nested pools/clusters. Existing Dask execution is extended, not reimplemented as a second abstraction. |
| Next | Remove the public terminal's complete-plane requirement. | Catalogue/measurement and publication operate through bounded Zarr windows/shards and hierarchical summaries; small analytic edge/corner and partition tests agree exactly. Qualify one larger size tier at a time before raising admission limits. |
| Next | Qualify a deployment Zarr store and restart/recovery path. | Atomicity, concurrent owned-chunk writes, codec/chunk geometry, missing chunks, cold/warm throughput and injected failures pass within an admitted memory budget. Publish the tested store envelope. |
| When scientifically prioritized | Resolve one remaining association, uncertainty, RMS/mask or flux-tail mechanism. | Prospective independent controls distinguish the cause; focused public-workflow and paired non-regression checks pass. Preserve source/component distinctions and explicit unavailable outputs. Broader F2 work is deferred unless seriousness changes. |
| Before claiming general scientific readiness | Complete candidate-bound cumulative parity/retention and fresh held-out/public-survey evidence. | Every binding endpoint passes under the reviewed contract; any new population/power design and execution are approved prospectively. Closed failed campaigns are never reused as confirmation. |
| Before claiming general scientific readiness | Replace the stale readiness composition prospectively and obtain independent acceptance. | A new current-candidate packet binds cumulative/fresh evidence, public API, execution/performance checks and separate radio-astronomy/engineering acceptances. Keep the restricted Rapthor profile in its own integration packet; preserve the old frozen record. |
| After general parity/retention | Audit the pinned Rapthor/LSMTool consumer and freeze its workflow profile. | Native catalogue/mask/RMS fields and filtering semantics are exercised on canonical true/apparent, bright, extended, edge, masked, sparse and crowded populations against both PyBDSF references. Choose compact only with ≥99.5% overall agreement and every safety stratum passing; otherwise continuum. |
| Integration increment | Add Rapthor backend selection, restartable true-sky/flat-noise/filter tasks and dual-run reporting. | Acceptance scenarios cover empty/corrupt input, restart, retry, backend selection and PyBDSF fallback. Concurrent branches respect the caller's resource budget. Keep the feature flag and remove the subprocess escape only from the Hebog path. |
| Before supported Rapthor deployment | Run matched complete `filter_skymodel` benchmarks and operational acceptance. | Both runtime confidence gates below pass across the frozen initial supported envelope; science, profile, retry/resume and memory gates pass. Bind the integration readiness packet and retain fallback outside the admitted envelope. A Rapthor-integrated experimental release can follow. |
| Before each scale claim | Qualify the next size/topology and extend complete-path benchmarks. | Add 30,000 then 100,000-square anchors, both sides of new crossovers, deployment storage and recovery. Prove invariance at 1, 10, 50, 100 and at least 200 workers with admitted node/worker resources. Small-machine evidence does not establish facility support. |
| Before default cutover / 1.0 | Complete operational soak and production review. | Full scientific/compatibility and performance matrix, 100,000-square facility gates, portability, security/licensing, packaging, current docs and independent acceptance pass. Native code, if added, also needs its complete wheel/safety/fallback matrix. |

## Scientific gates retained

Analytic/injected truth is primary. Released PyBDSF is the Rapthor compatibility
reference; pinned PyBDSF `master` is independently binding. Aegean is binding
for applicable compact/Gaussian populations. No finder is scientific truth.

- Use the exact candidate's reviewed endpoint registry, decision contract and
  activation/amendment records in `config/contracts/`. The
  [prospective registry](../config/contracts/phase-5-prospective-science-endpoint-registry.json)
  defines 383 endpoints and 1,187 co-primary comparisons. Do not confuse the
  original inactive freeze with later separately authorized executions.
- Require every applicable relative PyBDSF, Aegean and single-incumbent Hebog
  comparison. Choose a whole incumbent before viewing results; do not combine
  historical best values into a synthetic comparator. Retain fixed practical
  margins and the conjunctive one-sided confidence rule. Inconclusive binding
  evidence is not parity. An old candidate's uncertainty exception does not
  transfer to a replacement.
- Freeze population, semantic applicability, independent sampling unit,
  margins, missing-output rules and endpoint/joint power before execution.
  Pair and resample whole realizations, not dependent source rows or pixels.
  Planning variance sizes the study; the observed-data confidence interval
  decides non-inferiority. Separate superiority claims need a prospective
  multiplicity rule; improvements cannot compensate for failed binding checks.
- Longer-term absolute targets remain reported under the prospective policy.
  Product validity, finite/explicitly unavailable measurements, complete
  processing status, schemas/provenance and deterministic execution remain
  binding. Retain all morphology, scale, SNR, noise and boundary strata.
- Compare like source/component/support semantics; use original pixels for
  flux and photometry, valid pixels for mask precision/recall/IoU, and report
  splits, merges, duplicates and low-SNR completeness/reliability separately.
- Run an explicitly budgeted public finder/capture/read/evaluate/aggregate
  development screen before any long replacement campaign. Include ordinary,
  empty, failure-mechanism and numerical/invalid-pixel controls plus existing
  Dask agreement. Reuse verified applicable evidence. A small clean screen is
  neither powered parity nor a probability of campaign success.

The dataset matrix retains compact SNR 3–100, blends, diffuse Gaussians,
filaments/shells, mixed emission, different beams/WCS/pixel scales/units,
negative backgrounds, empty/all-NaN/invalid data, varying noise, edges and all
tile-edge/corner topologies. Every dataset has a development, regression or
qualification role, provenance/checksums and generator identity. General
qualification includes public/challenge cut-outs from at least two telescope
families. Tests compare Serial before alternate executors and external finders.

The durable cross-project targets remain unchanged. Under the prospective
science policy, absolute improvement targets are reported separately from
binding relative/validity gates; the Rapthor profile has its own agreement
and safety requirements. Exact campaign populations and margins stay in the
frozen contracts.

| Measurement | Target |
| --- | --- |
| Rapthor retained/rejected components | ≥99.5% agreement |
| Reference recovery, SNR ≥10 | ≥99% |
| SNR ≥5 | Report the compatibility curve; no single pass fraction |
| False-discovery rate | ≤1 percentage point above reference |
| Isolated SNR ≥10 position difference, median / p95 | ≤0.02 / 0.10 beam |
| Isolated SNR ≥10 peak-flux difference, median / p95 | ≤2% / 5% |
| Isolated SNR ≥10 integrated-flux difference, median / p95 | ≤5% / 10% |
| Source-free RMS-map difference, median / p95 | ≤2% / 5% |

## Performance and scale gates retained

For supported Rapthor deployment, matched complete-step median ratios and
their upper one-sided 95% bootstrap confidence bounds must satisfy:

```text
Hebog / released PyBDSF <= 0.50
Hebog / pinned PyBDSF master < 1.00
```

Scientific eligibility precedes acceptance of performance. These are minimum
deployment gates, not a reason to stop optimization or hold an unqualified
standalone development release until Rapthor integration exists.

- Maintain 256, 512, 1,024, 3,000, 8,000, 10,000, 30,000 and 100,000-square
  anchors, sparse/normal/dense-extended workloads and both sides of every
  measured crossover. Gate early deployment on its explicitly frozen envelope;
  full facility/1.0 qualification needs the whole matrix.
- Match inputs/checksums, revisions/dependencies, output mode, host, affinity,
  CPU/native threads, workers, memory, storage and cache policy. Use warm-up
  plus at least five measured repetitions, retain all values, medians and
  dispersion, and avoid unrelated workloads.
- Record wall/CPU time, worker/aggregate RSS, I/O, task/graph size, transfers,
  spill, failures/retries, tile/halo geometry, boundary summaries, occupancy,
  scheduler load, throughput and headroom. Scale evidence adds reduction depth,
  stragglers and strong/weak efficiency. Unavailable instrumentation needs a
  reason, not zero. Use versioned `hebog.validation.evidence` records.
- Hebog non-regression needs an upper one-sided 95% bound ≤1.05 against the
  previous reviewed curve. A lower bound >1.05 is a regression; crossing the
  margin is inconclusive. A >10% peak worker/aggregate memory regression
  against either PyBDSF reference needs an approved throughput trade-off.
- Existing 3,000-square component budgets remain diagnostic, including the
  four-core 6-second multiscale budget; complete filtering decides deployment.
  Exact resource/runtime/efficiency budgets remain in the
  [performance and scalability contracts](../docs/reference/performance-scalability-contracts.md).

## Architecture and documentation boundaries

Keep the scientific library pipeline-neutral with inert imports, small typed
requests/results and no implicit clients, clusters or pools. Maintain Serial
as the oracle, Zarr as the sole intermediate plane backend, stage-specific
halos/global ownership and hierarchical reductions. Never raise the public
size limit by sending a complete large plane to one worker. Preserve dtype
unless scientific evidence supports a change. Prefer established libraries,
NumPy/SciPy, then profiled Numba; new native code needs the reviewed ADR,
10% profile / 2× kernel / 5% end-to-end gates and portable distribution.
The [architecture](../docs/architecture/index.md),
[native assessment](../docs/explanation/native-code-assessment.md) and
[`AGENTS.md`](../AGENTS.md) retain the detailed requirements.

Keep README, docs home, release status and the public tutorial focused on
current behaviour. Replace stale summaries when status changes. Keep dated
reviews/immutable contracts in the evidence reference section and link to
`LOG.md` or Git for chronology; do not append another “latest snapshot” to
user guidance. Removing a historical narrative never changes a closed result.
