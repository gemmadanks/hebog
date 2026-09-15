# Hebog implementation plan

Authoritative remaining-work plan. Updated **15 September 2026**.
Current user-facing capability is in
[release status](../docs/reference/release-status.md); execution history,
evidence identities and completed decisions are in [`LOG.md`](../LOG.md).
Closed Phase 5 contracts, reviews and campaign tooling are in Git history at
`4babf0b`.

## Current state

| Item | Current position |
| --- | --- |
| Candidate | Public composition v19 on `main`, with its runtime extracted into `hebog.science` (#52). Development-unqualified. |
| Implemented | FITS/WCS ingress, background/RMS, compact and multiscale detection, source/component measurement, catalogue/mask/RMS/diagnostics publication, Serial and caller-owned Dask execution, Zarr intermediates. |
| Public envelope | ICRS `Jy/beam` FITS, at most 1,024 pixels on either spatial axis. `continuum` is the default; explicit `compact` is extended-emission-incomplete. Custom thresholds are unqualified. |
| Strongest evidence | The latest completed campaign (v15) is a scientific **fail**: 1,115 pass, 32 fail and 40 underpowered comparisons, with no definite binding external-reference failure. The later v16–v18 repairs and v19 have focused regression, Serial/Dask, equivalence and installed-wheel evidence only. The [campaign overview](../docs/reference/phase-5-campaign-overview.md) holds the conclusions and non-passing inventory. |
| Accepted limitations | On 13 September the human accepted uncertainty calibration, measurement tails and faint association as documented limitations of an experimental standalone release. They are not passing endpoints. |
| Blockers | v0.7.0 needs the PR 3 cleanup merged, hosted CI across the supported matrix and the release checklist below. General scientific readiness, Rapthor acceptance and complete-path performance remain unproven. |
| Next action | Review and merge PR 3 (`chore-cleanup-phase-5-closed-campaigns`), then prepare the v0.7.0 release-readiness branch. |
| Deferred | Broader F2 association repair, further scientific improvement, general qualification, Rapthor integration and facility-scale work. Reopen a deferred issue if it becomes a confirmed incorrect supported output. |

## Delivery policy

Ship frequent, useful experimental `0.x` increments rather than phase-sized
batches. Phase numbers survive only as historical identifiers.

- **Merge:** a coherent reviewed change with passing applicable tests and
  accurate documentation. Tooling and documentation changes need not wait for
  scientific qualification. Merge each PR in a sequence before branching the
  next, so CI isolates the responsible change.
- **Experimental release:** a tested package that states its unqualified
  science and current limitations and has no unresolved confirmed incorrect
  supported output. It need not establish general PyBDSF parity, the Rapthor
  speed target or facility scale.
- **Scientific qualification:** candidate-bound parity and quality retention,
  fresh held-out evidence and independent scientific and engineering
  acceptance. An experimental label never turns a failed or underpowered check
  into a pass.
- **Rapthor deployment or default cutover:** separately qualified workflow
  behaviour, complete-path performance and operational acceptance, with the
  feature-flagged PyBDSF fallback retained until the acceptance matrix passes.

Release Please owns versions, changelogs and tags. Task commits stay local for
human review and push.

## Collaboration and repair decisions

These rules govern agent work on this plan and are referenced from
[`AGENTS.md`](../AGENTS.md).

- The agent owns routine completeness checks, integration checks and clear
  recommendations. Do not depend on the user discovering missing checks,
  requesting a cheap diagnostic or reconstructing status across
  conversations. Reserve human attention for scientific interpretation,
  priorities and trade-offs that require human judgment.
- Before a scientific or campaign repair, write a short decision statement in
  the existing task or plan: observed problem, proposed cause, independent
  test, expected measurable change and stopping condition. Distinguish a
  correctness defect, agreed-gate failure, operational failure and optional
  improvement; an aggregate failed endpoint alone does not establish a cause.
- After two repairs aimed at the same mechanism produce no material change
  against the stated expectation, review the diagnosis and recommend a
  bounded next step before another full replay. This is a reassessment
  trigger, not permission to abandon required work, change gates or retry
  closed evidence.
- Follow the approved scope and severity policy. Keep development closure,
  scientific qualification, release and default cutover distinct, as in the
  delivery policy above. Record optional improvements as deferred work rather
  than automatically expanding the current milestone. Known incorrect
  supported outputs remain release blockers; a phase label or accepted
  development limitation cannot waive them.
- Carry existing authorization forward within its scope. Complete authorized
  preparation and present a concrete recommendation before requesting a new
  scientific or resource decision. Explain the exact boundary requiring that
  decision; do not add approval steps for routine reversible work.
- At milestone reviews, use the existing log to assess time to actionable
  diagnosis, avoidable campaign interruptions, repairs without useful change
  and user effort needed to recover status or scope. Use these observations
  to improve the workflow, not commit counts, test totals or documentation
  volume as productivity targets. Do not introduce a separate tracking
  framework.

## v0.7.0 experimental release

Publish v0.7.0 before starting scaling work. No version is otherwise
preassigned; a later fix, measured optimization or API improvement can repeat
R3–R5 for its own `0.x` release.

- [ ] **R1 — Merge the closed-campaign cleanup (PR 3).** The branch removes
      closed Phase 5 tooling, records, archive-only tests and reference pages,
      makes the notebook comparison workflow campaign-independent, and passes
      the local handoff checks recorded in `LOG.md`. Done when human review is
      complete and hosted CI passes. Stop if public science bytes or
      Serial/Dask results change, or a retained notebook workflow loses its
      replacement.
- [ ] **R2 — Prepare release readiness on a final small branch.**
      - Review the aggregate diff since v0.6.0 against `CODE_REVIEW.md`,
        including the public and `hebog.validation` breaking changes.
      - Confirm the wheel contains no removed campaign modules or records.
      - Decide the retained-validation CI partition. Fold
        `tests/unit/validation` into the portable matrix after it passes on
        hosted macOS and Windows runners, or keep the partition with a stated
        reason.
      - Refresh user-facing paths and limitations in the README, docs home,
        release status and tutorial.
      - Run `just ci` locally and the hosted matrix: Linux on Python
        3.12–3.14, plus macOS and Windows on Python 3.14.
- [ ] **R3 — Refresh and inspect the notebook comparison.** On the release
      candidate, run the Hebog refresh preflight, then refresh the 13 saved
      SDC1/Hydra/LoTSS inputs while reusing the saved PyBDSF/Aegean products.
      Inspect positions, unavailable measurements, empty and difficult
      extended regions with the user. A newly confirmed incorrect supported
      output blocks the release; existing statistical limitations follow the
      severity policy. This is a diagnostic workflow, not a campaign or parity
      evidence, and larger notebook images do not expand the public envelope.
- [ ] **R4 — Review the release PR.** State "experimental, scientifically
      unqualified", the tested input and resource envelope, known limitations
      and every breaking change. Verify the Release Please version, changelog,
      citation and lockfile changes rather than preparing them by hand.
- [ ] **R5 — Release through the existing workflow.** Configure the GitHub
      environment and PyPI Trusted Publisher using the
      [publishing guide](../docs/how-to/publish-releases.md). After main and
      the release PR checks pass, the human merges the Release Please PR and
      verifies the tag, the GitHub release and the PyPI upload. Update release
      status without copying campaign history into release notes.

## After v0.7.0

Take one row as a bounded work item and split it further when a measured
result reveals independent changes. Each item can merge and release with its
own checks. Qualification and deployment rows authorize only their stated
claim and still need their own scientific and resource decisions.

| When | Task | Done when |
| --- | --- | --- |
| Before scaling work | Add a reusable synthetic comparison campaign. Rebuild the population generator, driver, truth evaluation and paired statistics from Git history without the removed authorization layer. | One checked-in campaign configuration generates a fresh seed-disjoint continuum and compact-blend population, runs Hebog, released PyBDSF and Aegean (optionally pinned PyBDSF `master`), evaluates each finder against injected truth, writes resumable results the comparison notebook reads, and reports paired comparisons. Decide population size and power, pass/fail versus report-only rules, references and compute budget in the PR. Run it on the current candidate to give scaling work a scientific reference. |
| Next | Freeze a known-issues runtime baseline and profile complete FITS-to-products execution. | Inputs, candidate, resources and every warm-up and measured run are recorded; CPU, RSS, I/O and task costs identify the first material bottleneck. No speedup or qualification claim from this baseline alone. |
| Next | Remove one measured I/O, copy, materialization or fit-batching bottleneck. | Paired before/after evidence covers affected and adjacent anchors and crossovers; scientific non-regression and Serial/Dask invariance pass. Ship each useful optimization independently. |
| Next | Complete the shared Serial/local/Dask executor contract and add persistent local threads. | Ordering, serialization, errors, cancellation, retry and resource budgets pass the same contract suite; no nested pools or clusters. Existing Dask execution is extended, not reimplemented. |
| Next | Remove the public terminal's complete-plane requirement. | Catalogue, measurement and publication operate through bounded Zarr windows or shards and hierarchical summaries; small analytic edge, corner and partition tests agree exactly. Qualify one larger size tier at a time before raising admission limits. |
| Next | Qualify a deployment Zarr store and restart/recovery path. | Atomicity, concurrent owned-chunk writes, codec and chunk geometry, missing chunks, cold/warm throughput and injected failures pass within an admitted memory budget. Publish the tested store envelope. |
| When scientifically prioritized | Resolve one remaining association, uncertainty, RMS/mask or flux-tail mechanism. | Prospective independent controls distinguish the cause; focused public-workflow and paired non-regression checks pass. Preserve source/component distinctions and explicit unavailable outputs. |
| Before claiming general scientific readiness | Complete candidate-bound parity/retention and fresh held-out and public-survey evidence. | Every binding endpoint passes under a prospectively reviewed contract, population and power design. Closed failed campaigns are never reused as confirmation. |
| Before claiming general scientific readiness | Design a current readiness packet and obtain independent acceptance. | The packet binds cumulative and fresh evidence, public API, execution and performance checks, with separate radio-astronomy and engineering acceptances. The restricted Rapthor profile stays in its own integration packet. |
| After general parity/retention | Audit the pinned Rapthor/LSMTool consumer and freeze its workflow profile. | Native catalogue, mask and RMS fields and filtering semantics are exercised on true/apparent, bright, extended, edge, masked, sparse and crowded populations against both PyBDSF references. Choose compact only with ≥99.5% overall agreement and every safety stratum passing; otherwise continuum. |
| Integration increment | Add Rapthor backend selection, restartable true-sky/flat-noise/filter tasks and dual-run reporting. | Acceptance scenarios cover empty and corrupt input, restart, retry, backend selection and PyBDSF fallback. Concurrent branches respect the caller's resource budget. |
| Before supported Rapthor deployment | Run matched complete `filter_skymodel` benchmarks and operational acceptance. | Both runtime gates below pass across the frozen initial envelope; science, profile, retry/resume and memory gates pass. Retain fallback outside the admitted envelope. |
| Before each scale claim | Qualify the next size or topology and extend complete-path benchmarks. | Add 30,000 then 100,000-square anchors, both sides of new crossovers, deployment storage and recovery. Prove invariance at 1, 10, 50, 100 and at least 200 workers. Small-machine evidence does not establish facility support. |
| Before default cutover / 1.0 | Complete operational soak and production review. | The full scientific, compatibility and performance matrix, 100,000-square facility gates, portability, security, licensing, packaging, current docs and independent acceptance pass. Native code, if added, also needs its wheel, safety and fallback matrix. |

Optional comparison finders, such as ProFound or a dedicated 2D SoFiA
experiment, are follow-up work; see the
[notebook guide](../docs/how-to/notebooks.md).

## Scientific gates

Analytic or injected truth is primary. Released PyBDSF is the Rapthor
compatibility reference; pinned PyBDSF `master` is independently binding.
Aegean is binding for applicable compact and Gaussian populations. No finder is
scientific truth.

- Each campaign uses its own prospectively reviewed endpoint registry and
  decision contract. Choose a whole incumbent before viewing results; never
  combine historical best values into a synthetic comparator.
- Require every applicable relative PyBDSF, Aegean and incumbent Hebog
  comparison, with fixed practical margins and the conjunctive one-sided
  confidence rule. Inconclusive binding evidence is not parity. An old
  candidate's uncertainty exception does not transfer to a replacement.
- Freeze population, semantic applicability, independent sampling unit,
  margins, missing-output rules and endpoint and joint power before execution.
  Pair and resample whole realizations, not dependent source rows or pixels.
  Planning variance sizes the study; the observed-data interval decides.
  Superiority claims need a prospective multiplicity rule, and improvements
  cannot compensate for failed binding checks.
- Product validity, finite or explicitly unavailable measurements, complete
  processing status, schemas, provenance and deterministic execution remain
  binding. Report absolute targets separately. Retain all morphology, scale,
  SNR, noise and boundary strata.
- Compare like source, component and support semantics. Use original pixels
  for flux and photometry and valid pixels for mask precision, recall and IoU.
  Report splits, merges, duplicates and low-SNR completeness and reliability
  separately.
- Before a long campaign or replay, run a bounded development screen through
  the same runner and evaluator with an explicit time and resource budget.
  Select cases before inspecting results: ordinary controls, independent
  examples of known failure mechanisms, valid empty results, and numerical and
  invalid-pixel boundaries. Exercise the public finder, native product
  reading, evaluation, aggregation and Serial/existing-Dask agreement. A
  clean screen is neither powered parity nor a prediction of campaign
  success; resolve or explicitly defer its warnings before launch.

The dataset matrix retains compact SNR 3–100, blends, diffuse Gaussians,
filaments and shells, mixed emission, different beams, WCS, pixel scales and
units, negative backgrounds, empty, all-NaN and invalid data, varying noise,
image edges and all tile-edge and corner topologies. Every dataset has a
development, regression or qualification role, provenance, checksums and
generator identity, and new populations must be seed-disjoint from existing
manifests. General qualification includes public or challenge cut-outs from at
least two telescope families. Compare Serial before alternate executors and
external finders.

Durable cross-project targets are reported separately from binding relative
and validity gates; the Rapthor profile has its own agreement and safety
requirements.

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

## Performance and scale gates

For supported Rapthor deployment, matched complete-step median ratios and
their upper one-sided 95% bootstrap confidence bounds must satisfy:

```text
Hebog / released PyBDSF <= 0.50
Hebog / pinned PyBDSF master < 1.00
```

Scientific eligibility precedes performance acceptance. These are minimum
deployment gates, not a reason to stop optimizing or to hold an experimental
standalone release.

- Maintain 256, 512, 1,024, 3,000, 8,000, 10,000, 30,000 and 100,000-square
  anchors, sparse, normal and dense-extended workloads, and both sides of
  every measured crossover. Gate early deployment on its frozen envelope;
  facility and 1.0 qualification need the whole matrix.
- Match inputs and checksums, revisions and dependencies, output mode, host,
  affinity, CPU and native threads, workers, memory, storage and cache policy.
  Use a warm-up plus at least five measured repetitions, retain every value,
  median and dispersion, and avoid unrelated workloads.
- Record wall and CPU time, worker and aggregate RSS, I/O, task and graph size,
  transfers, spill, failures and retries, tile and halo geometry, boundary
  summaries, occupancy, scheduler load, throughput and headroom. Scale
  evidence adds reduction depth, stragglers and strong/weak efficiency. Record
  unavailable instrumentation with a reason, never zero, using versioned
  `hebog.validation.evidence` records.
- Hebog non-regression needs an upper one-sided 95% bound ≤1.05 against the
  previous reviewed curve; a lower bound >1.05 is a regression and crossing
  the margin is inconclusive. A >10% peak worker or aggregate memory
  regression against either PyBDSF reference needs an approved throughput
  trade-off.
- Component budgets, including the four-core 6-second multiscale budget at
  3,000 pixels, remain diagnostic; complete filtering decides deployment.
  Exact budgets are in the
  [performance and scalability contracts](../docs/reference/performance-scalability-contracts.md).

## Architecture and documentation boundaries

Keep the scientific library pipeline-neutral, with inert imports, small typed
requests and results, and no implicit clients, clusters or pools. Maintain
Serial as the oracle, Zarr as the sole intermediate plane backend,
stage-specific halos, global ownership and hierarchical reductions. Never
raise the public size limit by sending a complete large plane to one worker.
Preserve dtype unless scientific evidence supports a change. Prefer
established libraries, NumPy/SciPy, then profiled Numba; new native code needs
an accepted ADR, the 10% profile, 2× kernel and 5% end-to-end gates, and
portable distribution. The [architecture](../docs/architecture/index.md),
[native-code assessment](../docs/explanation/native-code-assessment.md) and
[`AGENTS.md`](../AGENTS.md) hold the detailed requirements.

Keep the README, docs home, release status and tutorial focused on current
behaviour, replacing stale summaries when status changes. Record chronology in
`LOG.md` or Git history, not as another "latest" section in user guidance.
Removing a historical narrative never changes a closed result.
